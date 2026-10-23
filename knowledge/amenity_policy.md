# Amenity Booking Policy

Property: Maple Grove Apartments
Document ID: amenity-policy
Version: 3
Effective date: 2026-10-22
Access level: community

## 1. Reservation Duration

Only catalog entries with access_mode=reservation and operational_status=open accept bookings. Shared walk-in and information-only facilities cannot be reserved. Consult amenity_access_guide.md and the live catalog for locations, hours and access notes. All amenity booking dates and times use America/Chicago.

Residents may book amenities for **1, 2, 3, or 4 consecutive hours**, subject to the amenity's configured maximum reservation duration.

Reservations must consist of continuous, uninterrupted hourly slots. Requests exceeding the amenity's maximum duration are not permitted.

## 2. Hourly Availability

Every hour included in a requested reservation must be both **offered and available**.

If any requested hour is unavailable or outside the amenity's offered booking hours, the entire reservation request is ineligible.

## 3. Resident Eligibility

Only residents with an **active residency status** may create amenity reservations.

Inactive residents are not eligible to reserve amenities.

## 4. Clubhouse Booking Window — October 23, 2026

For the seeded CommunityMate demo, the clubhouse offers the following booking window:

- **Date:** October 23, 2026
- **Start:** 17:00 (5:00 PM)
- **End:** 21:00 (9:00 PM)
- **Available hourly slots:** 17:00–18:00, 18:00–19:00, 19:00–20:00, and 20:00–21:00, subject to existing reservations.

A reservation must start and finish within this window and satisfy all duration and availability requirements.

## 5. Availability Checks and Booking Confirmation

An amenity availability check is **informational only**.

Checking availability does not temporarily hold, reserve, or guarantee any time slot.

A booking is confirmed only after the reservation operation successfully validates the request and saves the reservation record.

CommunityMate must not tell a resident that a booking is confirmed based solely on an availability check.

## 6. Demo Cancellation

Under this fictional demo policy, residents may cancel their own bookings after explicitly confirming cancellation. This demo applies no cancellation fees or cutoff. A successful cancellation releases the booked hours for others and preserves the original reservation details with cancelled status. Repeating a cancellation does not affect a later booking of those hours. Retrying the original booking request does not reactivate a cancelled booking; a new booking intent requires a new request ID.
