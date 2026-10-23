"""Start an isolated real HTTP server and check the installed Strands MCP client.

No AWS call, no model, and no access to the main demo database.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


ROOT = Path(__file__).resolve().parent.parent
SERVER_PYTHON = ROOT / ".venv/Scripts/python.exe"
CLIENT_PYTHON = ROOT / ".agent-venv/Scripts/python.exe"


def main():
    if not SERVER_PYTHON.exists() or not CLIENT_PYTHON.exists():
        raise SystemExit("Create both server and agent environments first; see PHASE3_CLIENT.md.")
    with TemporaryDirectory() as folder:
        child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        server_code = """
import sys
from pathlib import Path
from community_mate import database as db
from community_mate.server import mcp
db.DB_PATH = Path(sys.argv[1])
db.initialize_database()
db.seed_residents()
db.seed_amenities()
mcp.run(transport='streamable-http', host='127.0.0.1', port=int(sys.argv[2]))
"""
        with open(Path(folder) / "server.log", "w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(SERVER_PYTHON), "-c", server_code, str(Path(folder) / "test.db"), str(port)],
                cwd=ROOT, stdout=log, stderr=log,
                env=child_env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Isolated server stopped during startup.")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise TimeoutError("Isolated server did not become ready.")
                result = subprocess.run(
                    [str(CLIENT_PYTHON), "-m", "community_mate.agent_client", "--check",
                     "--url", f"http://127.0.0.1:{port}/mcp"],
                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=35,
                    env=child_env,
                )
                if result.returncode:
                    raise RuntimeError(result.stdout + result.stderr)
                report = json.loads(result.stdout)
                assert report["aws_called"] is False and report["writes_performed"] is False
                assert len(report["resources"]) == 14 and len(report["prompts"]) == 4
                assert "reserve_amenity" in report["tools"]
                print(f"HTTP check passed: {len(report['tools'])} tools, {len(report['resources'])} resources, 4 prompts.")
                print("Read community info and retrieved booking prompt. No AWS calls or demo database writes.")
            finally:
                # Windows venv launchers may start a child python process;
                # stop this test's entire process tree so log/DB handles close.
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
