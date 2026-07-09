from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.hotel_search import search_hotels, semantic_hotel_search, search_hotels_page, HotelSearchError
from app.config import get_settings
from app.schemas import ChatRequest, ChatResponse, DestinationPricing, DestinationCreate
from app.chatbot import chat
from app.pricing import get_all_destinations, get_all_places, upsert_destination, delete_destination, startup
from app.cache import pricing_cache
from app.fhe import encryption_mode
from app.database import SessionLocal
from app.models import HotelListing
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Automatically create any missing tables (like hotel_listings) on startup
    from app.database import engine
    from app.models import Base
    Base.metadata.create_all(bind=engine)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, startup)
    yield

app = FastAPI(title="Travel Cost Chatbot API", version="4.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def require_admin(authorization: str | None = Header(default=None)):
    expected = f"Bearer {get_settings().admin_password}"
    if authorization != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin password",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
    return {
        "status": "ok",
        "model": settings.agent_model,
        "encryption": encryption_mode(),
        "cache": pricing_cache.stats(),
    }


@app.get("/api/destinations")
async def public_destinations(origin: str | None = None):
    return get_all_destinations(origin)


# ── Admin: origins list (for the dropdown) ────────────────────────────────────

@app.get("/api/admin/places", dependencies=[Depends(require_admin)])
async def list_places():
    return get_all_places()


# ── Admin: destination pricing CRUD (now origin-aware) ────────────────────────

@app.get("/api/admin/destinations", dependencies=[Depends(require_admin)])
async def list_destinations(origin: str | None = None):
    return get_all_destinations(origin)


@app.post("/api/admin/destinations", dependencies=[Depends(require_admin)])
async def create_destination(body: DestinationCreate):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Destination name cannot be empty")
    origin = (body.origin or "Default").strip() or "Default"
    updated = upsert_destination(body.name.strip(), body.pricing.model_dump(), origin)
    return {"destination": body.name.strip(), "origin": origin, "pricing": updated}


@app.put("/api/admin/destinations/{destination}", dependencies=[Depends(require_admin)])
async def update_destination(destination: str, pricing: DestinationPricing, origin: str = "Default"):
    updated = upsert_destination(destination, pricing.model_dump(), origin)
    return {"destination": destination, "origin": origin, "pricing": updated}


@app.delete("/api/admin/destinations/{destination}", dependencies=[Depends(require_admin)])
async def remove_destination(destination: str, origin: str = "Default"):
    if destination == "Default" and origin == "Default":
        raise HTTPException(status_code=400, detail="Cannot delete the Default destination")
    if not delete_destination(destination, origin):
        raise HTTPException(status_code=404, detail=f"Route '{origin}' → '{destination}' not found")
    return {"deleted": destination, "origin": origin}


@app.get("/api/admin/cache/stats", dependencies=[Depends(require_admin)])
async def cache_stats():
    return pricing_cache.stats()


@app.delete("/api/admin/cache", dependencies=[Depends(require_admin)])
async def flush_cache():
    pricing_cache.clear()
    return {"flushed": True}


@app.get("/admin")
async def admin_page():
    return FileResponse("frontend/admin.html")


@app.get("/hotels")
async def hotels_page():
    return FileResponse("frontend/hotels.html")


# ── Public: hotel search ───────────────────────────────────────────────────────

@app.get("/api/hotels/search")
async def hotel_search_endpoint(city: str, query: str | None = None, hotel_name: str | None = None):
    loop = asyncio.get_event_loop()
    try:
        if hotel_name:
            hotels = await loop.run_in_executor(None, search_hotels, city, hotel_name)
        elif query:
            hotels = await loop.run_in_executor(None, semantic_hotel_search, query, city)
        else:
            hotels = await loop.run_in_executor(None, search_hotels, city)
        return {"city": city, "hotels": hotels}
    except HotelSearchError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hotels/search/page")
async def hotel_search_page_endpoint(city: str, page_token: str | None = None):
    try:
        loop = asyncio.get_event_loop()
        hotels, next_token = await loop.run_in_executor(None, search_hotels_page, city, page_token)
        return {"city": city, "hotels": hotels, "next_page_token": next_token}
    except HotelSearchError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Admin: browse cached hotels + force refresh ────────────────────────────────

@app.get("/api/admin/hotels", dependencies=[Depends(require_admin)])
async def list_cached_hotels(city: str | None = None):
    session = SessionLocal()
    try:
        q = session.query(HotelListing)
        if city:
            q = q.filter(HotelListing.city == city)
        rows = q.order_by(HotelListing.city, HotelListing.name).all()
        return [
            {
                "city": r.city,
                "name": r.name,
                "address": r.description,
                "amenities": r.amenities,
                "last_rate_seen": r.last_rate_seen,
                "last_updated": r.last_updated.isoformat() if r.last_updated else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@app.post("/api/admin/hotels/refresh", dependencies=[Depends(require_admin)])
async def refresh_hotels(city: str):
    try:
        hotels = search_hotels(city)
        return {"city": city, "refreshed": len(hotels), "hotels": hotels}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Static Files (CRITICAL: Keep at the very bottom as a fallback) ────────────

app.mount("/", StaticFiles(directory="frontend", html=True), name="static")