"""Browser API/consent tests using a fake agent; no AWS calls or demo DB writes."""

import importlib.util
import time
import unittest

if importlib.util.find_spec("httpx") is None:
    raise unittest.SkipTest("Run simulator tests with .agent-venv (httpx dependency).")

from starlette.testclient import TestClient
from community_mate.simulator import BrowserConfirmation, Settings, create_app


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.effects = []

    def factory(self, session):
        session.schemas = {"create_maintenance_request": {
            "type": "object", "required": ["location"],
            "properties": {"location": {"type": "string"}},
        }}
        guard = BrowserConfirmation(session)

        def agent(text):
            args = {} if text == "missing" else {"location": "Kitchen"}
            reason = guard.inspect({"name": "create_maintenance_request",
                                    "input": args, "toolUseId": "test-call"})
            if reason:
                return reason
            self.effects.append(args)
            return "Fake agent: test request saved."
        return agent

    def connect(self, client):
        response = client.post("/api/session", json={}, headers={"X-CommunityMate-Client": "1"})
        self.assertEqual(response.status_code, 201)
        return {"Authorization": "Bearer " + response.json()["token"], "X-CommunityMate-Client": "1"}

    def wait_for(self, client, headers, kind):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            events = client.get("/api/events", headers=headers).json()["events"]
            found = [event for event in events if event["type"] == kind]
            if found:
                return found[-1]
            time.sleep(.01)
        self.fail("Event not received: " + kind)

    def test_ui_and_preview_have_no_model_calls(self):
        with TestClient(create_app(Settings(preview=True))) as client:
            self.assertIn("CommunityMate", client.get("/").text)
            self.assertEqual(client.get("/api/health").json()["mode"], "preview")
            headers = self.connect(client)
            client.post("/api/messages", headers=headers, json={"text": "hello", "message_id": "a"})
            self.assertIn("No model", self.wait_for(client, headers, "assistant")["text"])

    def test_decline_stale_confirmation_and_authorization(self):
        with TestClient(create_app(Settings(), self.factory)) as client:
            self.assertEqual(client.get("/api/events").status_code, 401)
            headers = self.connect(client)
            client.post("/api/messages", headers=headers, json={"text": "repair", "message_id": "a"})
            pending = self.wait_for(client, headers, "confirmation")
            self.assertEqual(client.post("/api/confirmation", headers=headers,
                json={"approval_id": "wrong", "accepted": True}).status_code, 409)
            result = client.post("/api/confirmation", headers=headers,
                json={"approval_id": pending["approval_id"], "accepted": False})
            self.assertEqual(result.status_code, 200)
            self.assertIn("declined", self.wait_for(client, headers, "assistant")["text"])
            self.assertEqual(self.effects, [])

    def test_confirm_and_duplicate_message_execute_once(self):
        with TestClient(create_app(Settings(), self.factory)) as client:
            headers = self.connect(client)
            message = {"text": "repair", "message_id": "same"}
            client.post("/api/messages", headers=headers, json=message)
            pending = self.wait_for(client, headers, "confirmation")
            self.assertEqual(client.post("/api/messages", headers=headers, json=message).status_code, 200)
            client.post("/api/confirmation", headers=headers,
                        json={"approval_id": pending["approval_id"], "accepted": True})
            self.wait_for(client, headers, "assistant")
            self.assertEqual(len(self.effects), 1)
            self.assertTrue(self.effects[0]["confirmed"])
            self.assertTrue(self.effects[0]["request_id"].startswith("client-"))
            self.assertEqual(client.post("/api/confirmation", headers=headers,
                json={"approval_id": pending["approval_id"], "accepted": True}).status_code, 409)

    def test_confirmation_expiry_and_close_fail_closed(self):
        with TestClient(create_app(Settings(approval_timeout=.03), self.factory)) as client:
            headers = self.connect(client)
            client.post("/api/messages", headers=headers, json={"text": "repair", "message_id": "a"})
            self.assertIn("declined", self.wait_for(client, headers, "assistant")["text"])
            self.assertEqual(self.effects, [])
        with TestClient(create_app(Settings(), self.factory)) as client:
            headers = self.connect(client)
            client.post("/api/messages", headers=headers, json={"text": "repair", "message_id": "a"})
            self.wait_for(client, headers, "confirmation")
            client.delete("/api/session", headers=headers)
            self.assertEqual(self.effects, [])
            self.assertEqual(client.get("/api/events", headers=headers).status_code, 401)

    def test_missing_fields_do_not_prompt_for_approval(self):
        with TestClient(create_app(Settings(), self.factory)) as client:
            headers = self.connect(client)
            client.post("/api/messages", headers=headers, json={"text": "missing", "message_id": "a"})
            self.assertIn("missing or invalid", self.wait_for(client, headers, "assistant")["text"])
            events = client.get("/api/events", headers=headers).json()["events"]
            self.assertFalse(any(event["type"] == "confirmation" for event in events))

    def test_cross_origin_and_untrusted_requests_rejected(self):
        with TestClient(create_app(Settings(preview=True))) as client:
            self.assertEqual(client.post("/api/session", json={}).status_code, 403)
            self.assertEqual(client.post("/api/session", json={}, headers={
                "X-CommunityMate-Client": "1", "Origin": "https://untrusted.example",
            }).status_code, 403)
            self.assertEqual(client.get("/", headers={"Host": "untrusted.example"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
