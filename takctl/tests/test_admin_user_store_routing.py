import unittest
from unittest.mock import patch
from takctl.services import marti_user_mgmt as users


class AdminUserStoreRoutingTests(unittest.TestCase):
    def test_ldap_user_operations_never_create_parallel_file_users(self):
        with patch.object(users, 'selected_backing_user_store', return_value='ldap'), \
             patch.object(users, 'build_backing_user_store') as build, \
             patch.object(users, 'marti_request') as http:
            self.assertTrue(users.create_or_update_user(username='alex', password='PRIVATE')['ok'])
            self.assertTrue(users.change_user_password(username='alex', password='NEW')['ok'])
            self.assertEqual(build.return_value.ensure_user.call_args.kwargs,
                {'password': 'NEW', 'append': True})
            self.assertTrue(users.update_groups(username='alex', group_list=['Blue'])['ok'])
            self.assertTrue(users.delete_user(username='alex')['ok'])
            build.return_value.delete_user.assert_called_once_with('alex')
            http.assert_not_called()


if __name__ == '__main__': unittest.main()
