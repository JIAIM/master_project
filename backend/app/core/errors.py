"""Повідомлення про помилки перевірки даних українською."""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

FIELD_NAMES = {
    "email": "Email", "password": "Пароль", "full_name": "ПІБ", "role": "Роль",
    "title": "Назва", "description": "Опис", "material_ids": "Матеріали", "text": "Текст",
    "options": "Варіанти відповіді", "points": "Бали", "time_limit_sec": "Час на питання",
    "default_time_limit_sec": "Час на питання", "explanation": "Пояснення", "difficulty": "Складність",
    "type": "Тип питання", "single_choice_count": "Кількість питань з однією відповіддю",
    "true_false_count": "Кількість питань «правда/неправда»", "topic": "Тема", "language": "Мова",
    "pin": "PIN", "display_name": "Ім'я", "option_ids": "Відповідь", "time_limit_min": "Ліміт часу",
    "distraction_threshold_sec": "Поріг відволікання", "test_id": "Тест", "format": "Формат",
    "answers": "Параметр відповідей", "action": "Дія", "instruction": "Інструкція", "question_ids": "Питання",
    "file": "Файл",
}


def _chars(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} символ"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} символи"
    return f"{n} символів"


def _field(loc: tuple[Any, ...]) -> str:
    for part in reversed(loc):
        if isinstance(part, str) and part not in ("body", "query", "path"):
            return FIELD_NAMES.get(part, part)
    return ""


def translate(err: dict[str, Any]) -> str:
    kind = err.get("type", "")
    ctx = err.get("ctx") or {}
    field = _field(tuple(err.get("loc", ())))
    prefix = f"{field}: " if field else ""

    if kind == "value_error":
        msg = str(err.get("msg", ""))
        if "email" in msg.lower() or field == "Email":
            return "Email: некоректна адреса електронної пошти"
        return msg.removeprefix("Value error, ")
    if kind == "missing":
        return f"{prefix}обов'язкове поле"
    if kind == "string_too_short":
        n = ctx.get("min_length", 1)
        return f"{prefix}не може бути порожнім" if n <= 1 else f"{prefix}щонайменше {_chars(n)}"
    if kind == "string_too_long":
        return f"{prefix}не більше {_chars(int(ctx.get('max_length', 0)))}"
    if kind == "string_pattern_mismatch":
        return "PIN: має складатися з 6 цифр" if field == "PIN" else f"{prefix}неправильний формат"
    if kind in ("too_short", "list_too_short"):
        return f"{prefix}потрібно щонайменше {ctx.get('min_length', 1)}"
    if kind in ("too_long", "list_too_long"):
        return f"{prefix}не більше {ctx.get('max_length')}"
    if kind == "greater_than_equal":
        return f"{prefix}не менше {ctx.get('ge')}"
    if kind == "less_than_equal":
        return f"{prefix}не більше {ctx.get('le')}"
    if kind == "greater_than":
        return f"{prefix}має бути більше {ctx.get('gt')}"
    if kind == "less_than":
        return f"{prefix}має бути менше {ctx.get('lt')}"
    if kind in ("int_parsing", "int_type", "float_parsing", "float_type", "int_from_float"):
        return f"{prefix}має бути числом"
    if kind in ("bool_parsing", "bool_type"):
        return f"{prefix}має бути «так» або «ні»"
    if kind in ("list_type", "dict_type", "model_type", "string_type", "model_attributes_type"):
        return f"{prefix}неправильний тип даних"
    if kind in ("enum", "literal_error"):
        return f"{prefix}недопустиме значення"
    if kind in ("json_invalid", "json_type"):
        return "Некоректні дані запиту"
    return f"{prefix}некоректне значення"


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [{"loc": list(e.get("loc", ())), "msg": translate(e), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})
