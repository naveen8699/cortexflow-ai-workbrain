# 🧠 WorkBrain by CortexFlow

> AI-powered meeting execution system that automatically transforms meeting transcripts into action items, cognitive load assessments, calendar events, and team notifications — in real time.

[![Demo](https://img.shields.io/badge/Live%20Demo-workbrain--cortexflow.web.app-blue)](https://workbrain-cortexflow-project.web.app)
[![Backend](https://img.shields.io/badge/Backend-Cloud%20Run-green)](https://workbrain-backend-114869691007.us-central1.run.app)
[![License](https://img.shields.io/badge/License-Apache%202.0-yellow)](LICENSE)

---

## 🎯 Problem

Every meeting ends the same way — someone has to manually:
- Extract action items from notes
- Assign tasks to team members
- Create calendar focus blocks
- Notify the team on Slack
- Calculate who is overloaded

This takes **2+ hours per meeting** and is error-prone. For APAC teams, it's even harder — timezone differences, public holidays, and distributed ownership make coordination painful.

---

## ✅ Solution

WorkBrain listens to your meeting transcript and automatically:

1. **Extracts** structured action items using Gemini 2.5 Flash with enforced JSON schema
2. **Calculates** cognitive load per team member using Sweller's Cognitive Load Theory formula
3. **Schedules** focus blocks on Google Calendar — skipping overloaded team members and APAC public holidays
4. **Creates** Google Tasks cards for each action item
5. **Notifies** the team on Slack with a rich summary
6. **Invites** team members to their calendar focus blocks via real Google Calendar invitations

All of this happens in **under 2 minutes**, with real-time progress streaming via SSE.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER / BROWSER                        │
│          Next.js 14 + CopilotKit AG-UI                  │
│     Firebase Hosting (workbrain-cortexflow.web.app)     │
└──────────────────────┬──────────────────────────────────┘
                       │ SSE Stream (real-time progress)
                       ▼
┌─────────────────────────────────────────────────────────┐
│               CLOUD RUN — FastAPI Backend               │
│                  (min-instances=1)                       │
│                                                          │
│   ┌──────────────────────────────────────────────────┐  │
│   │     WorkBrainPipelineAgent (ADK CustomAgent)     │  │
│   │          Orchestrator — BaseAgent                │  │
│   │   Manages state, DB writes, SSE progress events  │  │
│   └──────────────────────────────────────────────────┘  │
│                          │                               │
│        ┌─────────────────┼─────────────────┐            │
│        ▼                 ▼                 ▼             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │
│  │  transcript  │ │  cognitive   │ │  scheduler   │    │
│  │    agent     │ │    agent     │ │    agent     │    │
│  │gemini-2.5-   │ │gemini-1.5-  │ │gemini-2.5-  │    │
│  │    flash     │ │    flash     │ │    flash     │    │
│  │ Structured   │ │ Sweller CLT  │ │Google Search │    │
│  │   Output     │ │   Formula    │ │  Grounding   │    │
│  │Pydantic      │ │AlloyDB MCP   │ │Calendar MCP  │    │
│  │  Schema      │ │              │ │APAC Holidays │    │
│  └──────────────┘ └──────────────┘ └──────────────┘    │
│                          │                               │
│                          ▼                               │
│                  ┌──────────────┐                        │
│                  │  execution   │                        │
│                  │    agent     │                        │
│                  │gemini-1.5-  │                        │
│                  │    flash     │                        │
│                  │ Google Tasks │                        │
│                  │  Slack MCP   │                        │
│                  └──────────────┘                        │
└──────┬──────────────────────────────────┬───────────────┘
       │                                  │
       ▼                                  ▼
┌──────────────────┐            ┌─────────────────────┐
│   AlloyDB AI     │            │    Google APIs       │
│   PostgreSQL 17  │            │                      │
│   pgvector(768)  │◄──MCP─────►│  Calendar MCP        │
│   pg_trgm        │  Toolbox   │  Google Tasks MCP    │
│   Embeddings     │  v0.7.0    │  Slack MCP (stdio)   │
│ text-embedding   │            │  Search Grounding    │
│      -004        │            │  bypass_multi_tools  │
└──────────────────┘            └─────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│              Vertex AI Platform                       │
│    gemini-2.5-flash + gemini-1.5-flash               │
│         text-embedding-004                           │
└──────────────────────────────────────────────────────┘
```

---

## 🤖 Agent Details

### WorkBrainPipelineAgent — Orchestrator (ADK CustomAgent)
The orchestrator is implemented as a **custom `BaseAgent`** using ADK's `_run_async_impl` pattern. It:
- Manages the full pipeline lifecycle
- Writes meetings, action items, embeddings, and cognitive states to AlloyDB
- Emits real-time SSE progress events at each step
- Handles overload detection and calendar skip logic
- Passes structured session state between agents using `ctx.session.state`

### transcript_agent — gemini-2.5-flash
- Uses `output_schema=TranscriptOutput` (Pydantic) for guaranteed JSON structure
- Uses `generate_content_config` with `response_mime_type="application/json"`
- Today's date injected via Python (not tool call) for compatibility with output_schema
- Extracts: action items, deadlines, priorities, complexity, focus block requirements

### cognitive_agent — gemini-1.5-flash
- Calls `calculate_cognitive_load` tool implementing Sweller's CLT formula
- Queries AlloyDB MCP Toolbox for historical cognitive state
- Detects overload (>100% capacity) per team member
- Separate quota bucket from 2.5-flash to avoid rate limiting

### scheduler_agent — gemini-2.5-flash
- Uses `GoogleSearchTool(bypass_multi_tools_limit=True)` for APAC holiday detection
- Calls Google Calendar MCP to check free slots and create focus blocks
- Skips calendar blocks for overloaded owners automatically
- Sends real Google Calendar invitations to team member email addresses

### execution_agent — gemini-1.5-flash
- Creates Google Tasks cards via Tasks MCP
- Posts rich Slack notification to `#workbrain-alerts` via Slack MCP (stdio)
- Separate quota bucket for rate limit isolation

---

## 🚀 Key Features

### 📡 Real-time SSE Streaming
- `POST /api/meetings/process` returns an SSE stream directly — no polling
- Pipeline emits progress events: `started` → `progress` (steps 1-4) → `done`
- Frontend shows live progress bar with agent names and step indicators
- HTTP connection stays alive throughout pipeline — solves Cloud Run container shutdown issue

### 🧠 Cognitive Load Theory (Sweller's CLT)
```python
load_score = Σ (complexity × priority × urgency_factor)
             for each pending task

urgency_factor = 2.0 if deadline < 3 days
               = 1.5 if deadline < 7 days
               = 1.2 if deadline < 14 days
               = 1.0 otherwise

capacity = 480 minutes (8 hours)
load_percentage = (load_score / capacity) × 100
overload = load_percentage > 100%
```

### 🌏 APAC-Aware Scheduling
- Google Search grounding with `bypass_multi_tools_limit=True`
- Detects public holidays: India, Singapore, Japan, Australia
- Avoids scheduling focus blocks on holidays and weekends
- Adds buffer days before major APAC holidays

### 🗄️ AlloyDB AI Integration
- Vector embeddings (768 dimensions) via `text-embedding-004`
- `pgvector` operator `<=>` for cosine similarity search
- `pg_trgm` `similarity()` for fuzzy text matching
- MCP Toolbox v0.7.0 with 4 tools over SSE protocol
- Natural language queries via CopilotKit chatbot

### 📎 Multi-format File Upload
- PDF — text extraction using pdfjs in browser
- TXT — direct file read
- VTT (Google Meet) — timestamp stripping
- SRT (Zoom) — sequence number and timestamp stripping
- No backend changes — pure frontend extraction

### 👥 Real Multi-user Calendar Invites
- Team member email mapping in config
- Calendar events include attendees array
- `sendUpdates="all"` sends real Gmail invitations
- Unknown users routed to main account with owner name in description

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, TailwindCSS, CopilotKit AG-UI |
| Backend | FastAPI, Python 3.11, SQLAlchemy async |
| AI Orchestration | Google ADK (Agent Development Kit) |
| LLM | Vertex AI gemini-2.5-flash, gemini-1.5-flash |
| Embeddings | Vertex AI text-embedding-004 |
| Database | AlloyDB AI (PostgreSQL 17 + pgvector + pg_trgm) |
| MCP | MCP Toolbox v0.7.0, Slack MCP, Calendar MCP |
| Infrastructure | Cloud Run, Firebase Hosting, Google Secret Manager |
| Search | Google Search Grounding (bypass_multi_tools_limit) |

---

## 📁 Project Structure

```
workbrain/
├── backend/
│   ├── agents/
│   │   ├── workbrain_pipeline_agent.py  # ADK CustomAgent (BaseAgent) — Orchestrator
│   │   ├── adk_agents.py               # 4 LlmAgents + model config
│   │   ├── adk_runner.py               # Pipeline runner + _run_agent helper
│   │   └── adk_tools.py                # Tool implementations (calendar, cognitive load)
│   ├── tools/
│   │   ├── calendar_tool.py            # Google Calendar API + attendee invites
│   │   └── slack_tool.py               # Slack SDK notification
│   ├── db/
│   │   ├── database.py                 # AsyncSession + pgvector registration
│   │   └── models.py                   # SQLAlchemy models
│   ├── main.py                         # FastAPI + SSE streaming endpoints
│   ├── config.py                       # Settings + team_members email mapping
│   ├── toolbox_config.yaml             # MCP Toolbox SQL tool definitions
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── meetings/ProcessMeetingForm.tsx  # SSE streaming + file upload
│       │   ├── copilot/WorkBrainSidebar.tsx     # CopilotKit chatbot (6 actions)
│       │   ├── dashboard/                       # Cognitive load, decisions, tasks
│       │   └── tasks/AddTaskForm.tsx            # Manual task creation
│       └── lib/api.ts                           # Typed API client
└── README.md
```

---

## 🗄️ Database Schema (AlloyDB AI)

```sql
CREATE SCHEMA workbrain_schema;
CREATE EXTENSION IF NOT EXISTS vector SCHEMA workbrain_schema;
CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA workbrain_schema;

CREATE TABLE workbrain_schema.meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR NOT NULL,
    title VARCHAR,
    transcript TEXT,
    summary TEXT,
    status VARCHAR DEFAULT 'processing',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE workbrain_schema.action_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID REFERENCES workbrain_schema.meetings(id),
    user_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    owner VARCHAR,
    deadline DATE,
    priority INTEGER DEFAULT 3,
    complexity INTEGER DEFAULT 3,
    duration_minutes INTEGER DEFAULT 60,
    needs_focus_block BOOLEAN DEFAULT FALSE,
    status VARCHAR DEFAULT 'pending',
    task_id VARCHAR,
    embedding vector(768),   -- Vertex AI text-embedding-004
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE workbrain_schema.cognitive_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR NOT NULL,
    owner VARCHAR NOT NULL,
    load_score FLOAT DEFAULT 0,
    capacity FLOAT DEFAULT 480,
    load_percentage FLOAT DEFAULT 0,
    overload_flag BOOLEAN DEFAULT FALSE,
    calculated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE workbrain_schema.decisions_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID,
    user_id VARCHAR NOT NULL,
    agent VARCHAR,
    decision TEXT,
    reason TEXT,
    recommendation TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 🔌 MCP Toolbox Configuration

```yaml
sources:
  alloydb-workbrain:
    kind: alloydb-postgres
    project: workbrain-cortexflow-project
    region: us-central1
    cluster: workbrain-cluster
    instance: primary
    database: workbrain

tools:
  get_action_items:
    description: Fetch pending action items by owner from AlloyDB
  get_cognitive_states:
    description: Get current cognitive load state per team member
  find_similar_tasks:
    description: Find similar tasks using pg_trgm text similarity
  get_team_analytics:
    description: Aggregated team metrics and workload summary

toolsets:
  workbrain_db_tools:
    tools: [get_action_items, get_cognitive_states, find_similar_tasks, get_team_analytics]
  cognitive_tools:
    tools: [get_cognitive_states, get_action_items]
```

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/meetings/process` | Process transcript — returns SSE stream |
| GET | `/api/meetings/stream/{job_id}` | SSE progress stream |
| GET | `/api/dashboard` | Full dashboard data |
| GET | `/api/meetings` | List all meetings |
| POST | `/api/tasks` | Add manual task + recalculate cognitive load |
| PATCH | `/api/tasks/{id}` | Update task status |
| POST | `/api/tasks/similar` | Find similar tasks via pg_trgm |
| POST | `/api/tasks/sync-google` | Sync from Google Tasks |
| GET | `/api/health` | Health check — DB + ADK status |

---

## 🚀 Deployment

### Backend (Cloud Run)
```bash
gcloud builds submit ./backend \
  --tag="us-central1-docker.pkg.dev/workbrain-cortexflow-project/workbrain/backend:latest" \
  --project=workbrain-cortexflow-project

gcloud run deploy workbrain-backend \
  --image="us-central1-docker.pkg.dev/workbrain-cortexflow-project/workbrain/backend:latest" \
  --region=us-central1 \
  --service-account="workbrain-sa@workbrain-cortexflow-project.iam.gserviceaccount.com" \
  --min-instances=1 \
  --project=workbrain-cortexflow-project
```

### Frontend (Firebase Hosting)
```bash
cd frontend
npm run build
firebase deploy --only hosting --project workbrain-cortexflow-project
```

---

## 🌐 Live URLs

| Service | URL |
|---------|-----|
| Frontend | https://workbrain-cortexflow-project.web.app |
| Backend API | https://workbrain-backend-114869691007.us-central1.run.app |
| Health Check | https://workbrain-backend-114869691007.us-central1.run.app/health |
| API Docs | https://workbrain-backend-114869691007.us-central1.run.app/docs |

---

## 👥 Team

**CortexFlow** — Google Gen-AI Academy APAC Hackathon 2026

| Name | Role |
|------|------|
| Naveen M | Full Stack + AI Engineering |
| Ravi Kumar | Backend + Infrastructure |
| Sushma M | Frontend + UX |

---

## 📄 License

Apache License 2.0 — See [LICENSE](LICENSE) for details.
