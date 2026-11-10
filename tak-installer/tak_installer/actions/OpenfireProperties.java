import java.io.DataInputStream;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;

/** Offline Openfire property update. Values arrive on stdin, never argv/logs. */
class OpenfireProperties {
    static String readString(DataInputStream input) throws Exception {
        int length = input.readInt();
        if (length < 0 || length > 65536) throw new IllegalArgumentException("Invalid property length");
        byte[] bytes = input.readNBytes(length);
        if (bytes.length != length) throw new IllegalArgumentException("Truncated property input");
        return new String(bytes, StandardCharsets.UTF_8);
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Database path required");
        Class.forName("org.hsqldb.jdbc.JDBCDriver");
        try (Connection connection = DriverManager.getConnection("jdbc:hsqldb:file:" + args[0] + ";ifexists=true", "sa", "")) {
            connection.setAutoCommit(false);
            DataInputStream input = new DataInputStream(System.in);
            int count = input.readInt();
            if (count < 1 || count > 100) throw new IllegalArgumentException("Invalid property count");
            try (PreparedStatement delete = connection.prepareStatement("DELETE FROM ofProperty WHERE name=?");
                 PreparedStatement insert = connection.prepareStatement("INSERT INTO ofProperty(name,propValue,encrypted,iv) VALUES(?,?,0,NULL)")) {
                for (int i = 0; i < count; i++) {
                    String name = readString(input), value = readString(input);
                    delete.setString(1, name); delete.executeUpdate();
                    insert.setString(1, name); insert.setString(2, value); insert.executeUpdate();
                }
            }
            connection.commit();
            connection.createStatement().execute("SHUTDOWN");
            System.out.println("Updated Openfire properties: " + count);
        }
    }
}
