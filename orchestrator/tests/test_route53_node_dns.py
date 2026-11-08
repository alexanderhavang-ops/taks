"""Route53 node and DevOps hostname records stay synchronized."""
import unittest
from unittest.mock import patch

from orchestrator_core import core


class TestNodeDNS(unittest.TestCase):
    @patch("orchestrator_core.core.boto3.client")
    def test_upsert_node_dns_changes_both_records_atomically(self, client):
        r53 = client.return_value
        r53.change_resource_record_sets.return_value = {
            "ChangeInfo": {"Id": "/change/C123", "Status": "PENDING"}}
        result = core._upsert_node_dns(
            zone_id="Z123", fqdn="47hvbat.aws.tak-hv-sandbox.se",
            public_ip="13.49.80.187")
        self.assertEqual(result["Id"], "/change/C123")
        kwargs = r53.change_resource_record_sets.call_args.kwargs
        changes = kwargs["ChangeBatch"]["Changes"]
        self.assertEqual(kwargs["HostedZoneId"], "Z123")
        self.assertEqual(len(changes), 2)
        self.assertEqual(
            [change["ResourceRecordSet"]["Name"] for change in changes],
            ["47hvbat.aws.tak-hv-sandbox.se",
             "devops.47hvbat.aws.tak-hv-sandbox.se"])
        for change in changes:
            self.assertEqual(change["Action"], "UPSERT")
            record = change["ResourceRecordSet"]
            self.assertEqual(record["Type"], "A")
            self.assertEqual(record["TTL"], 60)
            self.assertEqual(record["ResourceRecords"], [{"Value": "13.49.80.187"}])

    @patch("orchestrator_core.core._upsert_node_dns")
    @patch("orchestrator_core.core._route53_zone_id", return_value="Z123")
    def test_heartbeat_reconcile_reuses_two_record_upsert(self, zone, upsert):
        core.aws_reconcile_node_dns(
            fqdn="47hvbat.aws.tak-hv-sandbox.se",
            public_ip="13.49.80.187")
        upsert.assert_called_once_with(
            zone_id="Z123", fqdn="47hvbat.aws.tak-hv-sandbox.se",
            public_ip="13.49.80.187")


if __name__ == "__main__":
    unittest.main()
