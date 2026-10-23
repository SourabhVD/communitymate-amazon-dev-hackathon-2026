"""Fictional demo catalog, additive migrations, and repeatable seed data.

Amenity types are inspired by public apartment listings; every location, rule,
capacity and operating hour below is invented for Maple Grove, not a source fact.
"""

PROPERTY = {
    "property_id": "MAPLE001", "name": "Maple Grove Apartments",
    "timezone": "America/Chicago", "simulation": True,
    "location": "Fictional Richardson, Texas community",
    "buildings": ["A", "B", "C"],
    "office_location": "Building A, ground-floor lobby",
    "office_hours": "Monday-Friday 09:00-17:00; weekends closed",
    "contact": "Use the fictional resident portal or visit the leasing office; no live contact service is connected.",
}

# ID, name, category, location, access mode, capacity, open, close, notes.
AMENITIES = (
    ("CLB001", "Clubhouse 1", "social", "Building A, ground floor", "reservation", 30, "09:00", "21:00", "Resident-hosted gatherings; clean up after use."),
    ("MEET301", "Meeting Room 1", "work_study", "Building C, third floor", "reservation", 8, "09:00", "21:00", "Quiet meetings; shared Wi-Fi and display."),
    ("STDY001", "Study Room 1", "work_study", "Building B, second floor", "reservation", 4, "09:00", "21:00", "Quiet group study; no amplified audio."),
    ("MEDIA001", "Media Room", "entertainment", "Building A, second floor", "reservation", 12, "09:00", "21:00", "Shared screen; resident supplies media access."),
    ("PICK001", "Pickleball Court", "sports", "East recreation area", "reservation", 4, "09:00", "21:00", "Court booking does not include equipment rental."),
    ("BBQ001", "Outdoor Grill Pavilion", "outdoor", "Central courtyard", "reservation", 12, "09:00", "21:00", "Reserve the pavilion; clean grills and extinguish cooking equipment after use."),
    ("GOLF001", "Golf Simulator Room", "sports", "Building B, ground floor", "reservation", 4, "09:00", "21:00", "Indoor virtual golf; follow posted equipment instructions."),
    ("GYM001", "Fitness Center", "fitness", "Building B, ground floor", "walk_in", 20, "00:00", "24:00", "Resident credential required; open 24 hours; occupancy is not tracked."),
    ("YOGA001", "Yoga and Stretching Studio", "fitness", "Building B, ground floor", "walk_in", 10, "06:00", "22:00", "Shared use; no classes or instructors are scheduled by this demo."),
    ("POOL001", "Swimming Pool", "wellness", "Central courtyard", "walk_in", 40, "09:00", "21:00", "Follow posted pool safety rules; no lifeguard or live occupancy monitoring is represented."),
    ("BASK001", "Basketball Court", "sports", "East recreation area", "walk_in", 10, "09:00", "21:00", "Shared first-come use; no exclusive court reservations."),
    ("DOG001", "Dog Park", "pet", "West lawn", "walk_in", 15, "06:00", "22:00", "Supervise pets and remove waste; follow the pet policy."),
    ("COURT001", "Courtyard and Firepit Lounge", "outdoor", "Central courtyard", "walk_in", 20, "09:00", "21:00", "Shared seating; firepit operation is controlled by staff, not the concierge."),
    ("BUS001", "Business Center", "work_study", "Building A, lobby", "walk_in", 6, "09:00", "17:00", "Shared workstations and printer; no printing allowance is promised."),
    ("PLAY001", "Playground", "outdoor", "West lawn", "walk_in", 12, "09:00", "21:00", "Children must be supervised by a responsible adult."),
    ("EV001", "EV Charging Area", "transport", "North parking area", "information_only", 2, "00:00", "24:00", "Charging sessions, fees and live charger status belong to an external operator; no activation tool."),
    ("PKGDESK001", "Concierge Package Desk", "resident_service", "Building A, leasing office", "information_only", None, "09:00", "17:00", "Weekdays only. Ask about concierge-received packages; carrier shipment tracking is external."),
)


def migrate_catalog(connection):
    """Add columns without rebuilding or replacing existing resident records."""
    additions = {
        "amenities": {
            "category": "TEXT NOT NULL DEFAULT 'social'",
            "location": "TEXT NOT NULL DEFAULT 'Location not configured'",
            "access_mode": "TEXT NOT NULL DEFAULT 'reservation' CHECK(access_mode IN ('reservation','walk_in','information_only'))",
            "operational_status": "TEXT NOT NULL DEFAULT 'open' CHECK(operational_status IN ('open','closed','maintenance'))",
            "capacity": "INTEGER CHECK(capacity IS NULL OR capacity > 0)",
            "opening_time": "TEXT NOT NULL DEFAULT '09:00'",
            "closing_time": "TEXT NOT NULL DEFAULT '21:00'",
            "access_notes": "TEXT NOT NULL DEFAULT ''",
        },
        "residents": {
            "building": "TEXT", "floor": "INTEGER CHECK(floor IS NULL OR floor >= 0)",
            "email": "TEXT", "phone": "TEXT",
            "lease_start": "TEXT", "lease_end": "TEXT", "move_in_date": "TEXT",
            "preferred_name": "TEXT", "preferred_language": "TEXT NOT NULL DEFAULT 'en-US'",
            "notification_preference": "TEXT NOT NULL DEFAULT 'portal' CHECK(notification_preference IN ('portal','email','sms','none'))",
        },
    }
    for table, columns in additions.items():
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, declaration in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def seed_catalog(connection):
    for aid, name, category, location, mode, capacity, opening, closing, notes in AMENITIES:
        connection.execute(
            """INSERT INTO amenities
               (amenity_id,name,max_booking_hours,category,location,access_mode,capacity,
                opening_time,closing_time,access_notes) VALUES (?,?,4,?,?,?,?,?,?,?)
               ON CONFLICT(amenity_id) DO NOTHING""",
            (aid, name, category, location, mode, capacity, opening, closing, notes),
        )
        # Fill metadata on the two original demo records without replacing
        # their names, booking limits, operational status or reservation links.
        connection.execute(
            """UPDATE amenities SET category=?,location=?,access_mode=?,capacity=?,
               opening_time=?,closing_time=?,access_notes=?
               WHERE amenity_id=? AND location='Location not configured'""",
            (category, location, mode, capacity, opening, closing, notes, aid),
        )


def enrich_demo_residents(connection):
    for rid, building, floor, preferred, start, end in (
        ("RES001", "A", 1, "Alice", "2026-01-01", "2026-12-31"),
        ("RES002", "B", 2, "Bob", "2026-06-01", "2027-05-31"),
        ("RES003", "C", 3, "Charlie", "2025-01-01", "2025-12-31"),
    ):
        connection.execute(
            """UPDATE residents SET building=COALESCE(building,?),floor=COALESCE(floor,?),
               preferred_name=COALESCE(preferred_name,?),email=COALESCE(email,?),
               lease_start=COALESCE(lease_start,?),lease_end=COALESCE(lease_end,?),
               move_in_date=COALESCE(move_in_date,?) WHERE resident_id=?""",
            (building, floor, preferred, f"{rid.lower()}@example.invalid", start, end, start, rid),
        )


def require_reservable(amenity):
    if amenity["operational_status"] != "open":
        raise ValueError("This amenity is closed or under maintenance; reservations are unavailable.")
    if amenity["access_mode"] != "reservation":
        raise ValueError("This amenity does not accept reservations. Check its access notes and operating hours.")
