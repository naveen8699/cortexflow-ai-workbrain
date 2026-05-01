#!/usr/bin/env python3
"""WorkBrain End-to-End Test — Run after setup to verify everything works."""
import asyncio, json, sys
import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"

TRANSCRIPT = """Team sync - April 4th
Attendees: Arjun, Priya, Dev

API redesign must be done by April 10th. Arjun owns this. Complex backend task.
Priya prepares demo deck by April 8th. Needs 2 hours uninterrupted focus.
Dev reviews security audit by April 9th. High priority.
Next sync April 11th at 3pm.
Arjun already has 3 other deadlines this week — feeling stretched thin."""

async def run():
    print(f"=== WorkBrain E2E Test | {BASE} ===\n")
    async with httpx.AsyncClient(timeout=120.0) as c:
        # Health
        r = await c.get(f"{BASE}/health")
        assert r.status_code == 200, f"Health failed: {r.status_code}"
        h = r.json()
        print(f"[1/4] Health: {h['status']} | DB: {h['db']} | ADK: {h['adk']}")

        # Process meeting
        print("[2/4] Processing transcript (30-60s for full ADK pipeline)...")
        r = await c.post(f"{BASE}/api/meetings/process",
                         json={"transcript": TRANSCRIPT, "title": "Test sync"})
        assert r.status_code == 201, f"Process failed: {r.status_code} | {r.text[:200]}"
        res = r.json()
        print(f"       ✓ action_items={res['action_items_created']} events={res['events_created']} tasks={res['tasks_created']}")
        print(f"       ✓ overloaded={res['overloaded_owners']}")
        print(f"       ✓ decisions={len(res['decisions'])}")
        for d in res['decisions'][:3]:
            print(f"         [{d['agent']}] {d['decision']}")

        # Dashboard
        r = await c.get(f"{BASE}/api/dashboard")
        assert r.status_code == 200
        dash = r.json()
        print(f"[3/4] Dashboard: meetings={len(dash['meetings'])} tasks={len(dash['action_items'])} cog_states={len(dash['cognitive_states'])}")
        for cs in dash['cognitive_states']:
            flag = "⚠ OVERLOADED" if cs['overload_flag'] else "✓ OK"
            print(f"       {cs['owner']}: {cs['load_percentage']}% {flag}")

        # Add task
        r = await c.post(f"{BASE}/api/tasks",
                         json={"title": "Fix prod bug", "owner": "demo_user",
                               "duration_minutes": 180, "priority": 5, "complexity": 4})
        assert r.status_code == 201
        t = r.json()
        print(f"[4/4] Manual task: {t['action_item']['title']} | load={t['cognitive_state']['load_percentage'] if t['cognitive_state'] else 'N/A'}%")

    print("\n=== ALL TESTS PASSED — WorkBrain is ready! ===")

asyncio.run(run())
