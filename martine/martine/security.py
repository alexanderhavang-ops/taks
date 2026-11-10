"""Server supplied identity; enforce scope inside tools, independently of prompts."""
from dataclasses import dataclass, asdict
import functools
import inspect
import json
import os
import re


@dataclass(frozen=True)
class Principal:
    username: str = ''
    unit: str = ''
    admin: bool = False
    authenticated: bool = False
    sender_uid: str = ''
    callsign: str = ''
    device_uids: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()
    transport: str = 'anonymous'

    def as_dict(self):
        return asdict(self)

    @property
    def session_scope(self):
        return '|'.join((self.unit, self.username, 'admin' if self.admin else 'user'))


def current_principal():
    data = json.loads(os.environ.get('MARTINE_AUTH_CONTEXT', '{}'))
    for key in ('device_uids', 'channels'):
        data[key] = tuple(data.get(key) or ())
    return Principal(**data)


SECRET = re.compile(r'password|passwd|secret|token|api.?key|private.?key|authorization|download_url|card_url', re.I)


def sanitize(value):
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if SECRET.search(str(k)) else sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        try:
            nested = json.loads(value)
        except (ValueError, TypeError):
            nested = None
        if isinstance(nested, (dict, list)):
            return json.dumps(sanitize(nested), ensure_ascii=False)
        value = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[REDACTED KEY]', value, flags=re.S)
        value = re.sub(r'(?i)(authorization\s*[:=]\s*)(?:basic|bearer)\s+\S+', r'\1[REDACTED]', value)
        value = re.sub(r"(?im)((?:password|passwd|secret|token|api[_-]?key)[\"']?\s*(?:[:=]|\bis\b)\s*)[^\r\n]*", r'\1[REDACTED]', value)
        value = re.sub(r'(https?://)[^/\s:@]+:[^@\s]+@', r'\1[REDACTED]@', value)
        return re.sub(r'(/onboarding/cards/)[A-Za-z0-9_-]+', r'\1[REDACTED]', value)
    return value


PUBLIC = frozenset({'ping', 'get_current_time', 'list_reference_docs', 'search_reference_docs',
    'search_reference_docs_semantic', 'get_reference_doc_context', 'list_reference_doc_sections',
    'get_reference_section', 'route_between_points', 'route_alternatives_between_points', 'snap_point_to_network'})
SELF = frozenset({'get_onboarding_diagnostics', 'get_my_connection_events'})
DELIVERY = frozenset({'send_voice_onboarding', 'send_map_onboarding', 'send_plugin_onboarding'})
ADMIN = frozenset({'get_taks_paths','get_taks_state_summary','get_my_position','get_my_mgrs','get_contact_status','get_last_seen','get_distance_to_callsign','get_nearest_friendly','get_enemy_contacts_near_me','business_read','read_diagnostic_log','diagnostic_file_stat','marti_read','request_business_change','product_health','network_capture_start','network_capture_status'})
NEVER = frozenset({'ensure_martine_state_dirs', 'martine_offline_self_test', 'martine_live_inference_test'})


def allowed(name, actor):
    return name not in NEVER and (name in PUBLIC or (actor.authenticated and (name in SELF | DELIVERY or (actor.admin and name in ADMIN))))


def authorize(name, values, actor):
    if not allowed(name, actor):
        raise PermissionError('Tool unavailable for this account')
    values = dict(values)
    if name in SELF:
        target = str(values.get('username') or actor.username)
        if not actor.admin and target != actor.username:
            raise PermissionError('Only your own account is accessible')
        values['username'] = target
    if name in DELIVERY and not actor.admin:
        uid = str(values.get('target_uid') or actor.sender_uid)
        if not uid or uid not in actor.device_uids:
            raise PermissionError('Delivery requires one of your registered devices')
        if values.get('target_callsign') not in (None, '', actor.callsign):
            raise PermissionError('Delivery is limited to your own callsign')
        for key in ('mumble_host', 'server_password', 'channel_passwords'):
            if values.get(key):
                raise PermissionError('Server settings are managed by TAKS')
        if values.get('channels') and not set(values['channels']).issubset(actor.channels):
            raise PermissionError('Channel outside your account')
        values.update(target_uid=uid, target_callsign=actor.callsign)
    for key, value in (('sender_uid', actor.sender_uid), ('sender_callsign', actor.callsign)):
        if key in values:
            values[key] = value
    return values


def scoped_tool(function, name):
    signature = inspect.signature(function)
    @functools.wraps(function)
    def invoke(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        return sanitize(function(**authorize(name, bound.arguments, current_principal())))
    return invoke
