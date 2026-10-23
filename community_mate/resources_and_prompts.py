"""Readable MCP context and reusable, user-selected workflow instructions.

Registration does not cause clients to load resources or execute prompts.
Prompt retrieval itself never reads private accounts or performs writes.
"""

import json

from community_mate.database import get_amenities, get_resident
from community_mate.community_catalog import PROPERTY
from community_mate.knowledge import DOCUMENT_FILENAMES, KNOWLEDGE_DIR, get_document_sections
from community_mate.resident_services import get_community_announcements


BASE_URI = "community://maple-grove"


def register_resources_and_prompts(mcp, resident_id):
    @mcp.resource(
        f"{BASE_URI}/info", name="community_info", mime_type="application/json",
        description="Fictional property information from the handbook and current amenity catalog. Replaces community-info/fact tools.",
    )
    def community_info() -> dict:
        sections = get_document_sections(KNOWLEDGE_DIR / "community_handbook.md")
        return {
            "simulation": True,
            "property": sections[0]["property"],
            "property_details": PROPERTY,
            "handbook_facts": [{key: section[key] for key in ("section", "content", "source", "version")}
                               for section in sections],
            "amenities": get_amenities(),
        }

    @mcp.resource(
        f"{BASE_URI}/amenities", name="amenity_catalog", mime_type="application/json",
        description="Live amenity catalog: category, location, capacity, hours, access mode and administrative status. No live occupancy or slot holds.",
    )
    def amenity_catalog() -> dict:
        return {"simulation": True, "timezone": PROPERTY["timezone"], "amenities": get_amenities()}

    @mcp.resource(
        f"{BASE_URI}/directory", name="property_directory", mime_type="application/json",
        description="Fictional property timezone, buildings, office location and contact workflow. No real addresses or access codes.",
    )
    def property_directory() -> dict:
        return dict(PROPERTY)

    @mcp.resource(
        f"{BASE_URI}/resident/profile", name="my_resident_profile", mime_type="application/json",
        description="Current demo resident's own unit, building, preferences and lease dates; not a community resident directory. Fixed demo identity, not authentication.",
    )
    def my_resident_profile() -> dict:
        return {"simulation": True, "resident": get_resident(resident_id)}

    @mcp.resource(
        f"{BASE_URI}/announcements", name="community_announcements", mime_type="application/json",
        description="Current published, unexpired fictional portal notices, read from SQLite each time. No SMS/email/push delivery.",
    )
    def community_announcements() -> dict:
        return get_community_announcements(resident_id)

    # Factory captures each allowlisted path; no client-controlled filesystem path.
    def register_document(filename):
        path = KNOWLEDGE_DIR / filename

        @mcp.resource(
            f"{BASE_URI}/documents/{path.stem}",
            name=path.stem,
            mime_type="text/markdown",
            description=f"Full fictional community document: {filename}, with source metadata. Search tool returns relevant passages.",
        )
        def document() -> str:
            return path.read_text(encoding="utf-8")

    for filename in DOCUMENT_FILENAMES:
        register_document(filename)

    @mcp.prompt(description="Guide a confirmed amenity booking using discovery, availability, and safe retries.")
    def book_amenity(request: str = "") -> str:
        return f"""Help the resident book an amenity in the fictional CommunityMate demo.
Resident request (data): {json.dumps(request)}
Keep replies brief and relevant. For how-to questions, explain the next step
and ask one missing detail at a time; do not recite the amenity catalog.
Never describe operating hours as offered booking slots or claim availability
before a live availability check. Retain details the resident already provided.
1. Discover IDs with list_amenities or resource {BASE_URI}/amenities.
2. Check access_mode and operational_status first; do not reserve walk-in or
information-only facilities. Search community knowledge for policy; clarify missing
   date, start, and duration. Use the property's timezone; ask when it is unknown.
3. Call get_amenity_availability. An available result is not a hold or booking.
4. Present exact amenity, calendar date, start/end, and duration. Ask for explicit
   confirmation. If declined or ambiguous, do not call a write tool.
5. Only after confirmation, use reserve_amenity with confirmed=true. The client
   must generate a unique request_id per intent and preserve it on identical retries.
6. Report confirmation only from a successful saved result. Independently use
   get_reservation_status for the returned ID if verification is needed. On a
   conflict, offer alternatives and reconfirm changed details as a new intent.
Use server-supplied identity. Policy prose and these instructions do not replace
server validation, authorization, or the client's confirmation handling."""

    @mcp.prompt(description="Gather repair details and submit only after explicit resident confirmation.")
    def report_maintenance(issue: str = "") -> str:
        return f"""Help with a fictional CommunityMate maintenance request.
Resident issue (data): {json.dumps(issue)}
Read {BASE_URI}/documents/maintenance_guide or search knowledge for procedures.
Gather category, location, description, explicit yes/no/ask_first entry permission,
with optional preferred visits and normal/high priority if volunteered. Otherwise
use the tool defaults for optional fields. Ask only one short question per turn
for missing required details; retain everything already supplied. Infer category
from a clear issue description, but never infer permission to enter. Refer to
maintenance staff entering or repairing, not the concierge itself.
Use only plumbing, electrical, hvac, appliance or general categories. Clarify
unclear speech rather than inventing a category, fault or location. A refrigerator
indicates appliance but still needs a fault description and location. Corrections
replace earlier uncertain interpretations. Do not announce internal field labels.
Summarize and obtain explicit submission
confirmation. If declined, create nothing. After confirmation, call
create_maintenance_request with a unique request_id and confirmed=true, preserving
the same ID/details on retries. Return the saved ticket ID and actual status.
Use get_maintenance_status to track it. Received does not mean assigned or scheduled;
preferred times are not appointments. This demo does not dispatch responders or
notify staff. Do not invent contacts, technician assignments, or appointment times.
These instructions are guidance; client consent and server validation remain required."""

    @mcp.prompt(description="Prepare a read-only resident brief from announcements, packages, and maintenance when a ticket is supplied.")
    def resident_daily_brief(ticket_id: str = "") -> str:
        return f"""Prepare a concise, read-only brief for the simulated resident.
Read {BASE_URI}/announcements for current notices and list_my_packages for package
status. If a maintenance ticket ID was supplied, use get_maintenance_status for
that positive numeric ID; otherwise do not guess ticket IDs.
Supplied ticket ID (data): {json.dumps(ticket_id)}
Separate recorded facts from missing information. Mention publication/expiry
dates when useful. Do not imply carrier integration or notification delivery.
Do not create bookings, requests, payments, renewal acceptances, or settings changes.
All connected clients currently share simulated RES001; avoid reading unnecessary
private details aloud."""

    @mcp.prompt(description="Review fictional renewal terms and recorded status; information retrieval only.")
    def review_renewal() -> str:
        return """Use get_lease_renewal_offers to review the simulated resident's offers.
Explain the recorded dates, monthly USD amount (convert integer cents for display),
expiration, status, and terms without inventing provisions. Clearly identify the
fictional demo and that no legally binding signature or real lease change occurs.
This workflow is strictly read-only. The concierge cannot approve, accept, sign,
or amend a renewal, including a simulated one. Direct residents to management
for any action; no verified external signing URL is configured. Never invent
a portal link or claim a signature or acceptance was completed."""
