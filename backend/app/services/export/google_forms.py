"""Експорт тесту в Google Форми через веб-застосунок Google Apps Script."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import httpx

from app.services.export.documents import ExportTest


class GoogleFormsError(Exception):
    """Помилка, яку можна показати викладачу без змін."""


@dataclass(frozen=True)
class GoogleForm:
    form_id: str
    edit_url: str
    respond_url: str
    shared: str          # editor — викладач став редактором; link — редагування за посиланням


def build_payload(test: ExportTest, teacher_email: str, secret: str) -> dict:
    return {
        "secret": secret,
        "title": test.title,
        "description": test.description or "",
        "teacher_email": teacher_email,
        "questions": [
            {"type": q.type, "text": q.text, "points": 1, "explanation": q.explanation or "",
             "options": [asdict(o) for o in q.options]}
            for q in test.questions
        ],
    }


async def create_google_form(
    test: ExportTest, teacher_email: str, script_url: str, secret: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GoogleForm:
    if not script_url or not secret:
        raise GoogleFormsError(
            "Експорт у Google Форми не налаштовано: додайте GOOGLE_APPS_SCRIPT_URL і "
            "GOOGLE_APPS_SCRIPT_SECRET у .env (інструкція — integrations/google_forms/README.md)"
        )
    try:
        # Apps Script відповідає переадресацією 302 — httpx її проходить
        async with httpx.AsyncClient(timeout=90, follow_redirects=True, transport=transport) as client:
            resp = await client.post(script_url, json=build_payload(test, teacher_email, secret))
    except httpx.HTTPError as exc:
        raise GoogleFormsError(f"Не вдалося зв'язатися з Google Apps Script: {exc}") from exc
    try:
        data = resp.json()
    except ValueError:
        raise GoogleFormsError(
            "Скрипт повернув не JSON — перевірте, що веб-застосунок розгорнуто з доступом «Усі» "
            "і URL закінчується на /exec"
        ) from None
    if not data.get("ok"):
        raise GoogleFormsError(f"Google Apps Script: {data.get('error', 'невідома помилка')}")
    return GoogleForm(form_id=data["form_id"], edit_url=data["edit_url"],
                      respond_url=data["respond_url"], shared=data.get("shared", "editor"))
