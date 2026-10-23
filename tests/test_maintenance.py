"""Maintenance persistence, retry, access, and MCP contract checks."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from community_mate import database as db
from community_mate.knowledge import search_policy
from community_mate.server import mcp
from mcp.server.mcpserver.exceptions import ToolError


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path_patch = patch.object(db, "DB_PATH", Path(folder.name) / "test.db")
        path_patch.start()
        self.addCleanup(path_patch.stop)
        db.initialize_database()
        db.seed_residents()

    def create(self, **changes):
        args = dict(resident_id="RES001", category="hvac", location="Bedroom",
                    description="AC runs but does not cool", entry_permission="ask_first",
                    request_id="maintenance-test", preferred_visit_times="Friday after 3 PM")
        args.update(changes)
        return db.create_maintenance_request(**args)

    def count(self):
        connection = db.get_connection()
        try:
            return connection.execute("SELECT count(*) FROM maintenance_requests").fetchone()[0]
        finally:
            connection.close()

    def test_saved_ticket_retry_and_resident_access(self):
        ticket = self.create()
        self.assertEqual(ticket["status"], "received")
        self.assertIsNone(ticket["assigned_technician"])
        self.assertIsNone(ticket["scheduled_at"])
        self.assertEqual(ticket, self.create())
        self.assertEqual(self.count(), 1)
        self.assertEqual(db.get_maintenance_status(ticket["ticket_id"], "RES001"), ticket)
        self.assertIsNone(db.get_maintenance_status(ticket["ticket_id"], "RES002"))
        self.assertIsNone(db.get_maintenance_status(999, "RES001"))
        # Identical text with a NEW request ID represents a separate intent.
        self.create(resident_id="RES002")
        self.assertEqual(self.count(), 2)

    def test_changed_retry_rejected(self):
        self.create()
        with self.assertRaisesRegex(ValueError, "different maintenance details"):
            self.create(entry_permission="yes")
        self.assertEqual(self.count(), 1)

    def test_validation_creates_nothing(self):
        for change in (dict(resident_id="UNKNOWN"), dict(resident_id="RES003"),
                       dict(category="invalid"), dict(location=" "),
                       dict(description=""), dict(description="x" * 2001),
                       dict(entry_permission="maybe"), dict(request_id=""),
                       dict(preferred_visit_times=None), dict(reported_priority="urgent")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.create(**change)
        for invalid in (0, -1, True, "1"):
            with self.assertRaises(ValueError):
                db.get_maintenance_status(invalid, "RES001")
        self.assertEqual(self.count(), 0)

    def test_failure_rolls_back_insert(self):
        connection = db.get_connection()
        try:
            connection.execute("""
                CREATE TRIGGER fail_maintenance AFTER INSERT ON maintenance_requests
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END
            """)
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected failure"):
            self.create()
        self.assertEqual(self.count(), 0)

    def test_simultaneous_retries_create_one_ticket(self):
        barrier = Barrier(2)
        def attempt(_):
            barrier.wait()
            return self.create()
        with ThreadPoolExecutor(max_workers=2) as pool:
            tickets = list(pool.map(attempt, range(2)))
        self.assertEqual(tickets[0], tickets[1])
        self.assertEqual(self.count(), 1)

    def test_status_reads_real_updates_and_retries_preserve_them(self):
        ticket = self.create()
        connection = db.get_connection()
        try:
            # Simulates staff/backend activity; no resident tool can do this.
            connection.execute("""
                UPDATE maintenance_requests
                SET status = 'scheduled', assigned_technician = 'Demo technician',
                    scheduled_at = '2026-10-23T15:00:00-07:00', updated_at = CURRENT_TIMESTAMP
                WHERE ticket_id = ?
            """, (ticket["ticket_id"],))
            connection.commit()
        finally:
            connection.close()
        updated = db.get_maintenance_status(ticket["ticket_id"], "RES001")
        self.assertEqual(updated["status"], "scheduled")
        self.assertEqual(updated["assigned_technician"], "Demo technician")
        self.assertEqual(self.create(), updated)

    def test_mcp_confirmation_creation_status_and_errors(self):
        def payload(result):
            return (result.structured_content if result.structured_content is not None
                    else json.loads(result.content[0].text))

        async def exercise():
            arguments = dict(category="plumbing", location="Kitchen sink",
                             description="Faucet drips", entry_permission="no",
                             request_id="mcp-maintenance")
            with self.assertRaisesRegex(ToolError, "Confirm the maintenance"):
                await mcp.call_tool("create_maintenance_request", arguments)
            self.assertEqual(self.count(), 0)
            arguments["confirmed"] = True
            created = await mcp.call_tool("create_maintenance_request", arguments)
            self.assertFalse(created.is_error)
            ticket = payload(created)
            self.assertEqual(ticket["resident_id"], "RES001")
            self.assertEqual(ticket["status"], "received")
            self.assertEqual(payload(await mcp.call_tool(
                "get_maintenance_status", {"ticket_id": ticket["ticket_id"]})), ticket)
            self.assertEqual(payload(await mcp.call_tool("create_maintenance_request", arguments)), ticket)
            with self.assertRaisesRegex(ToolError, "not found"):
                await mcp.call_tool("get_maintenance_status", {"ticket_id": 999})
            arguments["entry_permission"] = "maybe"
            with self.assertRaises(ToolError):
                await mcp.call_tool("create_maintenance_request", arguments)

        asyncio.run(exercise())

    def test_guide_retrieval(self):
        for query in ("submission confirmation retries", "maintenance status definitions",
                      "preferred visit times reported priority"):
            result = search_policy(query, limit=1)
            self.assertEqual(result[0]["source"], "maintenance_guide.md")


if __name__ == "__main__":
    unittest.main()
