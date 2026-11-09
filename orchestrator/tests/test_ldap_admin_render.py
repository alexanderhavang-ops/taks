import os
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET


class LdapAdminRenderTests(unittest.TestCase):
    def test_admin_group_is_rendered_with_ldap_auth(self):
        source = (Path(__file__).resolve().parents[1] / 'orchestrator_core/default_bundle/install/tak-coreconfig-render.sh').read_text()
        function = source[source.index('render_auth_block() {'):source.index('\nextract_db_password()')]
        for group in ['TAKS_ADMIN', 'CustomAdmins']:
            script = '''cfg_value() { case "$1" in backing_user_store) printf ldap;; ldap_admin_group) printf '%s' "$TEST_ADMIN_GROUP";; *) printf '%s' "$2";; esac; }
secret_value() { printf dummy; }
xml_attr() { printf '%s' "$1"; }
die() { exit 1; }
''' + function + '\nrender_auth_block\n'
            result = subprocess.run(['bash'], input=script, text=True, capture_output=True,
                env={**os.environ, 'TEST_ADMIN_GROUP': group}, check=True)
            root = ET.fromstring(result.stdout)
            self.assertEqual(root.attrib['default'], 'ldap')
            self.assertEqual(root.find('ldap').attrib['adminGroup'], group)


if __name__ == '__main__': unittest.main()
