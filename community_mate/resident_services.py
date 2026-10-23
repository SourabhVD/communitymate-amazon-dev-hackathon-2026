"""Fictional package, rent, renewal, and announcement services.

All writes are local simulations. No carrier, payment processor, signing
provider, email/SMS service, or real resident portal is connected.
"""

import json

from community_mate.database import get_connection, _required_text


def initialize_services(connection):
    """Create additive tables using the initialization caller's transaction."""
    statements = (
        """CREATE TABLE IF NOT EXISTS packages (
            package_id TEXT PRIMARY KEY NOT NULL,
            resident_id TEXT NOT NULL REFERENCES residents(resident_id),
            carrier TEXT NOT NULL, tracking_reference TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('expected', 'ready_for_pickup', 'collected')),
            pickup_location TEXT, received_at TEXT, collected_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS package_assistance (
            assistance_id INTEGER PRIMARY KEY, package_id TEXT NOT NULL REFERENCES packages(package_id),
            resident_id TEXT NOT NULL REFERENCES residents(resident_id),
            issue TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'received',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS rent_charges (
            charge_id TEXT PRIMARY KEY NOT NULL,
            resident_id TEXT NOT NULL REFERENCES residents(resident_id),
            billing_period TEXT NOT NULL, due_date TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            currency TEXT NOT NULL DEFAULT 'USD',
            UNIQUE(resident_id, billing_period)
        )""",
        """CREATE TABLE IF NOT EXISTS demo_payment_methods (
            method_id TEXT PRIMARY KEY NOT NULL,
            resident_id TEXT NOT NULL REFERENCES residents(resident_id),
            method_type TEXT NOT NULL CHECK(method_type IN ('ach', 'debit', 'credit')),
            display_label TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS demo_payments (
            payment_id INTEGER PRIMARY KEY,
            resident_id TEXT NOT NULL REFERENCES residents(resident_id),
            charge_id TEXT NOT NULL REFERENCES rent_charges(charge_id),
            method_id TEXT NOT NULL REFERENCES demo_payment_methods(method_id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            status TEXT NOT NULL DEFAULT 'simulated_succeeded',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS demo_autopay (
            resident_id TEXT PRIMARY KEY REFERENCES residents(resident_id),
            method_id TEXT NOT NULL REFERENCES demo_payment_methods(method_id),
            max_amount_cents INTEGER NOT NULL CHECK(max_amount_cents > 0),
            enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS renewal_offers (
            offer_id TEXT PRIMARY KEY NOT NULL,
            resident_id TEXT NOT NULL REFERENCES residents(resident_id),
            starts_on TEXT NOT NULL, ends_on TEXT NOT NULL,
            monthly_rent_cents INTEGER NOT NULL CHECK(monthly_rent_cents > 0),
            terms TEXT NOT NULL, expires_on TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'offered'
                CHECK(status IN ('offered', 'accepted_simulation', 'withdrawn')),
            signer_name TEXT, accepted_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS community_announcements (
            announcement_id TEXT PRIMARY KEY NOT NULL,
            title TEXT NOT NULL, message TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('amenity', 'event', 'maintenance')),
            published_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'demo_portal'
        )""",
        """CREATE TABLE IF NOT EXISTS service_actions (
            resident_id TEXT NOT NULL REFERENCES residents(resident_id),
            action TEXT NOT NULL, request_id TEXT NOT NULL,
            details_json TEXT NOT NULL, result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(resident_id, action, request_id)
        )""",
    )
    for statement in statements:
        connection.execute(statement)


