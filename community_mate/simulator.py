"""Local voice/chat simulator. Start with the isolated .agent-venv interpreter."""

import argparse
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import queue
import secrets
import threading
import time

from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from community_mate.agent_client import ClientConfirmation, WRITE_TOOLS, create_agent


STATIC = Path(__file__).resolve().parent.parent / "simulator"
ACTION_TITLES = {
    "reserve_amenity": "Reserve amenity",
    "cancel_amenity_reservation": "Cancel reservation",
    "create_maintenance_request": "Submit maintenance request",
    "request_package_assistance": "Request concierge package help",
}


@dataclass
class Settings:
    mcp_url: str = "http://127.0.0.1:8000/mcp"
    profile: str = "communitymate"
    region: str = "us-east-1"
    model_id: str = "us.amazon.nova-2-lite-v1:0"
    preview: bool = False
    approval_timeout: float = 120


class BrowserConfirmation(ClientConfirmation):
    def __init__(self, session):
        self.session = session
        self.current = None
        super().__init__(ask=self.ask_browser, show=lambda _: None)

    def inspect(self, tool_use):
        if self.session.closed.is_set():
            return "Session closed. Do not perform this action."
        name = tool_use["name"]
        self.session.emit("tool", name=name)
        if name in WRITE_TOOLS:
            # Check schema before asking the resident to approve an incomplete
            # action. The server remains the authority for business rules.
            from jsonschema import Draft202012Validator
            candidate = dict(tool_use["input"], confirmed=False)
            if name != "cancel_amenity_reservation":
                candidate.setdefault("request_id", "pending-client-request")
            schema = self.session.schemas.get(name)
            if schema:
                errors = list(Draft202012Validator(schema).iter_errors(candidate))
                if errors:
                    return "Ask for missing or invalid details before confirmation: " + errors[0].message
            self.current = tool_use
        return super().inspect(tool_use)

    def ask_browser(self, _):
        action = self.current
        details = {key: value for key, value in action["input"].items()
                   if key not in {"confirmed", "request_id"}}
        return "yes" if self.session.request_approval(action["name"], details) else "no"


