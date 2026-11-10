"""Identity comes from the backing directory, never a chat message or callsign."""
import base64
import re

USER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')


def account_actor(username, *, transport='web', sender_uid=''):
    from takctl.config import load_config
    from takctl.services.ldap_user_store import LdapUserStore, selected_backing_user_store
    cfg = load_config()
    if not USER.fullmatch(username):
        raise PermissionError('Invalid account')
    if selected_backing_user_store() == 'ldap':
        user = LdapUserStore().get_user(username)
        admin = bool(user and str(cfg.get('ldap_admin_group', 'TAKS_ADMIN')) in user.groups)
    else:
        from takctl.onboarding.user_directory_xml import UserDirectoryXml
        user = UserDirectoryXml('/opt/tak/UserAuthenticationFile.xml').get_user(username)
        admin = bool(user and username == str(cfg.get('takctl_admin_user', 'admin')))
    if user is None:
        raise PermissionError('Account unavailable')
    return {'username': user.username, 'unit': str(cfg.get('fqdn') or cfg.get('node_fqdn') or ''),
            'admin': admin, 'authenticated': True, 'sender_uid': '', 'callsign': '',
            'device_uids': (), 'channels': (), 'transport': transport}


def request_actor(request):
    from takctl.web.core.auth_routes import get_session
    session = get_session(request)
    if session:
        return account_actor(str(session.get('u') or ''))
    header = request.headers.get('authorization', '')
    if header.lower().startswith('basic '):
        try:
            username, password = base64.b64decode(header.split()[1], validate=True).decode().split(':', 1)
            from takctl.services.marti_auth import check_selected_user_store
            if check_selected_user_store(username, password).ok:
                return account_actor(username, transport='basic')
        except (ValueError, UnicodeError):
            pass
    raise PermissionError('Authentication required')
