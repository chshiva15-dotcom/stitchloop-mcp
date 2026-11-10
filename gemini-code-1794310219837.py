import os
import json
import random
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastmcp import FastMCP

STATE_FILE = Path("stitchloop_state.json")

DEFAULT_STATE = {
    "profiles": {
        "SYNC-SHIVA-904": {
            "sync_id": "SYNC-SHIVA-904",
            "name": "Shiva Chinthala",
            "age": 27,
            "gender": "Male",
            "location": "Madhapur, Hyderabad",
            "verified": False,
            "verified_by": None,
            "unit": "in",
            "measurements": {
                "neck": 15.5, "shoulder": 18.0, "chest": 40.0,
                "sleeve": 25.0, "length": 29.0, "waist": 32.0,
                "hips": 39.0, "inseam": 30.0, "outseam": 40.5,
                "thigh": 22.5, "cuff": 14.0
            },
            "notes": "Slight right shoulder drop; prefers slim-tapered trouser ankle."
        }
    },
    "orders": [
        {
            "id": "SL-201",
            "customer_name": "Shiva Chinthala",
            "sync_id": "SYNC-SHIVA-904",
            "purpose": "Alteration & Fitting",
            "fabric": "Cotton / Linen",
            "item_count": 2,
            "description": "Take in waist by 1.5 inches and taper ankle on 2 formal trousers.",
            "budget": 320,
            "radius_km": 3.0,
            "logistics": "Doorstep Pickup",
            "pickup_fee": 45,
            "custody_otp": "4829",
            "status": "Counter-Offered",
            "rejections": [
                {
                    "operator": "Master Rafiq Tailors",
                    "reason": "Budget too low for double-stitched trouser tapering",
                    "counter_offer": 440
                }
            ],
            "assigned_operator": None,
            "assigned_driver": None
        }
    ]
}

def load_state() -> dict:
    if not STATE_FILE.exists():
        save_state(DEFAULT_STATE)
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))

def save_state(data: dict) -> None:
    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

# Initialize FastMCP Server
mcp = FastMCP("StitchLoop Hyperlocal Tailor Marketplace")

@mcp.tool()
def broadcast_garment_request(
    customer_name: str,
    purpose: str,
    fabric: str,
    item_count: int,
    description: str,
    budget_inr: int,
    radius_km: float = 3.0,
    logistics: str = "Doorstep Pickup",
    sync_id: str = "SYNC-SHIVA-904"
) -> dict:
    """Broadcast a tailoring, alteration, or dyeing request to nearby artisans within city limits."""
    state = load_state()
    new_id = f"SL-{random.randint(300, 999)}"
    otp = str(random.randint(1000, 9999)) if logistics == "Doorstep Pickup" else None
    order = {
        "id": new_id,
        "customer_name": customer_name,
        "sync_id": sync_id,
        "purpose": purpose,
        "fabric": fabric,
        "item_count": item_count,
        "description": description,
        "budget": budget_inr,
        "radius_km": radius_km,
        "logistics": logistics,
        "pickup_fee": 45 if logistics == "Doorstep Pickup" else 0,
        "custody_otp": otp,
        "status": "Broadcasted",
        "rejections": [],
        "assigned_operator": None,
        "assigned_driver": None
    }
    state["orders"].insert(0, order)
    save_state(state)
    return {"message": f"Order {new_id} broadcasted within {radius_km}km.", "order": order}

@mcp.tool()
def log_operator_response(
    order_id: str,
    operator_name: str,
    decision: str,
    rejection_reason: Optional[str] = None,
    counter_offer_inr: Optional[int] = None
) -> dict:
    """Record a tailor's Acceptance or Rejection (with mandatory reason and optional counter-offer)."""
    state = load_state()
    for order in state["orders"]:
        if order["id"].upper() == order_id.upper():
            if decision.lower() == "accept":
                order["status"] = "Accepted by Tailor"
                order["assigned_operator"] = operator_name
            else:
                order["status"] = "Counter-Offered" if counter_offer_inr else "Declined"
                order["rejections"].append({
                    "operator": operator_name,
                    "reason": rejection_reason or "Schedule capacity full",
                    "counter_offer": counter_offer_inr
                })
            save_state(state)
            return {"message": f"Recorded {decision} for {order_id}", "order": order}
    return {"error": f"Order {order_id} not found."}

@mcp.tool()
def sync_tailor_measurements(
    sync_id: str,
    tailor_shop_name: str,
    chest: float,
    waist: float,
    shoulder: float,
    inseam: float,
    posture_notes: str = "Verified via physical tape calibration"
) -> dict:
    """Sync walk-in physical tailor measurements directly into the customer's digital profile vault."""
    state = load_state()
    profile = state["profiles"].get(sync_id)
    if not profile:
        return {"error": f"Sync ID {sync_id} not found."}
    profile["measurements"].update({
        "chest": chest,
        "waist": waist,
        "shoulder": shoulder,
        "inseam": inseam
    })
    profile["verified"] = True
    profile["verified_by"] = tailor_shop_name
    profile["notes"] = posture_notes
    save_state(state)
    return {"message": f"Profile {sync_id} verified by {tailor_shop_name}", "profile": profile}

@mcp.tool()
def dispatch_delivery_agent(order_id: str, driver_name: str = "Lakshmi Devi (Neighborhood Partner)") -> dict:
    """Assign a household gig partner for city-limits garment pickup and return."""
    state = load_state()
    for order in state["orders"]:
        if order["id"].upper() == order_id.upper():
            order["assigned_driver"] = driver_name
            order["status"] = "Driver Assigned (Out for Pickup)"
            save_state(state)
            return {"message": f"Assigned {driver_name} to {order_id}", "order": order}
    return {"error": f"Order {order_id} not found."}

# Mount MCP HTTP app and REST Endpoints for the Web Dashboard
mcp_app = mcp.http_app(path="/mcp")
app = FastAPI(title="StitchLoop MCP Backend", lifespan=mcp_app.lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/state")
def get_state():
    return JSONResponse(load_state())

@app.post("/api/override/{order_id}")
def human_override_order(order_id: str, payload: dict = Body(...)):
    state = load_state()
    for order in state["orders"]:
        if order["id"].upper() == order_id.upper():
            if "budget" in payload:
                order["budget"] = int(payload["budget"])
            if "status" in payload:
                order["status"] = payload["status"]
            if "assigned_operator" in payload:
                order["assigned_operator"] = payload["assigned_operator"]
            save_state(state)
            return {"status": "updated", "order": order}
    return JSONResponse({"error": "Not found"}, status_code=404)

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    index_path = Path("index.html")
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>StitchLoop MCP Server Running</h1>"

app.mount("/", mcp_app)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)