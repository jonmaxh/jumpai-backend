import asyncio
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from app.models import User
from app.routers.auth import get_current_user
from app.services.events import subscribe, unsubscribe


router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/stream")
async def stream_events(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    queue = subscribe(current_user.id)

    async def event_generator():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                event_name = payload.get("event", "message")
                data = json.dumps(payload)
                yield f"event: {event_name}\ndata: {data}\n\n"
        finally:
            unsubscribe(current_user.id, queue)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )
