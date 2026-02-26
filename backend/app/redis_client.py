from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import redis

from app.config import get_settings


class MemoryStore:
    """
    Simple session memory backed by Redis (if configured) with in-process dict fallback.
    Stores the last N chat turns per session_id.
    """

    def __init__(self) -> None:
        self._redis: Optional[redis.Redis] = None
        self._inmem: Dict[str, List[Dict[str, Any]]] = {}
        self._initialized = False

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        s = get_settings()
        if s.redis_url:
            try:
                self._redis = redis.from_url(s.redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None  # fallback to in-memory

    def get_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        self._ensure_init()
        if self._redis:
            raw = self._redis.get(session_id)
            if not raw:
                return []
            data = json.loads(raw)
            return data[-limit:]
        return self._inmem.get(session_id, [])[-limit:]

    def append(self, session_id: str, message: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        self._ensure_init()
        history = self.get_history(session_id, limit=limit)
        history.append(message)
        history = history[-limit:]

        if self._redis:
            self._redis.set(session_id, json.dumps(history))
        else:
            self._inmem[session_id] = history
        return history

    def clear(self, session_id: str) -> None:
        self._ensure_init()
        if self._redis:
            self._redis.delete(session_id)
        else:
            self._inmem.pop(session_id, None)


memory_store = MemoryStore()
