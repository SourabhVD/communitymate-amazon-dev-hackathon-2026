"""Register local-only resident service tools with server-owned demo identity."""

from mcp.server.mcpserver.exceptions import ToolError
from community_mate import resident_services as services


def register_service_tools(mcp, resident_id):
    def read(function, *args):
        try:
            return function(resident_id, *args)
        except ValueError as error:
            raise ToolError(str(error)) from error

    def write(confirmed, function, *args):
        if confirmed is not True:
            raise ToolError("No action taken. Confirm the exact demo action details first.")
        return read(function, *args)

    @mcp.tool()
    def list_my_packages() -> list[dict]:
        """List the resident's packages already received by the concierge, with local IDs.

        Includes ready-for-pickup and recorded collection history only.
        No in-transit, expected-delivery, or carrier tracking information.
        Empty means no concierge record, not proof that a carrier lost an item.
        Use get_package_status for pickup guidance. Demo data only.
        """
        return read(services.list_packages)

    @mcp.tool()
    def get_package_status(package_id: str) -> dict:
        """Read an owned concierge package receipt/collection record and pickup help.

        Requires a recorded concierge receipt. Local package_id is not a shipper
        tracking number. Cannot track shipments, delivery estimates, or transit.
        Direct shipment questions to the carrier. No locker codes are issued.
        Search community knowledge for concierge pickup procedures.
        """
        return read(services.get_package_status, package_id)

    @mcp.tool()
    def request_package_assistance(package_id: str, issue: str, request_id: str,
                                   confirmed: bool = False) -> dict:
        """Save a concierge pickup/damage/collection issue for an owned received package.

        Confirm the package and issue before submission. Use one unique
        request_id per intent, identical on retries. Returns a local received
        acknowledgment; no staff notification or carrier claim is made.
        Does not investigate in-transit shipments or packages not received here.
        """
        return write(confirmed, services.request_package_assistance, package_id, issue, request_id)

    @mcp.tool()
    def get_package_assistance_status(assistance_id: int) -> dict:
        """Read an owned package-help request's actual local status by assistance ID.
        No staff contact or carrier investigation is implied by received status.
        """
        return read(services.get_package_assistance_status, assistance_id)

    @mcp.tool()
    def get_rent_account() -> dict:
        """Read fictional rent charges, balances in USD cents, demo methods, and receipts.

        Information retrieval only. Cannot initiate payments, change payment
        methods, or configure/run autopay. Never ask for bank/card credentials.
        """
        return read(services.get_rent_account)


    @mcp.tool()
    def get_demo_autopay() -> dict:
        """Read simulated recurring-payment preferences; no background job runs."""
        return read(services.get_demo_autopay)



    @mcp.tool()
    def get_lease_renewal_offers() -> dict:
        """Read current resident's fictional renewal terms, amounts in USD cents,
        expiration dates, and recorded status. Information retrieval only;
        cannot approve, accept, sign, or amend a renewal.
        """
        return read(services.get_lease_renewal_offers)


