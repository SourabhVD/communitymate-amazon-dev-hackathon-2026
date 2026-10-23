"""Integration tests for fictional resident services; no external side effects."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from community_mate import database as db
from community_mate import resident_services as services
from community_mate.knowledge import search_policy
from community_mate.server import mcp
from mcp.server.mcpserver.exceptions import ToolError


class ResidentServicesTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.object(db, "DB_PATH", Path(folder.name) / "services.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        db.initialize_database()
        db.seed_residents()
        services.seed_resident_services()


    def test_package_ownership_and_assistance_retries(self):
        self.assertEqual(len(services.list_packages("RES001")), 1)
        self.assertEqual(services.get_package_status("RES001", "PKG001")["status"], "ready_for_pickup")
        with self.assertRaisesRegex(ValueError, "not found"):
            services.get_package_status("RES001", "PKG003")
        created = services.request_package_assistance("RES001", "PKG001", "Not at desk", "help-1")
        self.assertEqual(created, services.request_package_assistance("RES001", "PKG001", "Not at desk", "help-1"))
        self.assertEqual(services.get_package_assistance_status("RES001", created["assistance_id"])["status"], "received")
        with self.assertRaises(ValueError):
            services.get_package_assistance_status("RES002", created["assistance_id"])
        with self.assertRaises(ValueError):
            services.request_package_assistance("RES001", "PKG003", "Missing", "help-2")






    def test_announcements_filter_future_and_expired(self):
        connection = db.get_connection()
        try:
            connection.execute("UPDATE community_announcements SET published_at = datetime('now', '-1 day'), expires_at = datetime('now', '+1 day')")
            connection.execute("UPDATE community_announcements SET expires_at = datetime('now', '-1 hour') WHERE announcement_id = 'ANN001'")
            connection.execute("UPDATE community_announcements SET published_at = datetime('now', '+1 hour') WHERE announcement_id = 'ANN002'")
            connection.commit()
        finally:
            connection.close()
        result = services.get_community_announcements("RES001")
        self.assertEqual([row["announcement_id"] for row in result["announcements"]], ["ANN003"])

    def test_document_retrieval(self):
        for query in ("concierge package pickup", "rent payment information", "lease renewal offers"):
            self.assertEqual(search_policy(query, 1)[0]["source"], "resident_services_guide.md")

    def test_payment_information_is_read_only(self):
        connection = db.get_connection()
        try:
            # Historical receipt fixture, not an application payment action.
            connection.execute("""INSERT INTO demo_payments
                (resident_id, charge_id, method_id, amount_cents)
                VALUES ('RES001', 'RENT001', 'DEMO_ACH_001', 10000)""")
            connection.commit()
        finally:
            connection.close()
        before = services.get_rent_account("RES001")
        self.assertEqual(before["charges"][0]["balance_cents"], 140000)
        self.assertEqual(len(before["payments"]), 1)
        self.assertEqual(before, services.get_rent_account("RES001"))
        self.assertEqual(services.get_demo_autopay("RES001")["configuration"], None)
        self.assertEqual(services.get_rent_account("RES002")["payments"], [])
        for name in ("make_demo_rent_payment", "configure_demo_autopay", "simulate_due_autopay"):
            self.assertFalse(hasattr(services, name))

    def test_mcp_payment_actions_absent_and_other_confirmations_retained(self):
        async def exercise():
            names = {tool.name for tool in await mcp.list_tools()}
            self.assertTrue({"get_rent_account", "get_package_status", "get_lease_renewal_offers"} <= names)
            removed = {"make_demo_rent_payment", "configure_demo_autopay", "simulate_due_autopay",
                       "accept_demo_lease_renewal", "accept_demo_lease_approval"}
            self.assertTrue(removed.isdisjoint(names))
            for name in removed:
                with self.assertRaisesRegex(ToolError, "Unknown tool"):
                    await mcp.call_tool(name, {})
            calls = [
                ("request_package_assistance", dict(package_id="PKG001", issue="Missing", request_id="mcp-help")),
            ]
            for name, args in calls:
                with self.subTest(tool=name), self.assertRaisesRegex(ToolError, "Confirm the exact"):
                    await mcp.call_tool(name, args)
            result = await mcp.call_tool("get_rent_account", {})
            payload = result.structured_content or json.loads(result.content[0].text)
            self.assertEqual(payload["charges"][0]["balance_cents"], 150000)
            self.assertTrue(payload["simulation"])
        asyncio.run(exercise())

    def test_renewals_read_only_and_resident_scoped(self):
        before = services.get_lease_renewal_offers("RES001")
        self.assertEqual(before["offers"][0]["offer_id"], "LEASE001")
        self.assertEqual(before, services.get_lease_renewal_offers("RES001"))
        self.assertEqual(services.get_lease_renewal_offers("RES002")["offers"], [])
        self.assertFalse(hasattr(services, "accept_demo_lease_renewal"))

    def test_unreceived_packages_are_not_exposed_or_assisted(self):
        connection = db.get_connection()
        try:
            # Legacy expected record must not be exposed as carrier tracking.
            connection.execute("""INSERT INTO packages VALUES
                ('PKG002', 'RES001', 'Demo carrier', 'OLD-TRACK', 'expected', NULL, NULL, NULL)""")
            connection.commit()
        finally:
            connection.close()
        packages = services.list_packages("RES001")
        self.assertEqual([item["package_id"] for item in packages], ["PKG001"])
        self.assertNotIn("tracking_reference", packages[0])
        for operation in (
            lambda: services.get_package_status("RES001", "PKG002"),
            lambda: services.request_package_assistance("RES001", "PKG002", "Where is it?", "unreceived"),
        ):
            with self.assertRaisesRegex(ValueError, "Check shipment progress with the carrier"):
                operation()


if __name__ == "__main__":
    unittest.main()
