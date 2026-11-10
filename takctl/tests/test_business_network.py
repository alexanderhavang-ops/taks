import importlib.machinery
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
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
        for args in [('81.2.3.4 or net 0/0',[8446],60,True),('',[0],60,True),('',list(range(1,18)),60,True),('',[],60,True),('',[8446],61,True)]:
            with self.subTest(args=args),self.assertRaises(ValueError):helper.validate(*args)
        self.assertEqual(helper.capture_filter('81.2.3.4',[443,8446]),'(tcp or udp) and host 81.2.3.4 and (port 443 or port 8446)')

    def test_capture_jobs_are_admin_only_and_bound_to_requesting_identity(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'TAKS_NETWORK_DB':str(Path(tmp)/'jobs.sqlite')}),patch.object(service.POOL,'submit') as pool,patch('takctl.services.business_network.Path.is_file',return_value=True):
            with self.assertRaises(PermissionError):service.start({**ADMIN,'admin':False},ports=[8446])
            data=service.start(ADMIN,ports=[8446]);pool.assert_called_once()
            with self.assertRaises(ValueError):service.start(ADMIN,ports=[8446])
            with self.assertRaises(PermissionError):service.status({**ADMIN,'username':'other'},data['capture_id'])
            self.assertEqual(service.status(ADMIN,data['capture_id'])['status'],'running')
