"""Build a voice-only profile from policy selection and actual Murmur channel IDs."""
from pathlib import Path
import sqlite3

MUMBLE_DB = Path('/var/lib/mumble-server/mumble-server.sqlite')


def live_channel_profile(username: str, vx: dict, *, database: Path | None = None) -> dict:
    database = database or MUMBLE_DB
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        rows = db.execute('SELECT channel_id,name FROM channels WHERE server_id=1').fetchall()
    ids = {}
    for identity, name in rows:
        ids.setdefault(name, []).append(identity)
    channels = []
    for selected in vx['channels']:
        name = selected['name']
        matches = ids.get(name, [])
        if len(matches) != 1:
            raise ValueError('Selected voice channel is missing or ambiguous')
        channels.append({'id': matches[0], 'name': name})
    if not channels or len(channels) > 128:
        raise ValueError('No valid voice channels')
    return {'_username': username, '_display': username, 'host': vx['host'], 'port': int(vx['port']),
            'missionName': vx['mission_name'], 'channels': channels}
