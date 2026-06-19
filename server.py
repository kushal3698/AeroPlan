import os
import sys

# Reconfigure stdout and stderr to use UTF-8 to prevent encoding errors on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from agent import app as agent_app, is_mock

# Get absolute path to the directory containing server.py
current_dir = os.path.dirname(os.path.abspath(__file__))
web_dir = os.path.join(current_dir, "web")

# Ensure the web directory exists
if not os.path.exists(web_dir):
    os.makedirs(web_dir)

app = FastAPI(title="LangGraph Travel Planner API")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PlanRequest(BaseModel):
    destination: str
    duration_days: int
    interests: List[str]
    budget_limit: float
    currency: str
    language: str

@app.post("/api/plan")
async def plan_trip(req: PlanRequest):
    async def event_generator():
        inputs = {
            "destination": req.destination,
            "duration_days": req.duration_days,
            "interests": req.interests,
            "budget_limit": req.budget_limit,
            "currency": req.currency,
            "language": req.language,
            "messages": []
        }
        
        # Send initial status
        yield f"data: {json.dumps({'event': 'start', 'message': 'Supervisor initializing nodes...'})}\n\n"
        await asyncio.sleep(0.8)
        
        try:
            for output in agent_app.stream(inputs):
                for node_name, state_update in output.items():
                    yield f"data: {json.dumps({'event': 'node_start', 'node': node_name})}\n\n"
                    await asyncio.sleep(1.5)
                    
                    payload = {
                        'event': 'node_complete',
                        'node': node_name,
                        'data': state_update
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    await asyncio.sleep(0.8)
            
            yield f"data: {json.dumps({'event': 'end', 'message': 'Planning completed successfully!'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/config")
async def get_config():
    return {
        "is_mock": is_mock,
        "google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", "")
    }

# Mount static web directory
app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Server running on http://localhost:{port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
