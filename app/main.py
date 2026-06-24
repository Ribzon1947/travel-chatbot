from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.schemas import ChatRequest, ChatResponse, DestinationPricing, DestinationCreate
from app.chatbot import chat
from app.pricing import get_all_destinations, upsert_destination, delete_destination

settings = get_settings()

app = FastAPI(title="Travel Cost Chatbot API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Admin auth dependency ─────────────────────────────────────────────────────

async def require_admin(authorization: str | None = Header(default=None)):
    expected = f"Bearer {get_settings().admin_password}"
    if authorization != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin password",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    history = [{"role": m.role, "content": m.content} for m in body.history]
    try:
        reply = await chat(body.message, history, body.from_location, body.to_location)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(reply=reply)


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": settings.agent_model}


# ── Public: list destinations (prices are shown in the chat UI) ──────────────

@app.get("/api/destinations")
async def public_destinations():
    return get_all_destinations()


# ── Admin: destination pricing CRUD (password-protected) ─────────────────────

@app.get("/api/admin/destinations", dependencies=[Depends(require_admin)])
async def list_destinations():
    return get_all_destinations()


@app.post("/api/admin/destinations", dependencies=[Depends(require_admin)])
async def create_destination(body: DestinationCreate):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Destination name cannot be empty")
    updated = upsert_destination(body.name.strip(), body.pricing.model_dump())
    return {"destination": body.name.strip(), "pricing": updated}


@app.put("/api/admin/destinations/{destination}", dependencies=[Depends(require_admin)])
async def update_destination(destination: str, pricing: DestinationPricing):
    updated = upsert_destination(destination, pricing.model_dump())
    return {"destination": destination, "pricing": updated}


@app.delete("/api/admin/destinations/{destination}", dependencies=[Depends(require_admin)])
async def remove_destination(destination: str):
    if destination == "Default":
        raise HTTPException(status_code=400, detail="Cannot delete the Default destination")
    if not delete_destination(destination):
        raise HTTPException(status_code=404, detail=f"Destination '{destination}' not found")
    return {"deleted": destination}


# ── Frontend static files (used on Render — serves index.html and admin.html) ─

@app.get("/admin")
async def admin_page():
    return FileResponse("frontend/admin.html")

app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
