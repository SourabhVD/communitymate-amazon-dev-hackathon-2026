"""Catalog migrations and business rules against disposable databases."""
from pathlib import Path
from contextlib import closing
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from community_mate import database as db


class CommunityCatalogTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "catalog.db"
        patcher = patch.object(db, "DB_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def seed(self):
        db.initialize_database()
        db.seed_residents()
        db.seed_amenities()
        db.seed_amenity_slots()

    def test_legacy_schema_migration_preserves_values_and_is_repeatable(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE amenities (amenity_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    max_booking_hours INTEGER NOT NULL DEFAULT 4);
                CREATE TABLE residents (resident_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    unit_number TEXT NOT NULL, account_status TEXT NOT NULL);
                INSERT INTO amenities VALUES ('CLB001','Existing custom name',2);
                INSERT INTO residents VALUES ('RES001','Existing resident','A199','active');
            """)
        self.seed()
        booked = db.reserve_amenity('RES001', 'CLB001', '2026-10-23', '17:00', 2, 'migration')
        self.seed()
        self.assertEqual(db.get_amenity('CLB001')['name'], 'Existing custom name')
        self.assertEqual(db.get_amenity('CLB001')['max_booking_hours'], 2)
        self.assertEqual(db.get_resident('RES001')['unit_number'], 'A199')
        self.assertEqual(db.get_reservation_details(booked['reservation_id'], 'RES001'), booked)
        with closing(db.get_connection()) as connection, connection:
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(connection.execute('SELECT count(*) FROM amenity_slots').fetchone()[0], 196)

    def test_walk_in_and_information_only_reject_booking_even_with_stray_slots(self):
        self.seed()
        gym = next(item for item in db.get_amenities() if item['amenity_id'] == 'GYM001')
        self.assertIsNone(gym['max_booking_hours'])
        self.assertIsNone(gym['booking_limit_hours'])
        self.assertEqual(gym['timezone'], 'America/Chicago')
        with closing(db.get_connection()) as connection, connection:
            for aid in ('POOL001', 'EV001'):
                connection.execute('INSERT INTO amenity_slots (amenity_id,slot_date,start_time,end_time) VALUES (?,?,?,?)',
                                   (aid, '2026-10-23', '17:00', '18:00'))
        for aid in ('POOL001', 'EV001'):
            with self.subTest(aid=aid):
                with self.assertRaisesRegex(ValueError, 'does not accept reservations'):
                    db.get_available_windows(aid, '2026-10-23', 1)
                with self.assertRaisesRegex(ValueError, 'does not accept reservations'):
                    db.reserve_amenity('RES001', aid, '2026-10-23', '17:00', 1, aid)

    def test_closure_and_hours_are_enforced_at_read_and_write(self):
        self.seed()
        for assignments, error in (("operational_status='maintenance'", 'closed or under maintenance'),
                                   ("operational_status='open',closing_time='18:00'", 'outside amenity operating hours')):
            with closing(db.get_connection()) as connection, connection:
                connection.execute(f"UPDATE amenities SET {assignments} WHERE amenity_id='MEET301'")
            if 'maintenance' in assignments:
                with self.assertRaisesRegex(ValueError, error):
                    db.get_available_windows('MEET301', '2026-10-23', 2)
            else:
                self.assertEqual(db.get_available_windows('MEET301', '2026-10-23', 2), [])
            with self.assertRaisesRegex(ValueError, error):
                db.reserve_amenity('RES001', 'MEET301', '2026-10-23', '17:00', 2, 'closed')

    def test_new_space_booking_and_profile_preferences_survive_reseed(self):
        self.seed()
        booked = db.reserve_amenity('RES001', 'STDY001', '2026-10-24', '18:00', 1, 'study')
        self.assertEqual(booked['slots'][0]['amenity_name'], 'Study Room 1')
        with closing(db.get_connection()) as connection, connection:
            connection.execute("UPDATE residents SET preferred_name='Al',notification_preference='none' WHERE resident_id='RES001'")
        self.seed()
        self.assertEqual(db.get_resident('RES001')['preferred_name'], 'Al')
        self.assertEqual(db.get_resident('RES001')['notification_preference'], 'none')


if __name__ == '__main__':
    unittest.main()
