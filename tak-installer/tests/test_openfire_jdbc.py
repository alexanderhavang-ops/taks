"""Real HSQLDB replay test for the deployed JDBC property writer."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).parents[1] / 'tak_installer/actions/OpenfireProperties.java'
JAR = Path(os.environ.get('TAKS_TEST_HSQL_JAR', '/nonexistent'))
FIXTURE = '''import java.sql.*;
class Fixture {
 public static void main(String[] args) throws Exception {
  Class.forName("org.hsqldb.jdbc.JDBCDriver");
  try(Connection c=DriverManager.getConnection("jdbc:hsqldb:file:"+args[0],"sa","")) {
   Statement s=c.createStatement();
   if(args[1].equals("init")) {
    s.execute("CREATE TABLE ofProperty(name VARCHAR(100) PRIMARY KEY,propValue LONGVARCHAR,encrypted INTEGER,iv VARCHAR(100))");
    s.execute("CREATE TABLE preserved(id INTEGER)");
    s.execute("INSERT INTO preserved VALUES(7)");
    s.execute("INSERT INTO ofProperty VALUES('unmanaged','keep',0,NULL)");
   } else {
    ResultSet r=s.executeQuery("SELECT COUNT(*) FROM ofProperty");r.next();if(r.getInt(1)!=3)throw new Exception("Property count changed");
    r=s.executeQuery("SELECT propValue FROM ofProperty WHERE name='unmanaged'");r.next();if(!r.getString(1).equals("keep"))throw new Exception("Unmanaged row changed");
    r=s.executeQuery("SELECT id FROM preserved");r.next();if(r.getInt(1)!=7)throw new Exception("Unrelated data changed");
   }
   s.execute("SHUTDOWN");
  }
 }
}'''


@unittest.skipUnless(JAR.is_file(), 'set TAKS_TEST_HSQL_JAR to the installed HSQLDB 2.7.4 jar')
class OpenfireJdbcTests(unittest.TestCase):
    def test_real_database_reopens_after_repeated_property_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / 'Fixture.java'
            fixture.write_text(FIXTURE)
            database = str(root / 'openfire')
            def java(source, *args, data=None):
                return subprocess.run(['java', '--class-path', str(JAR), str(source), *args],
                                      input=data, capture_output=True, check=True, timeout=40)
            java(fixture, database, 'init')
            props = {'provider.auth.className':'org.jivesoftware.openfire.ldap.LdapAuthProvider',
                     'ldap.adminPassword':"synthetic ' quote \\ and Unicode ö"}
            data = struct.pack('>I', len(props))
            for key, value in props.items():
                for text in (key, value):
                    encoded = text.encode();data += struct.pack('>I',len(encoded))+encoded
            java(SOURCE, database, data=data)
            java(fixture, database, 'verify')
            java(SOURCE, database, data=data)
            java(fixture, database, 'verify')


if __name__ == '__main__': unittest.main()
