"""Expand the local fictional demo, preserving data and backing up SQLite first.

Run from the project root: python -m community_mate.setup_demo
"""
from datetime import datetime, timezone
from contextlib import closing
import sqlite3

from community_mate import database as db


def main():
    if db.DB_PATH.exists():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = db.DB_PATH.with_name(f"community_mate.backup-catalog-{stamp}.db")
        with closing(sqlite3.connect(db.DB_PATH)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        print(f"Backup created: {backup.name}")
    db.initialize_database()
    db.seed_residents()
    db.seed_amenities()
    db.seed_amenity_slots()
    connection = db.get_connection()
    try:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        for table in ('amenities', 'residents', 'amenity_slots', 'reservations', 'maintenance_requests'):
            print(f"{table}: {connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]}")
    finally:
        connection.close()
    print('Demo catalog expanded. Existing reservations and tickets retained. No AWS calls.')


if __name__ == '__main__':
    main()