class Conversation:
    def __init__(self, settings, agent_factory=None):
        self.settings = settings
        self.agent_factory = agent_factory
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.events = []
        self.inbox = queue.Queue()
        self.closed = threading.Event()
        self.busy = False
        self.seen_messages = set()
        self.pending = None
        self.last_used = time.monotonic()
        self.schemas = {}
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def emit(self, kind, **data):
        with self.lock:
            self.events.append({"id": len(self.events) + 1, "type": kind, **data})

    def submit(self, text, message_id):
        with self.lock:
            self.last_used = time.monotonic()
            if message_id in self.seen_messages:
                return 200
            if self.busy or self.closed.is_set():
                return 409
            self.busy = True
            self.seen_messages.add(message_id)
            self.emit("resident", text=text)
            self.emit("state", state="thinking")
            self.inbox.put(text)
            return 202

    def request_approval(self, name, details):
        pending = {"approval_id": secrets.token_urlsafe(24), "name": name,
                   "details": details, "event": threading.Event(), "accepted": False}
        with self.lock:
            if self.closed.is_set():
                return False
            self.pending = pending
            self.emit("confirmation", approval_id=pending["approval_id"],
                      action=ACTION_TITLES.get(name, name), details=details,
                      expires_in=self.settings.approval_timeout)
        answered = pending["event"].wait(self.settings.approval_timeout)
        with self.lock:
            accepted = answered and pending["accepted"] and not self.closed.is_set()
            self.pending = None
            self.emit("confirmation_resolved", accepted=accepted,
                      reason="answered" if answered else "expired")
        return accepted

    def approve(self, approval_id, accepted):
        with self.lock:
            if (not self.pending or self.pending["approval_id"] != approval_id
                    or self.pending["event"].is_set()):
                return False
            self.pending["accepted"] = accepted
            self.pending["event"].set()
            return True

    def close(self):
        with self.lock:
            self.closed.set()
            if self.pending:
                self.pending["event"].set()  # fail closed if browser goes away
            self.inbox.put(None)

    def run(self):
        # This thread owns its MCP connection and agent for the whole session.
        # No credentials are accessed and no model is created until a message.
        with ExitStack() as stack:
            agent = None
            while not self.closed.is_set():
                text = self.inbox.get()
                if text is None:
                    return
                try:
                    if self.settings.preview:
                        self.preview_reply(text)
                    else:
                        if agent is None:
                            if self.agent_factory:
                                agent = self.agent_factory(self)
                            else:
                                from strands.tools.mcp import MCPClient
                                client = stack.enter_context(MCPClient(url=self.settings.mcp_url))
                                tools = client.list_tools_sync()
                                self.schemas = {tool.tool_name: tool.tool_spec["inputSchema"]["json"]
                                                for tool in tools}
                                agent = create_agent(
                                    client, self.settings.profile, self.settings.region,
                                    self.settings.model_id,
                                    confirmation=BrowserConfirmation(self),
                                    callback_handler=lambda **kwargs: None,
                                    extra_instructions=(
                                        "This is a voice-first browser simulator. Keep replies short, "
                                        "normally 1-2 short sentences and around 40 words or fewer. "
                                        "Give more detail only when requested or needed for an accurate "
                                        "action confirmation. Answer the actual question first, not every "
                                        "field returned by a tool. For a how-to question, explain the next "
                                        "step briefly and ask one useful follow-up. Do not turn a how-to "
                                        "question into an amenity brochure or announce 'I found it'. "
                                        "Omit location, capacity, hours, rules and booking limits unless "
                                        "asked or directly needed to resolve the current request. Do not "
                                        "repeat the resident's question or add a generic offer of help. "
                                        "For example, to 'How do I book the study room?', say 'Tell me "
                                        "when you'd like to use it, and I'll check the available slots. "
                                        "What date works for you?' This is style guidance, not evidence "
                                        "of availability. Never say that a space or time is available "
                                        "without a successful live availability check. Operating hours "
                                        "are not offered booking hours: do not tell residents they can "
                                        "book any time within opening hours. Speak naturally using contractions and "
                                        "everyday language. Turn tool results into a direct conversational "
                                        "answer rather than reading records or copying status messages. "
                                        "Do not use Markdown, bullet lists, headings, or field-label summaries "
                                        "unless the resident specifically requests a list. Say 'reservation "
                                        "number 3' rather than 'Reservation ID: 3'. Mention reference numbers "
                                        "once when creating a record or when useful for the question. "
                                        "Use conversation context and avoid repeating established details or "
                                        "generic closing offers. When gathering details, ask only ONE short "
                                        "question per turn, not a questionnaire or a numbered checklist. "
                                        "Do not combine issue, location and entry permission in one "
                                        "question. Speech recognition may produce fragments or wrong "
                                        "words. If an utterance is incomplete, ask one brief clarification "
                                        "rather than treating a guessed meaning as a confirmed detail. "
                                        "For 'Can you raise a complaint that for the', ask 'What would "
                                        "you like to report?' For an unclear fragment such as 'It's all "
                                        "Salon', ask 'I didn't catch that. What's the issue?' Never say "
                                        "'category is salon' or assume a salon location. If the next turn "
                                        "is 'It's the refrigerator', drop the unsupported interpretation "
                                        "and ask 'What's wrong with the refrigerator?' Internally use "
                                        "appliance, but do not assume it is in the kitchen or invent a "
                                        "fault. An earlier assistant assertion is not proof of location. "
                                        "If salon came only from an unclear fragment or your own guess, "
                                        "do not reuse it in a confirmation; ask 'Where is the refrigerator?' "
                                        "Only explicitly supplied, unambiguous resident details may fill "
                                        "required fields. Clarify uncertainty before requesting submission "
                                        "confirmation, rather than asking the resident to approve a guess. "
                                        "These examples illustrate uncertainty handling, not "
                                        "fixed replies to every complaint. "
                                        "Extract all useful details the resident volunteers and never ask "
                                        "again for something already supplied. For maintenance, first ask "
                                        "what is wrong; then ask only for missing location and explicit "
                                        "entry permission, one turn at a time. Infer category from a clear "
                                        "issue description, but never infer permission to enter. If the "
                                        "resident only says HVAC, retain that category and ask 'What's "
                                        "happening with your heating or cooling?' Do not assume a specific "
                                        "HVAC fault. Do not require preferred visit times or priority: use "
                                        "the tool defaults unless the resident supplies them. Ask whether "
                                        "maintenance staff may enter, not whether you may enter or fix it. "
                                        "For example, to 'Create maintenance', reply 'Sure. What needs "
                                        "fixing?' If the resident says 'The bedroom AC isn't cooling', "
                                        "retain category hvac, location bedroom, and that description, "
                                        "then ask 'May maintenance enter if you're not home, or should "
                                        "they ask you first?' Show the exact action confirmation only "
                                        "after required details are complete. Preserve exact facts, policy limits, dates, "
                                        "amounts, and statuses. Never invent details or imply that a received "
                                        "maintenance request has a technician or appointment. For example, "
                                        "a successful confirmed booking can be phrased 'You're booked for "
                                        "the clubhouse from 5 to 7 PM on October 23. Your reservation number "
                                        "is 3.' Use that wording only if the actual result supports it. "
                                        "Host confirmation appears in the browser. "
                                        "If the resident declines or confirmation expires, acknowledge "
                                        "that no action was performed and stop that action."
                                    ),
                                )
                        self.emit("assistant", text=str(agent(text)))
                except Exception as error:
                    # Keep the transcript, but do not automatically replay a paid
                    # invocation or an uncertain write after failure.
                    self.emit("error", text=f"{type(error).__name__}: {error}")
                finally:
                    with self.lock:
                        self.busy = False
                    self.emit("state", state="ready")

    def preview_reply(self, text):
        """UI-only rehearsal, explicitly labelled; never calls a backend action."""
        if any(word in text.lower() for word in ("book", "reserve", "maintenance", "cancel")):
            accepted = self.request_approval("reserve_amenity", {
                "amenity": "Preview clubhouse", "date": "Interface rehearsal only",
                "duration_hours": 2,
            })
            reply = ("Preview confirmation accepted. Nothing was saved; this is an interface rehearsal."
                     if accepted else "Preview action declined. Nothing was saved.")
        else:
            reply = "This is the interface preview. Try the microphone or type a request. No model is connected and nothing is saved."
        self.emit("assistant", text=reply)


