# Resident Services Guide

Property: Maple Grove Apartments
Document ID: resident-services-guide
Version: 4
Effective date: 2026-10-22
Access level: community

## Concierge Package Receipt and Pickup

Shipment tracking, transit progress, and delivery estimates belong to the shipper or carrier. CommunityMate only answers about packages after concierge staff have recorded receipt. List your concierge packages to discover local package IDs; these are not carrier tracking numbers. Ready for pickup means a concierge receipt is recorded; visit the recorded pickup location during office hours with identification. Collected means collection is recorded in that log. An empty list or missing concierge record does not prove non-delivery or loss; check shipment progress with the carrier and ask the concierge to verify physical receipt. No locker unlock, pickup code, or carrier proof of delivery is generated. These are fictional demo concierge records.

## Package Assistance

For a package already logged by the concierge, residents can ask about pickup location and hours or request help with pickup, observed damage, an item missing from the desk, or disputed collection. Identify the local package ID, describe the issue, and confirm submission. A local received acknowledgment does not mean staff have been notified or a carrier claim opened. Assistance tools do not track or investigate in-transit or unreceived shipments. Only your own concierge records are accessible in the simulated resident account.

## Rent and Payment Information

Rent and payment capabilities are strictly information retrieval only. Read the fictional rent account for charges, due dates, remaining balance, recorded payment history, and seeded ACH, debit, or credit demo method labels. Amounts are integer USD cents: 150000 is USD 1500.00. Never provide real bank or card credentials. The concierge cannot initiate payments, modify payment methods, transfer money, or issue refunds, including simulated transactions. No real payment processor or portal is connected. Previously recorded demo receipts, if present, are historical information only.

## Autopay Information

Residents may read any previously recorded fictional autopay preferences through get_demo_autopay. A null configuration means no preferences are recorded. The concierge cannot enable, disable, change, simulate, schedule, or execute recurring payments. There is no background scheduler or payment runner. Any payment or autopay changes must be handled outside CommunityMate through the property's actual portal; no verified portal URL is configured, so the concierge must not invent one.

## Lease Renewal Offers

Management-authored fictional renewal offers show term dates, monthly rent in USD cents, expiration, terms, and recorded status. This capability is strictly information retrieval. The concierge cannot approve, accept, sign, or amend a renewal, including simulated acceptance. Contact management for renewal actions. No verified signing portal URL is configured; do not invent one. Previously recorded status is historical information, not authority to perform a new action.

## Community Updates and Notifications

The demo portal lists published, unexpired management notices, including pool closures, community events, and parking-lot maintenance. Timestamps are UTC unless explicitly stated otherwise. Residents cannot broadcast notices through these tools. No SMS, email blasts, or push notifications are sent. A future management integration would publish content and use a notification provider with resident channel preferences; delivery must not be claimed from a portal read alone.
