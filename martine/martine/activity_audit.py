"""Shared activity watermark calls. No inference or message content is retained."""
import importlib
import sys
sys.path.append('/opt/tak/tools/takctl')
from takctl.services import activity_evidence as node_audit


def attach_mumble(client,module,is_human):
    callbacks=importlib.import_module(module.__name__+'.callbacks')
    client._idle_audit_connected=False
    def connected(*_):client._idle_audit_connected=True
    def disconnected(*_):
        client._idle_audit_connected=False
        node_audit.pulse('voice',False,force=True)
    def created(*args):
        if args and is_human(args[0]):node_audit.note('voice')
    client.callbacks.set_callback(callbacks.PYMUMBLE_CLBK_CONNECTED,connected)
    client.callbacks.set_callback(callbacks.PYMUMBLE_CLBK_DISCONNECTED,disconnected)
    client.callbacks.set_callback(callbacks.PYMUMBLE_CLBK_USERCREATED,created)
