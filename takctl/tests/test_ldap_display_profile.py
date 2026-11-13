import base64,unittest
from types import SimpleNamespace
from unittest.mock import Mock
from takctl.services.ldap_user_store import LdapUserStore,LdapUserStoreError

class DisplayProfileTests(unittest.TestCase):
    def store(self,existing=True,rdn='uid'):
        s=object.__new__(LdapUserStore);s.config=SimpleNamespace(user_rdn_attr=rdn,user_dn=lambda u:'uid='+u+',dc=test')
        s.get_user=Mock(return_value={} if existing else None);s.groups_for_user=Mock(return_value=[])
        s._ldapmodify=Mock();s._ldapadd=Mock();s._set_password=Mock()
        return s
    def test_updates_names_with_base64_and_preserves_cn_rdn(self):
        s=self.store(rdn='cn');s.ensure_user('sim-01',ctx={'first_name':'Erik','last_name':'Lind'})
        ldif=s._ldapmodify.call_args.args[0]
        self.assertIn('replace: displayName',ldif);self.assertNotIn('replace: cn\n',ldif)
        self.assertIn(base64.b64encode(b'Erik Lind').decode(),ldif)
    def test_new_person_uses_names_without_changing_username(self):
        s=self.store(existing=False);s.ensure_user('sim-01',password='unused',ctx={'first_name':'Sara','last_name':'Holm'})
        ldif=s._ldapadd.call_args.args[0]
        self.assertIn('uid: sim-01',ldif);self.assertIn('cn:: ',ldif)
        self.assertNotIn('cn: sim-01',ldif)
    def test_rejects_injected_name_before_any_write(self):
        s=self.store()
        with self.assertRaises(LdapUserStoreError):s.ensure_user('sim-01',ctx={'first_name':'Name\nreplace: userPassword'})
        s._ldapmodify.assert_not_called();s._ldapadd.assert_not_called()
