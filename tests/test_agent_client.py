"""Host-side confirmation checks; no Strands install or model call required."""

import unittest
from community_mate.agent_client import ClientConfirmation


class AgentConfirmationTests(unittest.TestCase):
    def tool(self, **changes):
        result = {"name": "reserve_amenity", "toolUseId": "call-1", "input": {
            "amenity_id": "CLB001", "date": "2026-10-23", "start_time": "17:00",
            "duration_hours": 2, "request_id": "intent-1", "confirmed": True,
        }}
        result.update(changes)
        return result

    def test_model_confirmation_cannot_bypass_host(self):
        guard = ClientConfirmation(ask=lambda _: "no", show=lambda _: None)
        call = self.tool()
        self.assertIn("declined", guard.inspect(call))
        self.assertFalse(call["input"]["confirmed"])

    def test_host_assigns_retry_keys(self):
        guard = ClientConfirmation(ask=lambda _: "yes", show=lambda _: None)
        first, second = self.tool(), self.tool()
        self.assertIsNone(guard.inspect(first))
        self.assertIsNone(guard.inspect(second))
        self.assertTrue(first["input"]["confirmed"])
        self.assertTrue(first["input"]["request_id"].startswith("client-"))
        self.assertEqual(first["input"]["request_id"], second["input"]["request_id"])

    def test_missing_confirmation_input_denies(self):
        def disconnected(_):
            raise EOFError
        guard = ClientConfirmation(ask=disconnected, show=lambda _: None)
        self.assertIn("declined", guard.inspect(self.tool()))

    def test_reads_do_not_prompt_and_disabled_actions_are_blocked(self):
        def unexpected(_):
            raise AssertionError("Unexpected confirmation")
        guard = ClientConfirmation(ask=unexpected)
        self.assertIsNone(guard.inspect(self.tool(name="list_amenities", input={})))
        self.assertIn("disabled", guard.inspect(self.tool(name="make_demo_rent_payment")))


if __name__ == "__main__":
    unittest.main()
