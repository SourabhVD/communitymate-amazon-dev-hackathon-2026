from pathlib import Path
import sqlite3
from datetime import date as Date
from datetime import datetime, timedelta

DB_PATH = Path(__file__).resolve().parent / "community_mate.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def initialize_database():
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS amenities (
                amenity_id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                max_booking_hours INTEGER NOT NULL DEFAULT 4
                    CHECK(max_booking_hours BETWEEN 1 AND 4)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS amenity_slots (
                slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                amenity_id TEXT NOT NULL,
                slot_date DATE NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                FOREIGN KEY (amenity_id) REFERENCES amenities (amenity_id),
                UNIQUE (amenity_id, slot_date, start_time)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS residents (
                resident_id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                unit_number TEXT NOT NULL,
                account_status TEXT NOT NULL 
                    CHECK(account_status IN ('active', 'inactive'))
            )
        """)

        connection.execute("""
                CREATE TABLE IF NOT EXISTS reservations(
                    reservation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resident_id TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN ('confirmed', 'cancelled')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (resident_id) REFERENCES residents (resident_id)
                )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS reservation_slots (
                reservation_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL,
                PRIMARY KEY (reservation_id, slot_id),
                FOREIGN KEY (reservation_id) REFERENCES reservations (reservation_id),
                FOREIGN KEY (slot_id) REFERENCES amenity_slots (slot_id)
            )
        """)

        _migrate_slot_claims(connection)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS booking_requests (
                resident_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                amenity_id TEXT NOT NULL,
                slot_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                duration_hours INTEGER NOT NULL
                    CHECK (duration_hours BETWEEN 1 AND 4),
                reservation_id INTEGER NOT NULL,
                PRIMARY KEY (resident_id, request_id),
                FOREIGN KEY (resident_id)
                    REFERENCES residents (resident_id),
                FOREIGN KEY (amenity_id)
                    REFERENCES amenities (amenity_id),
                FOREIGN KEY (reservation_id)
                    REFERENCES reservations (reservation_id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_requests (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                resident_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                category TEXT NOT NULL
                    CHECK (category IN ('plumbing', 'electrical', 'hvac', 'appliance', 'general')),
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                entry_permission TEXT NOT NULL
                    CHECK (entry_permission IN ('yes', 'no', 'ask_first')),
                preferred_visit_times TEXT NOT NULL DEFAULT '',
                reported_priority TEXT NOT NULL DEFAULT 'normal'
                    CHECK (reported_priority IN ('normal', 'high')),
                status TEXT NOT NULL DEFAULT 'received'
                    CHECK (status IN ('received', 'assigned', 'scheduled', 'in_progress', 'completed')),
                assigned_technician TEXT,
                scheduled_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (resident_id) REFERENCES residents(resident_id),
                UNIQUE (resident_id, request_id)
            )
        """)
        from community_mate.resident_services import initialize_services
        initialize_services(connection)
        from community_mate.community_catalog import migrate_catalog
        migrate_catalog(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _migrate_slot_claims(connection):
    """Preserve legacy slot links while moving exclusivity to active claims.

    The caller owns a transaction, so rebuilding the table and copying claims
    either complete together or leave the original schema/data intact.
    """
    legacy_unique_slot = False
    for index in connection.execute("PRAGMA index_list(reservation_slots)").fetchall():
        columns = [row["name"] for row in connection.execute(
            "SELECT name FROM pragma_index_info(?)", (index["name"],)
        ).fetchall()]
        if index["unique"] and columns == ["slot_id"]:
            legacy_unique_slot = True

    if legacy_unique_slot:
        connection.execute("""
            CREATE TABLE reservation_slots_history (
                reservation_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL,
                PRIMARY KEY (reservation_id, slot_id),
                FOREIGN KEY (reservation_id) REFERENCES reservations(reservation_id),
                FOREIGN KEY (slot_id) REFERENCES amenity_slots(slot_id)
            )
        """)
        connection.execute("""
            INSERT INTO reservation_slots_history (reservation_id, slot_id)
            SELECT reservation_id, slot_id FROM reservation_slots
        """)
        connection.execute("DROP TABLE reservation_slots")
        connection.execute("ALTER TABLE reservation_slots_history RENAME TO reservation_slots")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS active_slot_claims (
            slot_id INTEGER PRIMARY KEY,
            reservation_id INTEGER NOT NULL,
            FOREIGN KEY (reservation_id, slot_id)
                REFERENCES reservation_slots(reservation_id, slot_id)
        )
    """)
    connection.execute("""
        INSERT INTO active_slot_claims (slot_id, reservation_id)
        SELECT rs.slot_id, rs.reservation_id
        FROM reservation_slots AS rs
        JOIN reservations AS r ON r.reservation_id = rs.reservation_id
        WHERE r.status = 'confirmed'
          AND NOT EXISTS (
              SELECT 1 FROM active_slot_claims AS c
              WHERE c.slot_id = rs.slot_id AND c.reservation_id = rs.reservation_id
          )
    """)

def seed_amenities():
    connection = get_connection()
    try:
        from community_mate.community_catalog import seed_catalog
        seed_catalog(connection)
        connection.commit()
    finally:
        connection.close()

def seed_amenity_slots():
    # Explicit fictional demo week; operating hours alone do not create slots.
    from community_mate.community_catalog import AMENITIES
    slots = [
        (item[0], (Date(2026, 10, 23) + timedelta(days=day)).isoformat(),
         f"{hour:02}:00", f"{hour + 1:02}:00")
        for item in AMENITIES if item[4] == "reservation"
        for day in range(7) for hour in range(17, 21)
    ]

    connection = get_connection()
    try:
        connection.executemany(
            """
            INSERT INTO amenity_slots (
                amenity_id, slot_date, start_time, end_time
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(amenity_id, slot_date, start_time) DO NOTHING
            """,
            slots,
        )
        connection.commit()
    finally:
        connection.close()

def seed_residents():
    residents = [
        ("RES001", "Alice Johnson", "A101", "active"),
        ("RES002", "Bob Smith", "B202", "active"),
        ("RES003", "Charlie Brown", "C303", "inactive"),
    ]

    connection = get_connection()
    try:
        connection.executemany(
            """
            INSERT INTO residents (resident_id, name, unit_number, account_status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(resident_id) DO NOTHING
            """,
            residents,
        )
        from community_mate.community_catalog import enrich_demo_residents
        enrich_demo_residents(connection)
        connection.commit()
    finally:
        connection.close()

def get_available_slots(amenity_id: str, date: str):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT s.slot_id, s.slot_date, s.start_time, s.end_time
            FROM amenity_slots AS s
            WHERE s.amenity_id = ?
              AND s.slot_date = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM active_slot_claims AS rs
                  WHERE rs.slot_id = s.slot_id
              )
            ORDER BY s.start_time
            """,
            (amenity_id, date),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()

def get_available_windows(amenity_id: str, date: str, duration_hours: int):
    if type(duration_hours) is not int or not 1 <= duration_hours <= 4:
        raise ValueError("Duration must be a whole number from 1 to 4 hours.")

    try:
        parsed_date = Date.fromisoformat(date)
    except (TypeError, ValueError):
        raise ValueError("Date must be a valid date in YYYY-MM-DD format.") from None

    if parsed_date.isoformat() != date:
        raise ValueError("Date must use YYYY-MM-DD format.")

    amenity = get_amenity(amenity_id)

    if amenity is None:
        raise ValueError(f"Unknown amenity: {amenity_id}")

    from community_mate.community_catalog import require_reservable
    require_reservable(amenity)
    if duration_hours > amenity["max_booking_hours"]:
        raise ValueError(
            f"{amenity['name']} allows bookings up to "
            f"{amenity['max_booking_hours']} hours."
        )

    slots = get_available_slots(amenity_id, date)
    windows = []

    for index in range(len(slots) - duration_hours + 1):
        group = slots[index:index + duration_hours]

        consecutive = all(
            group[position]["end_time"] == group[position + 1]["start_time"]
            for position in range(len(group) - 1)
        )

        if consecutive:
            if (group[0]["start_time"] < amenity["opening_time"] or
                    group[-1]["end_time"] > amenity["closing_time"]):
                continue
            windows.append({
                "date": date,
                "start_time": group[0]["start_time"],
                "end_time": group[-1]["end_time"],
                "duration_hours": duration_hours,
            })

    return windows

def get_amenity(amenity_id: str):
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT *
            FROM amenities
            WHERE amenity_id = ?
            """,
            (amenity_id,),
        ).fetchone()

        return dict(row) if row is not None else None
    finally:
        connection.close()

def get_amenities():
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT *, CASE WHEN access_mode = 'reservation' THEN max_booking_hours
                           ELSE NULL END AS booking_limit_hours
            FROM amenities
            ORDER BY amenity_id
        """).fetchall()

        from community_mate.community_catalog import PROPERTY
        catalog = [dict(row) for row in rows]
        for amenity in catalog:
            amenity["timezone"] = PROPERTY["timezone"]
            if amenity["access_mode"] != "reservation":
                amenity["max_booking_hours"] = None
        return catalog
    finally:
        connection.close()

def get_reservation(reservation_id: int, resident_id: str):
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT reservation_id, resident_id, status, created_at
            FROM reservations
            WHERE reservation_id = ? AND resident_id = ?
            """,
            (reservation_id, resident_id),
        ).fetchone()

        return dict(row) if row is not None else None
    finally:
        connection.close()

def get_reservation_slots(reservation_id: int, resident_id: str):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                s.slot_id,
                s.slot_date,
                s.start_time,
                s.end_time,
                a.amenity_id,
                a.name AS amenity_name
            FROM reservations AS r
            JOIN reservation_slots AS rs
                ON rs.reservation_id = r.reservation_id
            JOIN amenity_slots AS s
                ON s.slot_id = rs.slot_id
            JOIN amenities AS a
                ON a.amenity_id = s.amenity_id
            WHERE r.reservation_id = ? AND r.resident_id = ?
            ORDER BY s.slot_date, s.start_time
            """,
            (reservation_id, resident_id),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()

def get_reservation_details(reservation_id: int, resident_id: str):
    connection = get_connection()
    try:
        return _read_reservation_details(connection, reservation_id, resident_id)
    finally:
        connection.close()


def _read_reservation_details(connection, reservation_id, resident_id):
    row = connection.execute(
        """SELECT reservation_id, resident_id, status, created_at
           FROM reservations WHERE reservation_id = ? AND resident_id = ?""",
        (reservation_id, resident_id),
    ).fetchone()
    if row is None:
        return None
    reservation = dict(row)
    reservation["slots"] = [dict(slot) for slot in connection.execute(
        """
        SELECT s.slot_id, s.slot_date, s.start_time, s.end_time,
               a.amenity_id, a.name AS amenity_name
        FROM reservation_slots AS rs
        JOIN amenity_slots AS s ON s.slot_id = rs.slot_id
        JOIN amenities AS a ON a.amenity_id = s.amenity_id
        WHERE rs.reservation_id = ?
        ORDER BY s.slot_date, s.start_time
        """,
        (reservation_id,),
    ).fetchall()]
    return reservation

def get_resident(resident_id: str):
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT *
            FROM residents
            WHERE resident_id = ?
            """,
            (resident_id,),
        ).fetchone()

        return dict(row) if row is not None else None
    finally:
        connection.close()

def require_active_resident(resident_id: str) -> dict:
    resident = get_resident(resident_id)

    if resident is None:
        raise ValueError("Resident account not found.")

    if resident["account_status"] != "active":
        raise ValueError("Only active residents may reserve amenities.")

    return resident

def validate_start_time(start_time: str) -> None:
    if not isinstance(start_time, str):
        raise ValueError("Start time must use HH:MM format.")

    try:
        parsed = datetime.strptime(start_time, "%H:%M")
    except ValueError:
        raise ValueError("Start time must use valid HH:MM format.") from None

    if parsed.strftime("%H:%M") != start_time or parsed.minute != 0:
        raise ValueError("Start time must be on the hour in HH:MM format.")

def get_requested_window(
    amenity_id: str,
    date: str,
    start_time: str,
    duration_hours: int,
) -> dict:
    validate_start_time(start_time)

    windows = get_available_windows(amenity_id, date, duration_hours)

    for window in windows:
        if window["start_time"] == start_time:
            return window

    raise ValueError("The requested booking window is unavailable.")


def get_booking_request(connection, resident_id: str, request_id: str):
    """Read retry information using the caller's transaction."""
    row = connection.execute(
        """
        SELECT amenity_id, slot_date, start_time, duration_hours, reservation_id
        FROM booking_requests
        WHERE resident_id = ? AND request_id = ?
        """,
        (resident_id, request_id),
    ).fetchone()
    return dict(row) if row is not None else None


def reserve_amenity(
    resident_id: str,
    amenity_id: str,
    date: str,
    start_time: str,
    duration_hours: int,
    request_id: str,
) -> dict:
    """Atomically book a confirmed request supplied by a trusted caller.

    The caller supplies trusted resident identity and obtains confirmation.
    This function does not authenticate users or establish consent.
    Reuse request_id only for retries of exactly the same booking.
    """
    if type(duration_hours) is not int or not 1 <= duration_hours <= 4:
        raise ValueError("Duration must be a whole number from 1 to 4 hours.")
    try:
        parsed_date = Date.fromisoformat(date)
    except (TypeError, ValueError):
        raise ValueError("Date must be a valid date in YYYY-MM-DD format.") from None
    if parsed_date.isoformat() != date:
        raise ValueError("Date must use YYYY-MM-DD format.")
    validate_start_time(start_time)
    for label, value in (
        ("Resident ID", resident_id),
        ("Amenity ID", amenity_id),
        ("Request ID", request_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a non-empty string.")

    start = datetime.combine(parsed_date, datetime.strptime(start_time, "%H:%M").time())
    end = start + timedelta(hours=duration_hours)
    if end.date() != start.date():
        raise ValueError("Bookings must start and finish on the same date.")

    connection = get_connection()
    try:
        # Obtain the write transaction BEFORE checking eligibility or claims.
        connection.execute("BEGIN IMMEDIATE")
        resident = connection.execute(
            "SELECT account_status FROM residents WHERE resident_id = ?",
            (resident_id,),
        ).fetchone()
        if resident is None:
            raise ValueError("Resident account not found.")
        if resident["account_status"] != "active":
            raise ValueError("Only active residents may reserve amenities.")

        previous = get_booking_request(connection, resident_id, request_id)
        if previous is not None:
            supplied = (amenity_id, date, start_time, duration_hours)
            recorded = tuple(previous[key] for key in
                             ("amenity_id", "slot_date", "start_time", "duration_hours"))
            if supplied != recorded:
                raise ValueError("Request ID was already used for different booking details.")
            reservation_id = previous["reservation_id"]
        else:
            amenity = connection.execute(
                "SELECT * FROM amenities WHERE amenity_id = ?",
                (amenity_id,),
            ).fetchone()
            if amenity is None:
                raise ValueError(f"Unknown amenity: {amenity_id}")
            from community_mate.community_catalog import require_reservable
            require_reservable(amenity)
            if start_time < amenity["opening_time"] or end.strftime("%H:%M") > amenity["closing_time"]:
                raise ValueError("The requested booking window is outside amenity operating hours.")
            if duration_hours > amenity["max_booking_hours"]:
                raise ValueError(
                    f"{amenity['name']} allows bookings up to "
                    f"{amenity['max_booking_hours']} hours."
                )

            slots = connection.execute(
                """
                SELECT s.slot_id, s.start_time, s.end_time
                FROM amenity_slots AS s
                WHERE s.amenity_id = ? AND s.slot_date = ?
                  AND s.start_time >= ? AND s.start_time < ?
                  AND NOT EXISTS (
                      SELECT 1 FROM active_slot_claims AS rs
                      WHERE rs.slot_id = s.slot_id
                  )
                ORDER BY s.start_time
                """,
                (amenity_id, date, start_time, end.strftime("%H:%M")),
            ).fetchall()
            expected = [
                ((start + timedelta(hours=i)).strftime("%H:%M"),
                 (start + timedelta(hours=i + 1)).strftime("%H:%M"))
                for i in range(duration_hours)
            ]
            actual = [(slot["start_time"], slot["end_time"]) for slot in slots]
            if actual != expected:
                raise ValueError("The requested booking window is unavailable.")

            cursor = connection.execute(
                "INSERT INTO reservations (resident_id, status) VALUES (?, 'confirmed')",
                (resident_id,),
            )
            reservation_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO reservation_slots (reservation_id, slot_id) VALUES (?, ?)",
                [(reservation_id, slot["slot_id"]) for slot in slots],
            )
            connection.executemany(
                "INSERT INTO active_slot_claims (slot_id, reservation_id) VALUES (?, ?)",
                [(slot["slot_id"], reservation_id) for slot in slots],
            )
            connection.execute(
                """
                INSERT INTO booking_requests (
                    resident_id, request_id, amenity_id, slot_date,
                    start_time, duration_hours, reservation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (resident_id, request_id, amenity_id, date,
                 start_time, duration_hours, reservation_id),
            )

        # Read back on this connection; return only after commit succeeds.
        reservation = _read_reservation_details(connection, reservation_id, resident_id)
        connection.commit()
        return reservation
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def cancel_amenity_reservation(resident_id: str, reservation_id: int) -> dict:
    """Cancel an owned booking atomically, retaining its original hourly links.

    Repeating cancellation returns the cancelled booking without affecting
    a later booking that reuses its hours. The caller obtains confirmation.
    Demo policy has no cancellation fee or cutoff enforcement.
    """
    if type(reservation_id) is not int or reservation_id <= 0:
        raise ValueError("Reservation ID must be a positive integer.")
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        booking = _read_reservation_details(connection, reservation_id, resident_id)
        if booking is None:
            raise ValueError("Reservation not found for the current resident.")
        connection.execute(
            "UPDATE reservations SET status = 'cancelled' WHERE reservation_id = ?",
            (reservation_id,),
        )
        connection.execute(
            "DELETE FROM active_slot_claims WHERE reservation_id = ?",
            (reservation_id,),
        )
        booking["status"] = "cancelled"
        connection.commit()
        return booking
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _maintenance_result(row) -> dict:
    """Return backend facts and a status-specific explanation, not a promise."""
    result = dict(row)
    result.pop("request_id", None)
    result["next_action"] = {
        "received": "Await property staff review; no technician or appointment is confirmed.",
        "assigned": "Check assigned_technician for the recorded assignment; visit preferences are not an appointment.",
        "scheduled": "Check scheduled_at for the recorded appointment; contact management for changes.",
        "in_progress": "Maintenance is recorded as in progress; await staff updates.",
        "completed": "Maintenance is recorded as completed; contact management if the issue remains.",
    }[result["status"]]
    return result


def _required_text(value, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters.")
    return value


def create_maintenance_request(
    resident_id: str,
    category: str,
    location: str,
    description: str,
    entry_permission: str,
    request_id: str,
    preferred_visit_times: str = "",
    reported_priority: str = "normal",
) -> dict:
    """Persist confirmed intake atomically; no dispatch or scheduling is performed.

    Identity and consent must be established by the caller. Identical retries
    return the existing ticket, including any later staff-recorded status.
    """
    resident_id = _required_text(resident_id, "Resident ID", 128)
    request_id = _required_text(request_id, "Request ID", 128)
    category = _required_text(category, "Category", 32).lower()
    entry_permission = _required_text(entry_permission, "Entry permission", 32).lower()
    reported_priority = _required_text(reported_priority, "Reported priority", 32).lower()
    if category not in {"plumbing", "electrical", "hvac", "appliance", "general"}:
        raise ValueError("Category must be plumbing, electrical, hvac, appliance, or general.")
    if entry_permission not in {"yes", "no", "ask_first"}:
        raise ValueError("Entry permission must be yes, no, or ask_first.")
    if reported_priority not in {"normal", "high"}:
        raise ValueError("Reported priority must be normal or high; it does not guarantee dispatch.")
    location = _required_text(location, "Location", 200)
    description = _required_text(description, "Description", 2000)
    if not isinstance(preferred_visit_times, str) or len(preferred_visit_times.strip()) > 500:
        raise ValueError("Preferred visit times must be a string of at most 500 characters.")
    preferred_visit_times = preferred_visit_times.strip()

    fields = ("category", "location", "description", "entry_permission",
              "preferred_visit_times", "reported_priority")
    details = (category, location, description, entry_permission,
               preferred_visit_times, reported_priority)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        resident = connection.execute(
            "SELECT account_status FROM residents WHERE resident_id = ?", (resident_id,)
        ).fetchone()
        if resident is None:
            raise ValueError("Resident account not found.")
        if resident["account_status"] != "active":
            raise ValueError("Only active demo residents may submit maintenance requests.")
        previous = connection.execute(
            "SELECT * FROM maintenance_requests WHERE resident_id = ? AND request_id = ?",
            (resident_id, request_id),
        ).fetchone()
        if previous is not None:
            if tuple(previous[field] for field in fields) != details:
                raise ValueError("Request ID was already used for different maintenance details.")
            result = _maintenance_result(previous)
        else:
            cursor = connection.execute(
                """
                INSERT INTO maintenance_requests (
                    resident_id, request_id, category, location, description,
                    entry_permission, preferred_visit_times, reported_priority
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (resident_id, request_id, *details),
            )
            row = connection.execute(
                "SELECT * FROM maintenance_requests WHERE ticket_id = ? AND resident_id = ?",
                (cursor.lastrowid, resident_id),
            ).fetchone()
            result = _maintenance_result(row)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_maintenance_status(ticket_id: int, resident_id: str):
    """Return an owned ticket, or None for both missing and inaccessible IDs."""
    if type(ticket_id) is not int or ticket_id <= 0:
        raise ValueError("Ticket ID must be a positive integer.")
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM maintenance_requests WHERE ticket_id = ? AND resident_id = ?",
            (ticket_id, resident_id),
        ).fetchone()
        return _maintenance_result(row) if row is not None else None
    finally:
        connection.close()
