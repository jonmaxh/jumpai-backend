import asyncio
from collections import defaultdict
from typing import Dict, List, Any


_subscribers: Dict[int, List[asyncio.Queue]] = defaultdict(list)


def subscribe(user_id: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers[user_id].append(queue)
    return queue


def unsubscribe(user_id: int, queue: asyncio.Queue) -> None:
    queues = _subscribers.get(user_id)
    if not queues:
        return
    if queue in queues:
        queues.remove(queue)
    if not queues:
        _subscribers.pop(user_id, None)


def publish(user_id: int, payload: Dict[str, Any]) -> None:
    queues = _subscribers.get(user_id, [])
    for queue in list(queues):
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            continue
