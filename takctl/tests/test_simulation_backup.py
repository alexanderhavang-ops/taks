import sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from takctl.services import orchestrator_backup

class ActorBackupTests(unittest.TestCase):
    def test_wal_actor_store_is_snapshotted_through_sqlite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);live=root/'live';archive=root/'archive';live.mkdir()
            db=sqlite3.connect(live/'perception-test.sqlite');db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE facts(body TEXT)');db.execute("INSERT INTO facts VALUES('current report')");db.commit()
            def path(value):
                if value=='/opt/tak/simulation':return live
                if value=='/opt/tak/tools/takctl/state/simulation-perception':return archive
                return Path(value)
            with patch.object(orchestrator_backup,'Path',side_effect=path):orchestrator_backup._takctl_state_paths()
            with sqlite3.connect(archive/'perception-test.sqlite') as restored:
                self.assertEqual(restored.execute('SELECT body FROM facts').fetchone()[0],'current report')
            db.close()
