"""Discovery, current resource reads, and side-effect-free prompt retrieval."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from community_mate import database as db
from community_mate.knowledge import DOCUMENT_FILENAMES, KNOWLEDGE_DIR
from community_mate.server import mcp


class ResourcesAndPromptsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.object(db, "DB_PATH", Path(folder.name) / "resources.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        db.initialize_database()
        db.seed_residents()
        db.seed_amenities()

    async def read(self, uri):
        return list(await mcp.read_resource(uri))[0].content

    async def test_discovery_and_removed_tools(self):
        resources = await mcp.list_resources()
        self.assertEqual(len(resources), 5 + len(DOCUMENT_FILENAMES))
        names = {tool.name for tool in await mcp.list_tools()}
        self.assertTrue({"get_community_info", "get_community_fact", "get_community_announcements"}.isdisjoint(names))
        self.assertTrue({"list_amenities", "search_community_knowledge", "reserve_amenity", "create_maintenance_request"} <= names)

    async def test_each_document_resource_has_correct_content(self):
        for filename in DOCUMENT_FILENAMES:
            with self.subTest(filename=filename):
                text = await self.read(f"community://maple-grove/documents/{Path(filename).stem}")
                self.assertEqual(text, (KNOWLEDGE_DIR / filename).read_text(encoding="utf-8"))

    async def test_info_uses_current_catalog_instead_of_stale_constants(self):
        info = json.loads(await self.read("community://maple-grove/info"))
        self.assertTrue({"CLB001", "MEET301", "POOL001", "GYM001", "STDY001"} <=
                        {row["amenity_id"] for row in info["amenities"]})
        self.assertEqual(info["property_details"]["timezone"], "America/Chicago")
        self.assertEqual(info["property"], "Maple Grove Apartments")
        self.assertEqual(len(info["handbook_facts"]), 2)

    async def test_profile_is_current_resident_only_and_directory_is_public(self):
        profile = json.loads(await self.read("community://maple-grove/resident/profile"))
        self.assertEqual(profile["resident"]["resident_id"], "RES001")
        self.assertEqual(profile["resident"]["unit_number"], "A101")
        self.assertEqual(profile["resident"]["building"], "A")
        self.assertNotIn("RES002", json.dumps(profile))
        directory = json.loads(await self.read("community://maple-grove/directory"))
        self.assertEqual(directory["timezone"], "America/Chicago")
        self.assertNotIn("residents", directory)

    async def test_announcements_resource_reads_live_database(self):
        uri = "community://maple-grove/announcements"
        self.assertEqual(json.loads(await self.read(uri))["announcements"], [])
        connection = db.get_connection()
        try:
            connection.execute("""
                INSERT INTO community_announcements
                (announcement_id, title, message, category, published_at, expires_at)
                VALUES ('TEST', 'Test', 'Current test notice', 'event',
                        datetime('now', '-1 hour'), datetime('now', '+1 hour'))
            """)
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(json.loads(await self.read(uri))["announcements"][0]["announcement_id"], "TEST")

    async def test_prompt_retrieval_produces_guidance_without_writes(self):
        prompts = await mcp.list_prompts()
        self.assertEqual({p.name for p in prompts}, {
            "book_amenity", "report_maintenance", "resident_daily_brief", "review_renewal",
        })
        for prompt in prompts:
            result = await mcp.get_prompt(prompt.name)
            self.assertTrue(result.messages)
            self.assertEqual(result.messages[0].role, "user")
        booking = await mcp.get_prompt("book_amenity", {"request": "Clubhouse for two hours"})
        self.assertIn("Clubhouse for two hours", booking.messages[0].content.text)
        self.assertIn("confirmation", booking.messages[0].content.text)
        connection = db.get_connection()
        try:
            for table in ("reservations", "maintenance_requests", "demo_payments", "service_actions"):
                self.assertEqual(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
