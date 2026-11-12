from contextlib import ExitStack
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from orchestrator_api import api_v2 as api


class LifecycleApiTests(unittest.TestCase):
    def test_changed_instance_is_rejected_before_aws_termination(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(api, 'require_operator'))
            stack.enter_context(patch.object(api, 'get_node', return_value={'node_id': 'taklabs'}))
            stack.enter_context(patch.object(api, '_resolve_instance_for_node_record', return_value={'instance_id': 'i-new'}))
            terminate = stack.enter_context(patch.object(api, 'aws_terminate'))
            with self.assertRaises(HTTPException) as raised:
                api.nodes_terminate('taklabs', None, {'expected_instance_id': 'i-old'})
            self.assertEqual(raised.exception.status_code, 409)
            terminate.assert_not_called()

    def test_corrupt_backup_is_not_selected(self):
        with patch.object(api, 'require_operator'), patch.object(api, 'verify_unit_backup', side_effect=ValueError('corrupt')), patch.object(api, 'set_unit_restore_backup_selection') as select:
            with self.assertRaises(HTTPException) as raised:
                api.unit_backup_select_restore('taklabs', 'backup', None)
            self.assertEqual(raised.exception.status_code, 409)
            select.assert_not_called()

    def test_verified_backup_can_be_selected(self):
        with patch.object(api, 'require_operator'), patch.object(api, 'verify_unit_backup', return_value={'verified': True}), patch.object(api, 'set_unit_restore_backup_selection', return_value={'backup_id': 'backup'}):
            self.assertTrue(api.unit_backup_select_restore('taklabs', 'backup', None)['ok'])
