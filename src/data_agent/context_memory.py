"""受控上下文压缩与用户明确授权的短期记忆存储。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable
from uuid import uuid4


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str
    tenant_id: str
    user_id: str
    content: str
    expires_at: datetime


class MemoryStore:
    """本地进程内实现；生产需替换为持久化且支持撤权的后端。"""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        """注入时钟便于验证 TTL；_items 保存本进程中的记忆。"""
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._items: dict[str, MemoryItem] = {}
        self._lock = RLock()

    def add(self, *, tenant_id: str, user_id: str, content: str, consent: bool, ttl: timedelta) -> str:
        """仅保存用户同意且有明确到期时间的记忆。"""
        if not consent or not tenant_id or not user_id or not content.strip() or ttl <= timedelta(0):
            raise ValueError("记忆需要明确同意、归属、正文和正数有效期")
        memory_id = uuid4().hex
        item = MemoryItem(memory_id, tenant_id, user_id, content[:2000], self.clock() + ttl)
        with self._lock:
            self._items[memory_id] = item
        return memory_id

    def list(self, *, tenant_id: str, user_id: str) -> list[MemoryItem]:
        """按租户、用户与有效期筛选，过期项不会进入模型上下文。"""
        now = self.clock()
        with self._lock:
            return [item for item in self._items.values() if item.tenant_id == tenant_id and item.user_id == user_id and item.expires_at > now]

    def delete(self, memory_id: str, *, tenant_id: str, user_id: str) -> bool:
        """只有归属用户可以删除该条记忆。"""
        with self._lock:
            item = self._items.get(memory_id)
            if item is None or item.tenant_id != tenant_id or item.user_id != user_id:
                return False
            del self._items[memory_id]
            return True


class ContextBuilder:
    def __init__(self, *, max_chars: int = 4000) -> None:
        """设置上下文字符预算；关键事实超过预算时直接拒绝。"""
        if max_chars < 100:
            raise ValueError("上下文预算过小")
        self.max_chars = max_chars

    def build(self, *, goal: str, confirmed: dict[str, str], messages: list[str], evidence_ids: list[str]) -> str:
        """优先保留目标、已确认条件和证据 ID，再容纳最新消息。"""
        facts = json.dumps({"goal": goal, "confirmed": confirmed, "evidence_ids": evidence_ids}, ensure_ascii=False, separators=(",", ":"))
        if len(facts) > self.max_chars:
            raise ValueError("关键事实超过上下文预算，不能静默截断")
        budget = self.max_chars - len(facts)
        recent: list[str] = []
        for message in reversed(messages):
            entry = "\n- " + message
            if len(entry) > budget:
                break
            recent.append(entry)
            budget -= len(entry)
        return facts + "".join(reversed(recent))
