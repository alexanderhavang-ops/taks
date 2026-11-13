"""Deterministic, persisted ambient routes. No planner, randomness or network I/O."""
import copy
from .model import distance, make_path, number, advance_path


def policy(start, args):
    rows = args.get('waypoints')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise ValueError('waypoints requires 1..64 position/travel_s/wait_s entries')
    repeat = args.get('repeat', False)
    if type(repeat) is not bool: raise ValueError('repeat must be boolean')
    legs, cursor, duration = [], dict(start), 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'position', 'travel_s', 'wait_s'}:
            raise ValueError('Each waypoint needs position, travel_s and wait_s')
        move = make_path(cursor, {'path':[row['position']], 'duration_s':row['travel_s']})
        wait = number(row['wait_s'], 'wait_s', 0, 86400)
        legs.append({'move':move, 'wait_s':wait})
        cursor = move['path'][-1]
        duration += move['duration_s'] + wait
    if repeat and distance(start,cursor) > .1:
        raise ValueError('Repeating routes must return to their starting position')
    return {'enabled': True, 'repeat':repeat, 'delay_s':number(args.get('delay_s',0),'delay_s',0,86400),
            'elapsed_s':0, 'cycle_s':duration, 'legs':legs, 'phase':'waiting', 'cycles':0}


def suspend(entity):
    if entity.get('background'): entity['background']['enabled'] = False


def advance(entity, seconds):
    p = entity.get('background')
    if not p or not p['enabled'] or entity.get('move') or entity.get('health_state','fit') != 'fit': return False
    p['elapsed_s'] += max(0,seconds)
    elapsed = p['elapsed_s'] - p['delay_s']
    if elapsed < 0: return True
    if p['repeat']:
        p['cycles'] = int(elapsed // p['cycle_s'])
        elapsed %= p['cycle_s']
    elif elapsed >= p['cycle_s']:
        entity['position'] = dict(p['legs'][-1]['move']['path'][-1])
        p.update(enabled=False, phase='completed', elapsed_s=p['delay_s']+p['cycle_s'])
        return True
    for i, leg in enumerate(p['legs']):
        length = leg['move']['duration_s'] + leg['wait_s']
        if elapsed < length:
            move = copy.deepcopy(leg['move'])
            entity['position'], _ = advance_path(move,min(elapsed,move['duration_s']))
            p.update(waypoint_index=i,phase='moving' if elapsed < move['duration_s'] else 'waiting')
            break
        elapsed -= length
    return True
