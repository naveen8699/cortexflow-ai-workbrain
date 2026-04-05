# WorkBrain — AI Personal Operating System
**Google ADK + Vertex AI + CopilotKit AG-UI + Cloud Run + Cloud SQL**

> Turn meeting transcripts into fully executed action plans. 5 AI agents coordinate to extract tasks, calculate cognitive load, create calendar events, and produce task cards — autonomously.

---

## Architecture

```
Frontend (Next.js + CopilotKit)  →  FastAPI (Cloud Run)
                                          │
                                   ADK Orchestrator (Vertex AI Gemini)
                                    ├── transcript_agent   → get_today_iso @tool
                                    ├── cognitive_agent    → calculate_cognitive_load @tool
                                    ├── scheduler_agent    → Calendar MCP @tools
                                    └── execution_agent    → Tasks MCP @tool
                                          │
                                   Cloud SQL PostgreSQL
                                   (meetings · action_items · cognitive_state · decisions_log)
```

---

## Local Development — Step by Step

### Prerequisites
- Python 3.11+, Node 18+, Docker, gcloud CLI, psql client

### Step 1 — Clone & Configure GCP
```bash
# Edit PROJECT_ID and DB_PASSWORD at top of file
nano scripts/setup_gcp.sh

# Run GCP setup (enables APIs, creates Cloud SQL, service account)
chmod +x scripts/setup_gcp.sh && ./scripts/setup_gcp.sh
```

### Step 2 — Database
```bash
# Download Cloud SQL Proxy
curl -o cloud-sql-proxy \
  "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64"
chmod +x cloud-sql-proxy

# Start proxy (keep this terminal open)
./cloud-sql-proxy YOUR_PROJECT:us-central1:workbrain-db --port=5432

# Apply schema (new terminal)
PGPASSWORD=WorkBrain2024! psql -h 127.0.0.1 -U postgres -d workbrain -f scripts/schema.sql
```

### Step 3 — Backend
```bash
cd backend
cp .env.example .env
# Edit .env: set GCP_PROJECT_ID, DB_PASSWORD

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export GOOGLE_APPLICATION_CREDENTIALS=./service-account.json
uvicorn main:app --reload --port 8080
# → http://localhost:8080/docs
```

### Step 4 — Google OAuth (Calendar + Tasks)
```bash
chmod +x scripts/setup_oauth.sh && ./scripts/setup_oauth.sh
# Opens browser, signs in, saves token.json
```

### Step 5 — Frontend
```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
# → http://localhost:3000
```

### Step 6 — Test Everything
```bash
pip install httpx  # if not already
python scripts/test_e2e.py
```

---

## Cloud Deployment

### Backend → Cloud Run
```bash
chmod +x scripts/deploy_backend.sh && ./scripts/deploy_backend.sh
```

### Frontend → Firebase Hosting
```bash
npm install -g firebase-tools
firebase login
chmod +x scripts/deploy_frontend.sh && ./scripts/deploy_frontend.sh
```

---

## Project Structure

```
workbrain/
├── backend/
│   ├── main.py                    # FastAPI app + CopilotKit endpoint
│   ├── config.py                  # Settings from .env
│   ├── agents/
│   │   ├── adk_tools.py           # @tool decorated functions (Gemini calls these)
│   │   ├── adk_agents.py          # 5 LlmAgent definitions (ADK)
│   │   └── adk_runner.py          # Runner bridge → FastAPI + DB writes
│   ├── db/
│   │   ├── database.py            # Async SQLAlchemy engine
│   │   └── models.py              # ORM: Meeting, ActionItem, CognitiveState, DecisionLog
│   ├── models/schemas.py          # Pydantic request/response schemas
│   ├── tools/calendar_tool.py     # Google Calendar + Tasks API wrappers
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── app/                   # Next.js pages (dashboard, meetings, tasks, decisions)
│       ├── components/
│       │   ├── copilot/           # CopilotKit AG-UI provider + sidebar
│       │   ├── dashboard/         # StatCards, CognitiveLoadPanel, DecisionsFeed, SchedulePanel
│       │   ├── meetings/          # ProcessMeetingForm, MeetingsList
│       │   ├── tasks/             # AddTaskForm, TaskTable
│       │   └── decisions/         # DecisionsTable
│       ├── hooks/useDashboard.ts  # 3s polling hook
│       ├── lib/api.ts             # Typed API client
│       └── types/index.ts         # TypeScript types
└── scripts/
    ├── schema.sql                 # Cloud SQL schema
    ├── setup_gcp.sh               # GCP one-time setup
    ├── setup_oauth.sh             # Google OAuth setup
    ├── deploy_backend.sh          # Cloud Run deploy
    ├── deploy_frontend.sh         # Firebase Hosting deploy
    └── test_e2e.py                # End-to-end test
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | DB + ADK status check |
| POST | /api/meetings/process | Run full 4-agent pipeline on transcript |
| POST | /api/tasks | Add task + recalculate cognitive load |
| GET | /api/dashboard | All data for frontend (polled every 3s) |
| GET | /api/meetings | List processed meetings |
| GET | /api/meetings/{id}/decisions | Decisions for one meeting |
| GET | /api/decisions | Full decisions log |
| GET | /api/tasks | All action items |
| POST | /api/copilotkit | CopilotKit AG-UI streaming endpoint |

---

## Key Design Decisions

**Why ADK?** Google-native agent framework. `LlmAgent` with `sub_agents` is real multi-agent coordination — Gemini reads agent descriptions and decides delegation order. Judges at a Google hackathon will recognise this.

**Why cognitive load in Python (not LLM)?** Deterministic math runs in <50ms, never hallucinates a percentage, costs zero LLM tokens. This is your "proprietary algorithm" story.

**Why Cloud SQL not AlloyDB?** Identical PostgreSQL dialect, 3-minute setup vs 15+. Same demo impression.

**Why @tool not direct function calls?** ADK `@tool` makes functions callable by Gemini mid-reasoning with auto-generated JSON schema. This is what makes the agents truly autonomous rather than scripted.

**Multi-user ready?** Yes. Every table has `user_id` column + index. Every query is scoped. Every agent receives user context. Adding Firebase Auth = 1-day integration.

---

## Demo Script

1. Open dashboard at localhost:3000
2. Click "Load demo transcript" in Process Meeting panel
3. Click "Process Meeting →"
4. Watch CopilotKit sidebar stream agent reasoning
5. Watch cognitive load meters update (Arjun goes red at 138%)
6. Watch overload alert banner appear
7. Watch decisions feed populate with reasons
8. Check Google Calendar — events created
9. Check Google Tasks — task cards created
10. Click Decisions page — full reasoning log
