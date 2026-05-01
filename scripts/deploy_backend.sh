#!/usr/bin/env bash
# WorkBrain — Deploy backend to Cloud Run
# Updated for: instance=csql-workbrain, user=workbrain_user, schema=workbrain_schema
set -euo pipefail

# Load .env values as shell variables
source <(grep -E '^[A-Z_]+=' ./backend/.env 2>/dev/null | sed 's/^/export /' || true)

PROJECT_ID="${GCP_PROJECT_ID:-your-project}"
REGION="${GCP_REGION:-us-central1}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/workbrain/backend"
SA_EMAIL="workbrain-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# ── Use the actual Cloud SQL instance name ────────────────────────────────────
# Instance connection name format: PROJECT:REGION:INSTANCE_ID
DB_INSTANCE="${CLOUD_SQL_INSTANCE:-${PROJECT_ID}:${REGION}:csql-workbrain}"

echo "=== WorkBrain Backend Deploy ==="
echo "  Project  : $PROJECT_ID"
echo "  Region   : $REGION"
echo "  Image    : $IMAGE"
echo "  SQL inst : $DB_INSTANCE"
echo "  DB user  : workbrain_user"
echo "  Schema   : workbrain_schema"
echo ""

# ── Build and push Docker image ───────────────────────────────────────────────
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build -t "$IMAGE:latest" ./backend/
docker push "$IMAGE:latest"
echo "✓ Image pushed: $IMAGE:latest"

# ── Store DB_PASSWORD in Secret Manager if not already there ──────────────────
DB_PW="${DB_PASSWORD:-}"
if [ -n "$DB_PW" ]; then
  echo -n "$DB_PW" | gcloud secrets create workbrain-db-password \
    --data-file=- --quiet 2>/dev/null || \
  echo -n "$DB_PW" | gcloud secrets versions add workbrain-db-password \
    --data-file=- --quiet
  echo "✓ DB password stored in Secret Manager"
fi

# ── Deploy to Cloud Run ───────────────────────────────────────────────────────
gcloud run deploy workbrain-backend \
  --image="$IMAGE:latest" \
  --platform=managed \
  --region="$REGION" \
  --service-account="$SA_EMAIL" \
  --add-cloudsql-instances="$DB_INSTANCE" \
  --set-env-vars="\
GCP_PROJECT_ID=${PROJECT_ID},\
GCP_REGION=${REGION},\
APP_ENV=production,\
USER_ID=demo_user,\
DB_USER=workbrain_user,\
DB_NAME=workbrain,\
DB_SCHEMA=workbrain_schema,\
CLOUD_SQL_INSTANCE=${DB_INSTANCE},\
VERTEX_AI_MODEL=gemini-2.0-flash-001,\
VERTEX_AI_LOCATION=${REGION},\
DAILY_CAPACITY_MINUTES=480,\
OVERLOAD_THRESHOLD=0.85" \
  --set-secrets="DB_PASSWORD=workbrain-db-password:latest" \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=1 \
  --max-instances=10 \
  --timeout=300 \
  --allow-unauthenticated \
  --quiet

URL=$(gcloud run services describe workbrain-backend \
  --region="$REGION" --format="value(status.url)")

echo ""
echo "=== Deploy complete ==="
echo "  URL   : $URL"
echo "  Health: curl ${URL}/health"
echo ""
echo "Test pipeline:"
echo "  curl -X POST ${URL}/api/meetings/process \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"transcript\": \"Team sync. Arjun owns API redesign by Apr 10.\"}'"
