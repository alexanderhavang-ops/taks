import unittest
from takctl.web.mcp_domains import host_monitor,devops

class MonitorTests(unittest.TestCase):
    def test_invalid_bounds_and_boolean_samples(self):
        for args in ((0,20,'cpu'),(6,20,'cpu'),(True,20,'cpu'),(1,51,'cpu'),(1,20,'args')):
            with self.assertRaises(ValueError):host_monitor.sample_snapshot(*args)
        for count in (0,6,True):
            with self.assertRaises(ValueError):host_monitor.vmstat_samples(1,count)
        with self.assertRaises(ValueError):host_monitor.vmstat_samples(5,5)
    def test_live_sample_is_bounded_and_omits_sensitive_process_fields(self):
        data=host_monitor.sample_snapshot(.2,3)
        self.assertLessEqual(len(data['processes']),3)
        self.assertGreater(data['logical_cpus'],0)
        self.assertIn('busy_percent',data['cpu_percent_all_cores'])
        for row in data['processes']:
            self.assertFalse({'args','cmdline','environ','cwd'} & set(row))
        self.assertIn('swap_used_kib',host_monitor.memory_snapshot()['memory'])
    def test_node_exposes_fixed_read_tools(self):
        self.assertIn('memory_read',{t['name'] for t in devops.TOOLS})
        with self.assertRaises(ValueError):devops.call('process_sample',{'command':'id'})
        self.assertTrue(host_monitor.memory_snapshot()['ok'])