def seed_resident_services():
    """Explicit, repeatable demo setup; never overwrite existing service records."""
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        # Dependencies are seeded separately by the existing resident seed.
        for resident in ("RES001", "RES002"):
            if connection.execute("SELECT 1 FROM residents WHERE resident_id = ?", (resident,)).fetchone() is None:
                raise ValueError("Seed residents before seeding resident services.")
        connection.executemany(
            """INSERT INTO packages VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(package_id) DO NOTHING""",
            [
                ("PKG001", "RES001", "Demo Carrier", "DEMO-TRACK-001", "ready_for_pickup",
                 "Leasing office package desk", "2026-10-22 16:00:00", None),
                ("PKG003", "RES002", "Demo Carrier", "DEMO-TRACK-003", "ready_for_pickup",
                 "Leasing office package desk", "2026-10-22 16:00:00", None),
            ],
        )
        connection.executemany(
            """INSERT INTO rent_charges VALUES (?, ?, ?, ?, ?, 'USD')
               ON CONFLICT(charge_id) DO NOTHING""",
            [("RENT001", "RES001", "2026-11", "2026-11-01", 150000),
             ("RENT002", "RES002", "2026-11", "2026-11-01", 160000)],
        )
        connection.executemany(
            """INSERT INTO demo_payment_methods VALUES (?, ?, ?, ?)
               ON CONFLICT(method_id) DO NOTHING""",
            [("DEMO_ACH_001", "RES001", "ach", "Fictional ACH method"),
             ("DEMO_DEBIT_001", "RES001", "debit", "Fictional debit method"),
             ("DEMO_CREDIT_001", "RES001", "credit", "Fictional credit method"),
             ("DEMO_ACH_002", "RES002", "ach", "Other resident demo method")],
        )
        connection.execute(
            """INSERT INTO renewal_offers (
                offer_id, resident_id, starts_on, ends_on, monthly_rent_cents, terms, expires_on
            ) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(offer_id) DO NOTHING""",
            ("LEASE001", "RES001", "2027-01-01", "2027-12-31", 155000,
             "Fictional 12-month renewal at USD 1550/month. No real lease is created or amended.",
             "2026-12-15"),
        )
        connection.executemany(
            """INSERT INTO community_announcements (
                announcement_id, title, message, category, published_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(announcement_id) DO NOTHING""",
            [("ANN001", "Demo pool closure", "Fictional pool closure October 23, 9 AM to noon for cleaning.",
              "amenity", "2026-10-22 00:00:00", "2026-10-24 00:00:00"),
             ("ANN002", "Demo community social", "Fictional clubhouse social October 25 at 4 PM.",
              "event", "2026-10-22 00:00:00", "2026-10-26 00:00:00"),
             ("ANN003", "Demo parking maintenance", "Fictional east parking-lot maintenance October 26, 8 AM to noon.",
              "maintenance", "2026-10-22 00:00:00", "2026-10-27 00:00:00")],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _resident(connection, resident_id):
    row = connection.execute("SELECT name, account_status FROM residents WHERE resident_id = ?",
                             (resident_id,)).fetchone()
    if row is None or row["account_status"] != "active":
        raise ValueError("An active demo resident account is required.")
    return row


def _positive_integer(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer.")


def _write(resident_id, action, request_id, details, operation):
    """Shared transaction/retry boundary for simulated service actions."""
    request_id = _required_text(request_id, "Request ID", 128)
    serialized = json.dumps(details, sort_keys=True)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        _resident(connection, resident_id)
        old = connection.execute(
            "SELECT details_json, result_json FROM service_actions WHERE resident_id = ? AND action = ? AND request_id = ?",
            (resident_id, action, request_id),
        ).fetchone()
        if old:
            if old["details_json"] != serialized:
                raise ValueError("Request ID was already used for different service details.")
            result = json.loads(old["result_json"])
        else:
            result = operation(connection)
            result.update(simulation=True)
            connection.execute(
                "INSERT INTO service_actions (resident_id, action, request_id, details_json, result_json) VALUES (?, ?, ?, ?, ?)",
                (resident_id, action, request_id, serialized, json.dumps(result)),
            )
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_packages(resident_id):
    connection = get_connection()
    try:
        _resident(connection, resident_id)
        return [dict(row) | {"simulation": True} for row in connection.execute(
            """SELECT package_id, resident_id, carrier, status, pickup_location,
                      received_at, collected_at
               FROM packages WHERE resident_id = ? AND received_at IS NOT NULL
                 AND status IN ('ready_for_pickup', 'collected')
               ORDER BY package_id""", (resident_id,)
        ).fetchall()]
    finally:
        connection.close()


def get_package_status(resident_id, package_id):
    package_id = _required_text(package_id, "Package ID", 128)
    connection = get_connection()
    try:
        _resident(connection, resident_id)
        row = connection.execute("""SELECT package_id, resident_id, carrier, status,
                pickup_location, received_at, collected_at FROM packages
                WHERE package_id = ? AND resident_id = ? AND received_at IS NOT NULL
                  AND status IN ('ready_for_pickup', 'collected')""",
                                 (package_id, resident_id)).fetchone()
        if row is None:
            raise ValueError("Concierge package record not found for the current resident. Check shipment progress with the carrier.")
        result = dict(row) | {"simulation": True, "record_source": "concierge receipt and collection log"}
        result["next_action"] = {
            "ready_for_pickup": "Use the recorded pickup location during office hours and bring identification. No locker code is issued.",
            "collected": "Collection is recorded; request package assistance if you dispute it.",
        }[result["status"]]
        return result
    finally:
        connection.close()


def request_package_assistance(resident_id, package_id, issue, request_id):
    package_id = _required_text(package_id, "Package ID", 128)
    issue = _required_text(issue, "Issue", 2000)
    def operation(connection):
        if connection.execute("""SELECT 1 FROM packages WHERE package_id = ? AND resident_id = ?
                AND received_at IS NOT NULL AND status IN ('ready_for_pickup', 'collected')""",
                              (package_id, resident_id)).fetchone() is None:
            raise ValueError("Concierge package record not found for the current resident. Check shipment progress with the carrier.")
        cursor = connection.execute(
            "INSERT INTO package_assistance (package_id, resident_id, issue) VALUES (?, ?, ?)",
            (package_id, resident_id, issue),
        )
        return {"assistance_id": cursor.lastrowid, "package_id": package_id,
                "status": "received", "message": "Saved locally; no staff notification was sent."}
    return _write(resident_id, "package_assistance", request_id, [package_id, issue], operation)


def _balance(connection, resident_id, charge_id):
    row = connection.execute("""
        SELECT c.*, c.amount_cents - COALESCE((
            SELECT SUM(p.amount_cents) FROM demo_payments AS p WHERE p.charge_id = c.charge_id
        ), 0) AS balance_cents
        FROM rent_charges AS c WHERE c.charge_id = ? AND c.resident_id = ?
    """, (charge_id, resident_id)).fetchone()
    if row is None:
        raise ValueError("Rent charge not found for the current resident.")
    return dict(row) | {"simulation": True}


def get_package_assistance_status(resident_id, assistance_id):
    _positive_integer(assistance_id, "Assistance ID")
    connection = get_connection()
    try:
        _resident(connection, resident_id)
        row = connection.execute(
            "SELECT * FROM package_assistance WHERE assistance_id = ? AND resident_id = ?",
            (assistance_id, resident_id),
        ).fetchone()
        if row is None:
            raise ValueError("Package assistance request not found for the current resident.")
        return dict(row) | {"simulation": True, "message": "Local request only; no staff notification was sent."}
    finally:
        connection.close()


def get_rent_account(resident_id):
    connection = get_connection()
    try:
        _resident(connection, resident_id)
        charges = connection.execute("SELECT charge_id FROM rent_charges WHERE resident_id = ? ORDER BY due_date",
                                     (resident_id,)).fetchall()
        return {"simulation": True, "currency": "USD",
                "charges": [_balance(connection, resident_id, row["charge_id"]) for row in charges],
                "payment_methods": [dict(row) for row in connection.execute(
                    "SELECT method_id, method_type, display_label FROM demo_payment_methods WHERE resident_id = ? ORDER BY method_id",
                    (resident_id,)).fetchall()],
                "payments": [dict(row) for row in connection.execute(
                    "SELECT payment_id, charge_id, method_id, amount_cents, status, created_at FROM demo_payments WHERE resident_id = ? ORDER BY payment_id",
                    (resident_id,)).fetchall()],
                "message": "Read-only fictional ledger. Payment and autopay actions are unavailable; no real payment processor is connected."}
    finally:
        connection.close()






def get_demo_autopay(resident_id):
    connection = get_connection()
    try:
        _resident(connection, resident_id)
        row = connection.execute("SELECT * FROM demo_autopay WHERE resident_id = ?", (resident_id,)).fetchone()
        return {"simulation": True, "configuration": dict(row) if row else None,
                "message": "Read-only simulated preferences. Autopay configuration and execution are unavailable; no scheduler is running."}
    finally:
        connection.close()






def get_lease_renewal_offers(resident_id):
    connection = get_connection()
    try:
        _resident(connection, resident_id)
        return {"simulation": True, "offers": [dict(row) for row in connection.execute(
            "SELECT * FROM renewal_offers WHERE resident_id = ? ORDER BY offer_id", (resident_id,)
        ).fetchall()], "message": "Read-only fictional offers. Approval, acceptance, signing, and lease changes are unavailable."}
    finally:
        connection.close()




def get_community_announcements(resident_id):
    connection = get_connection()
    try:
        _resident(connection, resident_id)
        rows = connection.execute("""
            SELECT * FROM community_announcements
            WHERE published_at <= CURRENT_TIMESTAMP AND expires_at > CURRENT_TIMESTAMP
            ORDER BY published_at DESC, announcement_id
        """).fetchall()
        return {"simulation": True, "announcements": [dict(row) for row in rows],
                "message": "Published demo portal notices only. No SMS, email, or push notifications are sent."}
    finally:
        connection.close()
