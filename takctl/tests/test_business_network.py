import importlib.machinery
import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from takctl.services import business_network as service
ROOT=Path(__file__).resolve().parents[2]
helper=importlib.machinery.SourceFileLoader('capture_helper',str(ROOT/'takctl/bin/taks-network-capture')).load_module()
ADMIN={'username':'operator','unit':'unit','admin':True,'authenticated':True}

class NetworkDiagnosticsTests(unittest.TestCase):
    def test_discovery_lists_client_ip_and_never_returns_packet_payload(self):
        summary=helper.Summary('',[8446,5222],True)
        for line in [
            '100.1 eth0 In IP 81.2.3.4.50000 > 172.31.0.2.8446: Flags [S], seq 1, HTTP: password=private',
            '100.2 IP 172.31.0.2.8446 > 81.2.3.4.50000: Flags [S.], seq 1, ack 2',
            '100.3 IP 81.2.3.4.50000 > 172.31.0.2.8446: Flags [.], ack 2',
            '100.4 IP6 2001:db8::4.50123 > 2001:db8::2.5222: Flags [S], seq 1',
        ]:summary.feed(line)
        data=summary.result();self.assertEqual(data['packets'],3);self.assertEqual(data['client_ips'],['2001:db8::4','81.2.3.4'])
        row=next(v for v in data['flows'] if v['server_port']==8446)
        self.assertEqual(row['client_syn'],1);self.assertEqual(row['server_syn_ack'],1)
        self.assertNotIn('private',json.dumps(data));self.assertNotIn('password',json.dumps(data).replace('password failure',''))

    def test_follow_up_ip_capture_includes_resets_and_ignores_other_clients(self):
        summary=helper.Summary('81.2.3.4',[64738],False)
        for line in ['100 IP 81.2.3.4.50000 > 172.31.0.2.64738: Flags [S], seq 1',
                     '101 IP 172.31.0.2.64738 > 81.2.3.4.50000: Flags [R.], seq 1',
                     '102 IP 81.2.3.5.50001 > 172.31.0.2.64738: Flags [S], seq 1']:
            summary.feed(line)
        self.assertEqual(summary.result()['flows'][0]['server_rst'],1)
        self.assertEqual(summary.result()['packets'],2)

    def test_filters_and_duration_cannot_be_used_for_shell_or_bpf_injection(self):
        for args in [('fe80::1%eth0 or host 1.2.3.4',[8446],60,True),('81.2.3.4 or net 0/0',[8446],60,True),('',[0],60,True),('',list(range(1,18)),60,True),('',[],60,True),('',[8446],61,True)]:
            with self.subTest(args=args),self.assertRaises(ValueError):helper.validate(*args)
        self.assertEqual(helper.capture_filter('81.2.3.4',[443,8446]),'(tcp or udp) and host 81.2.3.4 and (port 443 or port 8446)')

    def test_capture_jobs_are_admin_only_and_bound_to_requesting_identity(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'TAKS_NETWORK_DB':str(Path(tmp)/'jobs.sqlite')}),patch.object(service.POOL,'submit') as pool,patch('takctl.services.business_network.Path.is_socket',return_value=True):
            with self.assertRaises(PermissionError):service.start({**ADMIN,'admin':False},ports=[8446])
            data=service.start(ADMIN,ports=[8446]);pool.assert_called_once()
            with self.assertRaises(ValueError):service.start(ADMIN,ports=[8446])
            with self.assertRaises(PermissionError):service.status({**ADMIN,'username':'other'},data['capture_id'])
            with self.assertRaises(PermissionError):service.status({**ADMIN,'admin':False},data['capture_id'])
            self.assertEqual(service.status(ADMIN,data['capture_id'])['status'],'running')

    def test_missing_socket_reports_setup_required_without_starting_job(self):
        with patch('takctl.services.business_network.Path.is_socket',return_value=False),patch.object(service.POOL,'submit') as pool:
            self.assertTrue(service.start(ADMIN,ports=[8446])['setup_required'])
            pool.assert_not_called()

    def run_broker_request(self, uid, request):
        client=MagicMock()
        client.__enter__.return_value=client
        client.getsockopt.return_value=struct.pack('3i',123,uid,1000)
        client.recv.side_effect=[request,b'']
        server=MagicMock()
        server.accept.side_effect=[(client,None),helper.socket.timeout()]
        with patch.dict(os.environ,{'LISTEN_PID':str(os.getpid()),'LISTEN_FDS':'1'}),patch.object(helper.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000)),patch.object(helper.socket,'socket',return_value=server),patch.object(helper,'capture',return_value={'ok':True,'packets':0}) as capture:
            helper.serve()
        return client,capture

    def test_broker_rejects_unrelated_local_identity_before_reading_request(self):
        client,capture=self.run_broker_request(1001,b'{}\n')
        client.recv.assert_not_called()
        capture.assert_not_called()

    def test_broker_accepts_only_fixed_json_request_from_service_identity(self):
        request={'host_ip':'','ports':[8446],'seconds':1,'syn_only':True}
        client,capture=self.run_broker_request(1000,json.dumps(request).encode()+b'\n')
        capture.assert_called_once_with('',[8446],1,True)
        self.assertEqual(json.loads(client.sendall.call_args.args[0]),{'ok':True,'packets':0})

    def test_broker_rejects_extra_fields_oversized_and_incomplete_requests(self):
        for request in [b'{"command":"id"}\n',b'x'*1025+b'\n',b'{}']:
            with self.subTest(request=request[:40]):
                client,capture=self.run_broker_request(1000,request)
                capture.assert_not_called()
                self.assertFalse(json.loads(client.sendall.call_args.args[0])['ok'])

    def test_broker_requires_systemd_socket_activation(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(RuntimeError):
            helper.serve()

    def test_capture_uses_bounded_non_promiscuous_tcpdump_and_summarizes_output(self):
        read_fd,write_fd=os.pipe()
        os.write(write_fd,b'100 IP 81.2.3.4.50000 > 172.31.0.2.8446: Flags [S], seq 1, password=private\n')
        os.close(write_fd)
        with os.fdopen(read_fd,'rb') as output:
            proc=MagicMock(stdout=output,returncode=0)
            proc.poll.return_value=0
            with patch.object(helper.subprocess,'Popen',return_value=proc) as popen:
                result=helper.capture('',[8446],1,True)
        command=popen.call_args.args[0]
        self.assertIn('-p',command)
        self.assertEqual(command[command.index('-c')+1],'4096')
        self.assertEqual(result['client_ips'],['81.2.3.4'])
        self.assertNotIn('private',json.dumps(result))
