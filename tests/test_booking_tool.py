"""Exercise MCP dispatch against a disposable database, not the HTTP layer."""

from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from community_mate import database as db
from community_mate.server import mcp


class BookingToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmation_booking_retry_and_status(self):
        with TemporaryDirectory() as folder:
            with patch.object(db, "DB_PATH", Path(folder) / "test.db"):
                db.initialize_database()
                db.seed_residents()
                db.seed_amenities()
                db.seed_amenity_slots()
                arguments = dict(amenity_id="CLB001", date="2026-10-23",
                                 start_time="17:00", duration_hours=2,
                                 request_id="tool-test-1")
                # SDK direct dispatch raises ToolError; the HTTP handler
                # serializes it for Inspector.
                from mcp.server.mcpserver.exceptions import ToolError
                with self.assertRaisesRegex(ToolError, "Confirm the exact"):
                    await mcp.call_tool("reserve_amenity", arguments)
                connection = db.get_connection()
                try:
                    self.assertEqual(connection.execute(
                        "SELECT count(*) FROM reservations"
                    ).fetchone()[0], 0)
                finally:
                    connection.close()

                arguments["confirmed"] = True
                created = await mcp.call_tool("reserve_amenity", arguments)
                self.assertFalse(created.is_error)
                # A generic dict annotation may serialize as JSON text rather
                # than structured_content in this installed SDK.
                def payload(result):
                    return (result.structured_content if result.structured_content is not None
                            else json.loads(result.content[0].text))

                booking = payload(created)
                self.assertEqual(booking["resident_id"], "RES001")
                self.assertEqual(len(booking["slots"]), 2)
                retried = await mcp.call_tool("reserve_amenity", arguments)
                self.assertEqual(payload(retried), booking)
                status = await mcp.call_tool("get_reservation_status", {
                    "reservation_id": booking["reservation_id"],
                })
                self.assertEqual(payload(status), booking)
                with self.assertRaisesRegex(ToolError, "Confirm cancellation"):
                    await mcp.call_tool("cancel_amenity_reservation", {
                        "reservation_id": booking["reservation_id"],
                    })
                cancelled = await mcp.call_tool("cancel_amenity_reservation", {
                    "reservation_id": booking["reservation_id"], "confirmed": True,
                })
                self.assertEqual(payload(cancelled)["status"], "cancelled")
                self.assertEqual(payload(cancelled)["slots"], booking["slots"])


if __name__ == "__main__":
    unittest.main()
