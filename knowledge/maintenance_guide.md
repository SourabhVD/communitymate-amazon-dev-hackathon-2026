# Maintenance Guide

Property: Maple Grove Apartments
Document ID: maintenance-guide
Version: 2
Effective date: 2026-10-22
Access level: community

## Reporting a Repair

This is a fictional CommunityMate demo procedure for active demo residents. Tickets are saved locally; this demo does not contact property staff or dispatch responders.

Residents can submit maintenance requests for repairs or issues within their apartment or shared community areas.

When reporting a repair, provide the following information:

- **Issue Category:** Use plumbing, electrical, hvac, appliance, or general.
- **Location:** Specify the apartment unit, room, or common area where the issue occurs.
- **Description:** Explain the problem clearly, including relevant symptoms, when it started, and any other useful details.
- **Entry Permission:** Explicitly choose yes, no, or ask_first. The concierge must not assume permission to enter.
- **Preferred Visit Times:** Provide preferred dates or time windows for a maintenance visit.

Providing complete and accurate information helps the property management team review and coordinate the repair request.

## Submission Confirmation and Retries

The concierge must summarize the category, location, description, entry permission, reported priority, and any preferred visit times, then obtain explicit confirmation before submitting. Declining confirmation creates no ticket. A successfully saved request receives a numeric ticket ID. The client uses a unique request ID per submission intent and reuses it with identical details when retrying an uncertain response. Such retries return the original ticket; reusing the ID with different details is rejected. Photo attachments are not supported in this demo.

## Preferred Visit Times and Reported Priority

Preferred visit times are free-text resident preferences, not scheduled appointments. They may be left blank. Reported priority may be normal or high and is a resident-reported concern, not an automated emergency determination or a dispatch guarantee. No technician is assigned and no appointment is scheduled by the ticket-creation tool. This demo does not provide emergency response or verified after-hours contact details.

## Request Status

Submitting a maintenance request confirms only that the request has been **received** by the property management system.

A successfully submitted request does **not** mean:

- A technician has been assigned.
- A maintenance appointment has been scheduled or confirmed.
- The requested visit time has been approved.
- Repair work has started.

Residents may check the status of their maintenance request to determine whether it is awaiting review, assigned, scheduled, in progress, or completed.

Technician assignments and appointment confirmations must be explicitly verified through the maintenance request system.

**Important:** The AI resident concierge must not claim that a technician has been assigned or an appointment confirmed unless the maintenance system explicitly provides that information.

## Maintenance Status Definitions

- received: the ticket is saved and awaiting review; no assignment or appointment is confirmed.
- assigned: staff have recorded assignment status; use the actual assigned_technician field for any name.
- scheduled: staff have recorded scheduled status; use the actual scheduled_at field for appointment information.
- in_progress: staff have recorded work as in progress.
- completed: staff have recorded completion; contact management if the problem remains.

Only backend records establish actual progress. Null assigned_technician or scheduled_at fields mean no corresponding detail is recorded. The resident-facing tools cannot change status or fabricate staff updates. Status access is restricted to the current resident in the demo; all connected clients currently act as simulated resident RES001, which is not production authentication.
