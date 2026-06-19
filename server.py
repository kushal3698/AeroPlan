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
import hashlib
import secrets
import uuid
import datetime
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

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

# ---------------------------------------------------------
# DATABASE & AUTHENTICATION HELPER STATE
# ---------------------------------------------------------
DB_FILE = os.path.join(current_dir, "db.json")

# In-memory database fallback in case of read-only environments (e.g., Vercel)
in_memory_db = {
    "users": {},
    "trips": []
}
is_db_persistent = True

def load_db():
    global is_db_persistent
    if not os.path.exists(DB_FILE):
        return in_memory_db
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading db.json, falling back to in-memory: {e}")
        is_db_persistent = False
        return in_memory_db

def save_db(data):
    global is_db_persistent
    if not is_db_persistent:
        return False
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving db.json: {e}. Switching to in-memory fallback.")
        is_db_persistent = False
        return False

# Initialize DB structure if new
db_data = load_db()
if "users" not in db_data:
    db_data["users"] = {}
if "trips" not in db_data:
    db_data["trips"] = []
save_db(db_data)

# Session management
active_sessions = {}  # token -> email

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return hashed, salt

async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
    token = authorization.split(" ")[1]
    if token not in active_sessions:
        raise HTTPException(status_code=401, detail="Session expired or invalid token")
    return active_sessions[token]

# ---------------------------------------------------------
# REQUEST & RESPONSE MODELS
# ---------------------------------------------------------
class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TripSaveRequest(BaseModel):
    trip_name: str
    destination: str
    duration_days: int
    budget_limit: float
    currency: str
    language: str
    interests: List[str]
    itinerary_data: dict

class RenameTripRequest(BaseModel):
    trip_name: str

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
        await asyncio.sleep(0.1)
        
        try:
            for output in agent_app.stream(inputs):
                for node_name, state_update in output.items():
                    yield f"data: {json.dumps({'event': 'node_start', 'node': node_name})}\n\n"
                    await asyncio.sleep(0.2)
                    
                    payload = {
                        'event': 'node_complete',
                        'node': node_name,
                        'data': state_update
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    await asyncio.sleep(0.1)
            
            yield f"data: {json.dumps({'event': 'end', 'message': 'Planning completed successfully!'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/auth/signup")
async def signup(req: SignupRequest):
    db_data = load_db()
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    if email in db_data["users"]:
        raise HTTPException(status_code=400, detail="An account with this email already exists")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
    pwd_hash, salt = hash_password(req.password)
    db_data["users"][email] = {
        "password_hash": pwd_hash,
        "salt": salt,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    save_db(db_data)
    
    token = secrets.token_hex(32)
    active_sessions[token] = email
    return {"status": "ok", "token": token, "email": email, "is_persistent": is_db_persistent}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    db_data = load_db()
    email = req.email.strip().lower()
    if email not in db_data["users"]:
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    user_info = db_data["users"][email]
    pwd_hash, _ = hash_password(req.password, user_info["salt"])
    if pwd_hash != user_info["password_hash"]:
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    token = secrets.token_hex(32)
    active_sessions[token] = email
    return {"status": "ok", "token": token, "email": email, "is_persistent": is_db_persistent}

@app.get("/api/trips")
async def get_trips(email: str = Depends(get_current_user)):
    db_data = load_db()
    user_trips = [t for t in db_data["trips"] if t.get("user_email") == email]
    user_trips.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"status": "ok", "trips": user_trips, "is_persistent": is_db_persistent}

@app.post("/api/trips")
async def save_trip(req: TripSaveRequest, email: str = Depends(get_current_user)):
    db_data = load_db()
    trip_id = f"trip_{uuid.uuid4().hex[:12]}"
    new_trip = {
        "id": trip_id,
        "user_email": email,
        "trip_name": req.trip_name,
        "destination": req.destination,
        "duration_days": req.duration_days,
        "budget_limit": req.budget_limit,
        "currency": req.currency,
        "language": req.language,
        "interests": req.interests,
        "itinerary_data": req.itinerary_data,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    db_data["trips"].append(new_trip)
    saved = save_db(db_data)
    return {"status": "ok", "trip": new_trip, "is_persistent": saved}

@app.put("/api/trips/{trip_id}")
async def rename_trip(trip_id: str, req: RenameTripRequest, email: str = Depends(get_current_user)):
    db_data = load_db()
    for trip in db_data["trips"]:
        if trip.get("id") == trip_id and trip.get("user_email") == email:
            trip["trip_name"] = req.trip_name
            saved = save_db(db_data)
            return {"status": "ok", "trip": trip, "is_persistent": saved}
    raise HTTPException(status_code=404, detail="Trip not found or unauthorized")

@app.delete("/api/trips/{trip_id}")
async def delete_trip(trip_id: str, email: str = Depends(get_current_user)):
    db_data = load_db()
    new_trips = []
    found = False
    for trip in db_data["trips"]:
        if trip.get("id") == trip_id and trip.get("user_email") == email:
            found = True
        else:
            new_trips.append(trip)
            
    if not found:
        raise HTTPException(status_code=404, detail="Trip not found or unauthorized")
        
    db_data["trips"] = new_trips
    saved = save_db(db_data)
    return {"status": "ok", "message": "Trip deleted successfully", "is_persistent": saved}

@app.get("/api/config")
async def get_config():
    return {
        "is_mock": is_mock,
        "google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", ""),
        "is_db_persistent": is_db_persistent
    }

# Mount static web directory
app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Server running on http://localhost:{port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
