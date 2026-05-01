#!/bin/bash
# Start MCP Toolbox for AlloyDB in background
/app/toolbox --tools-file /app/toolbox_config.yaml --address 0.0.0.0 --port 5000 &
sleep 3
echo "MCP Toolbox started"

# Start FastAPI backend
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --loop asyncio
