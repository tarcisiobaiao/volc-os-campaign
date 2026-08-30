"""
ClickUp API (v2) — cria a TASK do briefing + anexa o DOCX, ao mover o card
para "Pronto". Server-side ONLY (o token nunca vai pro frontend).

Auth: token pessoal (pk_...) no header `Authorization` — SEM prefixo 'Bearer'.
Docs: https://developer.clickup.com/reference/createtask
      https://developer.clickup.com/reference/createtaskattachment
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from app.config import Settings

API_BASE = "https://api.clickup.com/api/v2"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ClickUpService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.token = settings.clickup_api_token or ""
        self.list_id = settings.clickup_list_id or ""
        self.status = (settings.clickup_task_status or "").strip() or None

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.list_id)

    def _headers(self, json: bool = True) -> Dict[str, str]:
        h = {"Authorization": self.token}
        if json:
            h["Content-Type"] = "application/json"
        return h

    async def create_task(
        self, name: str, *, description: str = "", status: Optional[str] = None,
        list_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        lid = list_id or self.list_id
        body: Dict[str, Any] = {"name": name}
        if description:
            body["description"] = description
        st = status if status is not None else self.status
        if st:
            body["status"] = st
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post(f"{API_BASE}/list/{lid}/task", headers=self._headers(), json=body)
            resp.raise_for_status()
            return resp.json()

    async def upload_attachment(
        self, task_id: str, filename: str, data: bytes, content_type: str = DOCX_MIME,
    ) -> Dict[str, Any]:
        files = {"attachment": (filename, data, content_type)}
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            # multipart => NÃO enviar Content-Type json; só o Authorization
            resp = await client.post(
                f"{API_BASE}/task/{task_id}/attachment",
                headers=self._headers(json=False),
                files=files,
            )
            resp.raise_for_status()
            return resp.json()

    async def add_comment(self, task_id: str, comment_text: str, *, notify_all: bool = False) -> Dict[str, Any]:
        body = {"comment_text": comment_text, "notify_all": notify_all}
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post(f"{API_BASE}/task/{task_id}/comment", headers=self._headers(), json=body)
            resp.raise_for_status()
            return resp.json()
