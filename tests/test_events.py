import asyncio
import pytest
from starlette.requests import Request

from app.routers.events import stream_events
from app.services.events import subscribe, publish, unsubscribe


@pytest.mark.asyncio
async def test_events_publish_delivers_payload():
    queue = subscribe(1)
    publish(1, {"event": "test_event", "value": 123})

    payload = await asyncio.wait_for(queue.get(), timeout=1)
    assert payload["event"] == "test_event"
    assert payload["value"] == 123

    unsubscribe(1, queue)


def test_events_stream_requires_auth(client):
    response = client.get("/api/events/stream")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_events_stream_returns_event_stream(test_user):
    request = Request({"type": "http", "headers": []})
    response = await stream_events(request, current_user=test_user)
    assert response.media_type == "text/event-stream"
