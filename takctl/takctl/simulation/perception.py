"""Durable actor knowledge and directed inboxes. No inference or action execution."""
import json
import sqlite3
import threading
import time


class PerceptionStore:
    def __init__(self,path):
        self.lock=threading.RLock()
        self.db=sqlite3.connect(str(path),check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA cache_size=-1024')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS messages(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_uid TEXT UNIQUE,sender_uid TEXT,body TEXT,channel TEXT,received_at REAL);
        CREATE TABLE IF NOT EXISTS deliveries(seq INTEGER,recipient_uid TEXT,PRIMARY KEY(seq,recipient_uid));
        CREATE INDEX IF NOT EXISTS recipient_messages ON deliveries(recipient_uid,seq);
        CREATE TABLE IF NOT EXISTS knowledge(actor_uid TEXT PRIMARY KEY,revision INTEGER,facts TEXT);
        CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY,actor_uid TEXT,result TEXT);
        ''')
        self.db.commit()

    def receive(self,event_uid,sender_uid,recipients,body,channel='GeoChat'):
        if not isinstance(body,str) or len(body)>2000 or len(event_uid)>256 or len(sender_uid)>256 or len(channel)>128:
            raise ValueError('Invalid bounded message')
        recipients=sorted(set(recipients))
        if len(recipients)>1024 or any(not isinstance(r,str) or len(r)>256 for r in recipients):raise ValueError('Invalid recipients')
        with self.lock,self.db:
            row=self.db.execute('SELECT seq FROM messages WHERE event_uid=?',(event_uid,)).fetchone()
            if row:return {'seq':row[0],'duplicate':True}
            cursor=self.db.execute('INSERT INTO messages(event_uid,sender_uid,body,channel,received_at) VALUES(?,?,?,?,?)',(event_uid,sender_uid,body,channel,time.time()))
            seq=cursor.lastrowid
            self.db.executemany('INSERT INTO deliveries VALUES(?,?)',((seq,r) for r in recipients))
            # A shared bounded journal, not a copy of each body for every soldier.
            self.db.execute('DELETE FROM deliveries WHERE seq < ?',(max(0,seq-10000),))
            self.db.execute('DELETE FROM messages WHERE seq < ?',(max(0,seq-10000),))
            return {'seq':seq,'duplicate':False,'recipients':len(recipients)}

    def events(self,after_seq=0,limit=50,actor_uid=None):
        if type(after_seq) is not int or after_seq<0 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Invalid event cursor/limit')
        with self.lock:
            if actor_uid:
                rows=self.db.execute('SELECT m.seq,m.event_uid,m.sender_uid,m.body,m.channel,m.received_at FROM messages m JOIN deliveries d ON m.seq=d.seq WHERE d.recipient_uid=? AND m.seq>? ORDER BY m.seq LIMIT ?',(actor_uid,after_seq,limit)).fetchall()
            else:rows=self.db.execute('SELECT seq,event_uid,sender_uid,body,channel,received_at FROM messages WHERE seq>? ORDER BY seq LIMIT ?',(after_seq,limit)).fetchall()
            oldest=self.db.execute('SELECT MIN(seq) FROM messages').fetchone()[0]
        return {'events':[dict(zip(('seq','event_uid','sender_uid','body','channel','received_at'),r)) for r in rows],
            'next_seq':rows[-1][0] if rows else after_seq,'cursor_gap':bool(oldest and after_seq and after_seq<oldest-1)}

    def actor(self,uid,after_seq=0,limit=50):
        with self.lock:
            row=self.db.execute('SELECT revision,facts FROM knowledge WHERE actor_uid=?',(uid,)).fetchone()
        return {'actor_uid':uid,'actor_revision':row[0] if row else 0,'knowledge':json.loads(row[1]) if row else {},**self.events(after_seq,limit,uid)}

    def put(self,uid,request_id,expected_revision,facts):
        if not isinstance(request_id,str) or not 1<=len(request_id)<=128 or type(expected_revision) is not int or expected_revision<0:raise ValueError('Invalid actor write identity/revision')
        if not isinstance(facts,dict) or len(json.dumps(facts,allow_nan=False).encode())>8192:raise ValueError('Actor knowledge must be an object <=8KiB')
        with self.lock,self.db:
            previous=self.db.execute('SELECT actor_uid,result FROM requests WHERE request_id=?',(request_id,)).fetchone()
            if previous:
                if previous[0]!=uid:raise ValueError('Request belongs to another actor')
                return {**json.loads(previous[1]),'duplicate':True}
            row=self.db.execute('SELECT revision FROM knowledge WHERE actor_uid=?',(uid,)).fetchone()
            revision=row[0] if row else 0
            if revision!=expected_revision:raise ValueError('Actor revision conflict')
            self.db.execute('INSERT OR REPLACE INTO knowledge VALUES(?,?,?)',(uid,revision+1,json.dumps(facts,allow_nan=False)))
            result={'ok':True,'actor_uid':uid,'actor_revision':revision+1}
            self.db.execute('INSERT INTO requests VALUES(?,?,?)',(request_id,uid,json.dumps(result)))
            self.db.execute('DELETE FROM requests WHERE rowid NOT IN (SELECT rowid FROM requests ORDER BY rowid DESC LIMIT 10000)')
            return result