class Sessions:
    def __init__(self, settings, agent_factory=None):
        self.settings = settings
        self.agent_factory = agent_factory
        self.items = {}
        self.lock = threading.Lock()

    def create(self):
        with self.lock:
            for token, item in list(self.items.items()):
                if time.monotonic() - item.last_used > 1200:
                    item.close()
                    del self.items[token]
            if len(self.items) >= 8:
                raise ValueError("Too many local sessions. Close a session or restart the simulator.")
            item = Conversation(self.settings, self.agent_factory)
            self.items[item.token] = item
            return item

    def get(self, request):
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        with self.lock:
            item = self.items.get(token)
            if item:
                item.last_used = time.monotonic()
            return item


def create_app(settings=None, agent_factory=None):
    settings = settings or Settings()
    sessions = Sessions(settings, agent_factory)

    @asynccontextmanager
    async def lifespan(app):
        yield
        for item in list(sessions.items.values()):
            item.close()

    async def index(request):
        return FileResponse(STATIC / "index.html")

    async def health(request):
        return JSONResponse({"mode": "preview" if settings.preview else "live",
                             "resident": "RES001", "simulation": True})

    async def new_session(request):
        try:
            item = sessions.create()
            return JSONResponse({"token": item.token}, status_code=201)
        except ValueError as error:
            return JSONResponse({"error": str(error)}, status_code=429)

    async def events(request):
        item = sessions.get(request)
        if not item:
            return JSONResponse({"error": "Session expired. Start a new conversation."}, status_code=401)
        try:
            after = max(0, int(request.query_params.get("after", "0")))
        except ValueError:
            return JSONResponse({"error": "Invalid event cursor."}, status_code=400)
        with item.lock:
            return JSONResponse({"events": item.events[after:], "busy": item.busy})

    async def message(request):
        item = sessions.get(request)
        if not item:
            return JSONResponse({"error": "Session expired. Start a new conversation."}, status_code=401)
        try:
            body = await request.json()
            text, message_id = body.get("text"), body.get("message_id")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
                raise ValueError("Enter a message of 1-4000 characters.")
            if not isinstance(message_id, str) or not 1 <= len(message_id) <= 128:
                raise ValueError("A message ID is required.")
        except (ValueError, AttributeError):
            return JSONResponse({"error": "Invalid message or message ID."}, status_code=400)
        status = item.submit(text.strip(), message_id)
        return JSONResponse({"accepted": status != 409}, status_code=status)

    async def confirmation(request):
        item = sessions.get(request)
        if not item:
            return JSONResponse({"error": "Session expired."}, status_code=401)
        try:
            body = await request.json()
            if type(body.get("accepted")) is not bool or not isinstance(body.get("approval_id"), str):
                raise ValueError
        except (ValueError, AttributeError):
            return JSONResponse({"error": "Invalid confirmation."}, status_code=400)
        if not item.approve(body["approval_id"], body["accepted"]):
            return JSONResponse({"error": "This confirmation expired or was already answered."}, status_code=409)
        return JSONResponse({"accepted": body["accepted"]})

    async def close(request):
        item = sessions.get(request)
        if item:
            item.close()
            with sessions.lock:
                sessions.items.pop(item.token, None)
        return JSONResponse({"closed": True})

    app = Starlette(routes=[
        Route("/", index), Route("/api/health", health),
        Route("/api/session", new_session, methods=["POST"]),
        Route("/api/session", close, methods=["DELETE"]),
        Route("/api/events", events), Route("/api/messages", message, methods=["POST"]),
        Route("/api/confirmation", confirmation, methods=["POST"]),
        Mount("/static", StaticFiles(directory=STATIC), name="static"),
    ], lifespan=lifespan)
    app.state.sessions = sessions
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    async def local_browser_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = {f"http://127.0.0.1:{request.url.port}", f"http://localhost:{request.url.port}",
                   "http://testserver"}
        if origin and origin not in allowed:
            return JSONResponse({"error": "Cross-origin requests are not allowed."}, status_code=403)
        if request.method in {"POST", "DELETE"} and request.headers.get("x-communitymate-client") != "1":
            return JSONResponse({"error": "Local simulator client header required."}, status_code=403)
        if request.method == "POST" and not request.headers.get("content-type", "").startswith("application/json"):
            return JSONResponse({"error": "JSON request required."}, status_code=415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=local_browser_boundary)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--mcp-url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--profile", default="communitymate")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--model", default="us.amazon.nova-2-lite-v1:0")
    parser.add_argument("--preview", action="store_true", help="UI rehearsal only; no MCP/AWS/model calls")
    args = parser.parse_args()
    settings = Settings(mcp_url=args.mcp_url, profile=args.profile, region=args.region,
                        model_id=args.model, preview=args.preview)
    import uvicorn
    print(f"CommunityMate simulator: http://127.0.0.1:{args.port}")
    print("Interface preview: no model calls." if args.preview else "Live Bedrock mode: messages incur usage charges.")
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
