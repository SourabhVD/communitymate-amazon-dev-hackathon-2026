from mcp.server import MCPServer
from typing import Literal
from community_mate.database import get_available_windows, get_amenities, get_reservation_details
from community_mate.database import reserve_amenity as save_amenity_reservation
from community_mate.database import cancel_amenity_reservation as cancel_saved_reservation
from community_mate.database import create_maintenance_request as save_maintenance_request
from community_mate.database import get_maintenance_status as read_maintenance_status
from mcp.server.mcpserver.exceptions import ToolError
from community_mate.knowledge import search_policy
from community_mate.service_tools import register_service_tools
from community_mate.resources_and_prompts import register_resources_and_prompts

mcp = MCPServer("CommunityMate")
DEMO_RESIDENT_ID = "RES001"

@mcp.tool()
def get_amenity_availability(
    amenity_id: str,
    date: str,
    duration_hours: int,
) -> list[dict]:
    """Find available booking windows for an amenity ID and YYYY-MM-DD date.

    Duration must be 1, 2, 3, or 4 consecutive hours, within the amenity's
    booking limit. Returns an empty list when no matching windows exist.
    This tool checks availability; it does not create a reservation.
    """
    try:
        return get_available_windows(amenity_id, date, duration_hours)
    except ValueError as error:
        raise ToolError(str(error)) from error

@mcp.tool()
def list_amenities() -> list[dict]:
    """List amenity IDs, categories, locations, hours, capacities and access rules.

    Only access_mode=reservation accepts bookings; walk_in is shared access
    and information_only requires the stated external or staff workflow.
    operational_status is administrative, not live occupancy. Hours use the
    property timezone. Only booking_limit_hours applies to reservable spaces.
    Use the returned amenity_id when checking reservable-space availability.
    This tool does not check availability or create reservations.
    """
    return get_amenities()

@mcp.tool()
def get_reservation_status(reservation_id: int) -> dict:
    """Get a reservation and its booked slots for the current demo resident."""
    if reservation_id <= 0:
        raise ToolError("Reservation ID must be a positive integer.")

    reservation = get_reservation_details(
        reservation_id, DEMO_RESIDENT_ID
    )

    if reservation is None:
        raise ToolError("Reservation not found for the current resident.")

    return reservation

@mcp.tool()
def search_community_knowledge(
    query: str,
    limit: int = 3,
) -> list[dict]:
    """Search fictional demo community documents using keyword matching.

    Covers office hours, quiet hours, amenity booking rules, maintenance
    reporting procedures, request-status explanations, parking, pet rules,
    package pickup, read-only rent/payment information, renewals, and community updates.
    Returns passages with source metadata and keyword-overlap scores.
    An empty list means no matching evidence was found.
    Scores measure word overlap, not confidence. Does not check live
    availability, create requests, grant parking approval, or register pets.
    """
    try:
        return search_policy(query, limit)
    except ValueError as error:
        raise ToolError(str(error)) from error

@mcp.tool()
def reserve_amenity(
    amenity_id: str,
    date: str,
    start_time: str,
    duration_hours: int,
    request_id: str,
    confirmed: bool = False,
) -> dict:
    """Create an amenity booking for the current simulated resident (RES001).

    First show the amenity, YYYY-MM-DD date, HH:MM start, and duration to
    the resident and obtain explicit confirmation. Only then set confirmed
    to true. Confirmation is reported by the client, not independently verified.
    Duration is 1-4 consecutive hours within the amenity's limit.
    The client must generate a unique request_id per booking intent and reuse
    it with identical details for retries. Never generate a new ID just to retry
    an uncertain response. Availability is rechecked atomically when booking.
    Only a successful response means the booking has been saved.
    """
    if confirmed is not True:
        raise ToolError("Booking not created. Confirm the exact booking details first.")
    try:
        return save_amenity_reservation(
            DEMO_RESIDENT_ID, amenity_id, date, start_time,
            duration_hours, request_id,
        )
    except ValueError as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def cancel_amenity_reservation(reservation_id: int, confirmed: bool = False) -> dict:
    """Cancel a booking owned by the current simulated resident (RES001).

    Show the booking details and obtain explicit cancellation confirmation
    before setting confirmed=true. The client reports consent; this demo has
    no cancellation fees or cutoff. Returns cancelled status with original
    booked hours and frees active claims. Repeated cancellation is safe.
    """
    if confirmed is not True:
        raise ToolError("Booking not cancelled. Confirm cancellation of this reservation first.")
    try:
        return cancel_saved_reservation(DEMO_RESIDENT_ID, reservation_id)
    except ValueError as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def create_maintenance_request(
    category: Literal["plumbing", "electrical", "hvac", "appliance", "general"],
    location: str,
    description: str,
    entry_permission: Literal["yes", "no", "ask_first"],
    request_id: str,
    preferred_visit_times: str = "",
    reported_priority: Literal["normal", "high"] = "normal",
    confirmed: bool = False,
) -> dict:
    """Submit a repair ticket for simulated resident RES001 after confirmation.

    Gather category, location, description, and entry permission; do not infer
    permission to enter. Ask for missing required details one question at a
    time, retaining details already supplied. Use optional visit-time and
    priority defaults unless the resident supplies them. Show
    the intake summary before obtaining explicit submission confirmation.
    Only then set confirmed=true; consent is reported by the client.
    Use a unique request_id per intent and identical details/ID for retries.
    A successful new ticket is received, not assigned or scheduled. Preferred
    times and reported priority do not confirm appointments or dispatch.
    This demo does not contact staff or emergency responders. No attachments
    are supported. Use get_maintenance_status for live ticket facts and
    search_community_knowledge for reporting procedures and status definitions.
    """
    if confirmed is not True:
        raise ToolError("Request not submitted. Confirm the maintenance details first.")
    try:
        return save_maintenance_request(
            DEMO_RESIDENT_ID, category, location, description,
            entry_permission, request_id, preferred_visit_times, reported_priority,
        )
    except ValueError as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def get_maintenance_status(ticket_id: int) -> dict:
    """Read the current demo resident's repair ticket and recorded next action.

    Includes status, submitted details, reported priority, entry preference,
    timestamps, and any staff-recorded technician/appointment. Null assignment
    or scheduled_at means none is recorded. Do not treat requested visit times
    as a confirmed appointment. Missing and inaccessible tickets look identical.
    """
    try:
        ticket = read_maintenance_status(ticket_id, DEMO_RESIDENT_ID)
        if ticket is None:
            raise ValueError("Maintenance request not found for the current resident.")
        return ticket
    except ValueError as error:
        raise ToolError(str(error)) from error


register_service_tools(mcp, DEMO_RESIDENT_ID)
register_resources_and_prompts(mcp, DEMO_RESIDENT_ID)


if __name__ == "__main__":
    # Also applies the transactional legacy-slot migration on startup.
    from community_mate.database import initialize_database
    initialize_database()
    mcp.run(transport="streamable-http")




