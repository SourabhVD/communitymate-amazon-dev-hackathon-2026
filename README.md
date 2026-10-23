# CommunityMate

A fictional apartment resident concierge with a voice-first web interface.

Architecture:
Browser -> Strands Agent -> Amazon Bedrock -> MCP server -> SQLite / Markdown documents.

This is an independent simulated Alexa+ experience, not a direct Alexa integration.
All clients use simulated resident RES001. Payment and lease features are read-only.

## Requirements

- Windows PowerShell
- Python 3.13
- AWS CLI with an authenticated `communitymate` profile
- Bedrock permission to invoke `us.amazon.nova-2-lite-v1:0` in us-east-1

Live messages incur Bedrock usage charges. AWS credentials are not included.

## Install

Run from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

py -3.13 -m venv .agent-venv
.\.agent-venv\Scripts\python.exe -m pip install -r requirements-agent.txt

.\.venv\Scripts\python.exe -m community_mate.setup_demo
```

Keep the server and agent environments separate because their MCP dependencies differ.
Setup creates fictional records and backs up an existing database before updating it.
Demo booking slots cover October 23-29, 2026.

## Run

Authenticate using your own authorized AWS account:

```powershell
aws login --profile communitymate
```

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m community_mate.server
```

Terminal 2:

```powershell
.\.agent-venv\Scripts\python.exe -m community_mate.simulator
```

Open http://127.0.0.1:8080.

## Interface preview without AWS

```powershell
.\.agent-venv\Scripts\python.exe -m community_mate.simulator --preview
```

Preview uses fixed rehearsal responses and does not save actions.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.agent-venv\Scripts\python.exe -m unittest discover -s tests -p test_simulator.py -q
.\.agent-venv\Scripts\python.exe scripts/check_agent_connection.py
```
