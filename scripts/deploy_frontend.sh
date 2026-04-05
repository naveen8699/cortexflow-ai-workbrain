#!/usr/bin/env bash
# Deploy WorkBrain frontend to Firebase Hosting
set -euo pipefail
source <(grep -E '^[A-Z_]+=' ./backend/.env 2>/dev/null | sed 's/^/export /' || true)
PROJECT_ID="${GCP_PROJECT_ID:-your-project}"

BACKEND_URL=$(gcloud run services describe workbrain-backend --region="${GCP_REGION:-us-central1}" --format="value(status.url)" 2>/dev/null || echo "")
if [ -z "$BACKEND_URL" ]; then
  echo "ERROR: Backend not deployed. Run deploy_backend.sh first."
  exit 1
fi

cat > ./frontend/.env.local << ENV
NEXT_PUBLIC_API_URL=${BACKEND_URL}
NEXT_PUBLIC_COPILOTKIT_URL=${BACKEND_URL}/api/copilotkit
ENV

cd frontend
npm install
npm run build

# Check if firebase CLI is installed
if ! command -v firebase &> /dev/null; then
  npm install -g firebase-tools
fi

firebase use "$PROJECT_ID" 2>/dev/null || firebase init hosting --project "$PROJECT_ID"
firebase deploy --only hosting
FRONTEND_URL=$(firebase hosting:channel:list 2>/dev/null | grep "live" | awk '{print $4}' | head -1 || echo "Check Firebase console")
echo "✓ Frontend deployed: $FRONTEND_URL"
cd ..
