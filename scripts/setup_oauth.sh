#!/usr/bin/env bash
# WorkBrain Google OAuth Setup for Calendar + Tasks APIs
# Run AFTER setup_gcp.sh

set -euo pipefail
source <(grep -E '^[A-Z_]+=' ./backend/.env 2>/dev/null | sed 's/^/export /' || true)
PROJECT_ID="${GCP_PROJECT_ID:-your-project}"

echo "=== Google OAuth Setup ==="
echo ""
echo "Step 1: Create OAuth credentials"
echo "  → Go to: https://console.cloud.google.com/apis/credentials?project=${PROJECT_ID}"
echo "  → Click: Create Credentials → OAuth 2.0 Client ID"
echo "  → Application type: Desktop app"
echo "  → Name: WorkBrain"
echo "  → Download JSON → save as: backend/credentials.json"
echo ""
echo "Press ENTER when done..."
read -r

if [ ! -f "./backend/credentials.json" ]; then
  echo "ERROR: backend/credentials.json not found"
  exit 1
fi

CLIENT_ID=$(python3 -c "import json; d=json.load(open('./backend/credentials.json')); print(d.get('installed',d.get('web',{})).get('client_id',''))")
CLIENT_SECRET=$(python3 -c "import json; d=json.load(open('./backend/credentials.json')); print(d.get('installed',d.get('web',{})).get('client_secret',''))")

# Add to .env
echo "GOOGLE_OAUTH_CLIENT_ID=${CLIENT_ID}" >> ./backend/.env
echo "GOOGLE_OAUTH_CLIENT_SECRET=${CLIENT_SECRET}" >> ./backend/.env
echo "✓ OAuth credentials added to .env"

echo ""
echo "Step 2: Running OAuth flow (browser will open)..."
cd backend
source venv/bin/activate 2>/dev/null || true
python3 -c "from tools.calendar_tool import setup_oauth; setup_oauth()"
cd ..

echo ""
echo "Step 3: Testing Calendar + Tasks APIs..."
cd backend
python3 << 'PYEOF'
from datetime import datetime, timezone, timedelta
from tools.calendar_tool import create_calendar_event_api, create_task_api

now = datetime.now(timezone.utc)
ev = create_calendar_event_api("WorkBrain Test Event", now + timedelta(hours=1), now + timedelta(hours=2), "Setup test")
print(f"✓ Calendar event: {ev['status']} | ID: {ev['event_id']}")

task = create_task_api("WorkBrain Test Task", notes="Setup verification")
print(f"✓ Task: {task['status']} | ID: {task['task_id']}")
print("Check your Google Calendar and Tasks!")
PYEOF
cd ..
echo ""
echo "=== OAuth setup complete! ==="
