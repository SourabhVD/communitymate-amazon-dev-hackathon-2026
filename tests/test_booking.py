"""Booking integration checks using disposable SQLite databases."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from community_mate import database as db


class BookingTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path_patch = patch.object(db, "DB_PATH", Path(self.folder.name) / "test.db")
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        db.initialize_database()
        db.seed_residents()
        db.seed_amenities()
        db.seed_amenity_slots()

    def book(self, request_id="test-1", resident="RES001", start="17:00", hours=2):
        return db.reserve_amenity(resident, "CLB001", "2026-10-23", start, hours, request_id)

    def counts(self):
        connection = db.get_connection()
        try:
            return tuple(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                         for table in ("reservations", "reservation_slots", "booking_requests"))
        finally:
            connection.close()

    def test_persistence_retry_and_ownership(self):
        result = self.book()
        self.assertEqual(len(result["slots"]), 2)
        self.assertEqual(result, self.book())
        self.assertEqual(self.counts(), (1, 2, 1))
        self.assertEqual(db.get_reservation_details(result["reservation_id"], "RES001"), result)
        self.assertIsNone(db.get_reservation_details(result["reservation_id"], "RES002"))
        self.assertEqual([s["start_time"] for s in
                          db.get_available_slots("CLB001", "2026-10-23")], ["19:00", "20:00"])

    def test_changed_retry_and_competing_booking(self):
        self.book()
        with self.assertRaisesRegex(ValueError, "different booking details"):
            self.book(start="19:00")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.book("other", "RES002", "18:00", 2)
        self.assertEqual(self.counts(), (1, 2, 1))

    def test_ineligible_and_invalid_inputs(self):
        for args in ({"resident": "RES003"}, {"resident": "UNKNOWN"},
                     {"start": "17:30"}, {"hours": True}, {"hours": 5},
                     {"request_id": " "}, {"start": "20:00"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.book(**args)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_amenity_limit_and_malformed_slot(self):
        connection = db.get_connection()
        try:
            connection.execute("UPDATE amenities SET max_booking_hours = 1 WHERE amenity_id = 'CLB001'")
            connection.commit()
            with self.assertRaisesRegex(ValueError, "up to 1"):
                self.book()
            connection.execute("UPDATE amenities SET max_booking_hours = 4 WHERE amenity_id = 'CLB001'")
            connection.execute("UPDATE amenity_slots SET end_time = '18:30' WHERE start_time = '17:00'")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.book()
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_failure_after_slot_writes_rolls_back_everything(self):
        connection = db.get_connection()
        try:
            connection.execute("""
                CREATE TRIGGER fail_request BEFORE INSERT ON booking_requests
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END
            """)
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected failure"):
            self.book()
        self.assertEqual(self.counts(), (0, 0, 0))
        connection = db.get_connection()
        try:
            self.assertEqual(connection.execute("SELECT count(*) FROM active_slot_claims").fetchone()[0], 0)
        finally:
            connection.close()

    def test_cancel_preserves_history_frees_slots_and_allows_rebooking(self):
        booking = self.book()
        with self.assertRaisesRegex(ValueError, "not found"):
            db.cancel_amenity_reservation("RES002", booking["reservation_id"])
        self.assertEqual(len(db.get_available_slots("CLB001", "2026-10-23")), 2)
        cancelled = db.cancel_amenity_reservation("RES001", booking["reservation_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["slots"], booking["slots"])
        self.assertEqual(len(db.get_available_slots("CLB001", "2026-10-23")), 4)
        replacement = self.book("replacement", "RES002")
        self.assertNotEqual(replacement["reservation_id"], booking["reservation_id"])
        # A retry of the OLD booking must not recreate it after cancellation.
        self.assertEqual(self.book()["status"], "cancelled")
        db.cancel_amenity_reservation("RES001", booking["reservation_id"])
        self.assertEqual(len(db.get_available_slots("CLB001", "2026-10-23")), 2)
        db.initialize_database()
        self.assertEqual(db.get_reservation_details(booking["reservation_id"], "RES001"), cancelled)

    def test_cancellation_failure_rolls_back_status_and_claims(self):
        booking = self.book()
        connection = db.get_connection()
        try:
            connection.execute("""
                CREATE TRIGGER fail_release BEFORE DELETE ON active_slot_claims
                BEGIN SELECT RAISE(ABORT, 'injected release failure'); END
            """)
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(sqlite3.IntegrityError, "release failure"):
            db.cancel_amenity_reservation("RES001", booking["reservation_id"])
        self.assertEqual(db.get_reservation_details(booking["reservation_id"], "RES001")["status"], "confirmed")
        self.assertEqual(len(db.get_available_slots("CLB001", "2026-10-23")), 2)

    def test_legacy_migration_preserves_booking_and_retries(self):
        booking = self.book()
        connection = db.get_connection()
        try:
            connection.execute("DROP TABLE active_slot_claims")
            connection.execute("CREATE UNIQUE INDEX legacy_unique_slot ON reservation_slots(slot_id)")
            connection.commit()
        finally:
            connection.close()
        db.initialize_database()
        db.initialize_database()
        self.assertEqual(self.book(), booking)
        self.assertEqual(len(db.get_available_slots("CLB001", "2026-10-23")), 2)
        cancelled = db.cancel_amenity_reservation("RES001", booking["reservation_id"])
        self.assertEqual(cancelled["slots"], booking["slots"])
        self.book("replacement", "RES002")

    def test_simultaneous_conflicts_and_retries(self):
        def run_pair(same_request):
            barrier = Barrier(2)

            def attempt(index):
                barrier.wait()
                try:
                    return self.book("shared" if same_request else f"race-{index}",
                                     start="19:00" if same_request else "17:00")
                except ValueError as error:
                    return error

            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(attempt, range(2)))

        competing = run_pair(False)
        self.assertEqual(sum(isinstance(result, dict) for result in competing), 1)
        self.assertEqual(self.counts(), (1, 2, 1))
        retried = run_pair(True)
        self.assertTrue(all(isinstance(result, dict) for result in retried))
        self.assertEqual(retried[0]["reservation_id"], retried[1]["reservation_id"])
        self.assertEqual(self.counts(), (2, 4, 2))


if __name__ == "__main__":
    unittest.main()
