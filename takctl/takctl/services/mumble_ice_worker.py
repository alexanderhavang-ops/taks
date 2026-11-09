"""Fixed JSON-over-stdin worker for system Python's installed Mumble Ice bindings."""
import json
from pathlib import Path
import sys


def invoke(server, operation, args):
    if operation == 'snapshot':
        return {'channels': [{'id': c.id, 'parent': c.parent, 'name': c.name}
                             for c in server.getChannels().values()],
                'users': [{'session': u.session, 'name': u.name, 'channel': u.channel,
                           'userid': u.userid} for u in server.getUsers().values()]}
    if operation == 'channel_create':
        return {'channel_id': server.addChannel(args['name'], args['parent'])}
    if operation == 'channel_rename':
        channel = server.getChannelState(args['channel_id'])
        channel.name = args['name']
        server.setChannelState(channel)
        return {'channel_id': channel.id}
    if operation == 'channel_delete':
        server.removeChannel(args['channel_id'])
        return {'channel_id': args['channel_id']}
    raise ValueError('Unknown Mumble operation')


def main():
    import Ice
    Ice.loadSlice('-I/usr/share/ice/slice --all /etc/mumble/MumbleServer.ice')
    import MumbleServer
    message = json.loads(sys.stdin.read(8193))
    operation, args = message['operation'], message['arguments']
    if operation not in ('snapshot', 'channel_create', 'channel_rename', 'channel_delete'):
        raise ValueError('Unknown Mumble operation')
    init = Ice.InitializationData()
    init.properties = Ice.createProperties()
    init.properties.setProperty('Ice.ImplicitContext', 'Shared')
    with Ice.initialize([], init) as communicator:
        communicator.getImplicitContext().setContext({
            'secret': Path('/etc/taks/mumble-ice-secret').read_text().strip()})
        meta = MumbleServer.MetaPrx.checkedCast(communicator.stringToProxy(
            'Meta:tcp -h 127.0.0.1 -p 6502').ice_invocationTimeout(5000))
        server = meta.getServer(args.get('server_id', 1)).ice_invocationTimeout(5000)
        print(json.dumps({'ok': True, 'data': invoke(server, operation, args)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': type(exc).__name__}))
        sys.exit(1)
