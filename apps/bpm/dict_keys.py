"""Внутренний код записи справочника по главному полю (без ручного lookup)."""

from __future__ import annotations

import re
import uuid

from django.utils.text import slugify


def slug_base(text: str, max_len: int = 72) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    s = slugify(t.replace(".", "-"))
    if not s:
        s = re.sub(r"[^\w\-]+", "-", t, flags=re.UNICODE).strip("-").lower()[:max_len]
    return (s or "row")[:max_len]


def unique_lookup_key(dictionary_id: int, base: str, exclude_record_id: int | None = None) -> str:
    """Гарантирует уникальность (dictionary_id, lookup_key) в DictionaryRecords."""
    from .models import DictionaryRecord

    candidate = base[:255] or "row"
    qs = DictionaryRecord.objects.filter(dictionary_id=dictionary_id, lookup_key=candidate)
    if exclude_record_id:
        qs = qs.exclude(record_id=exclude_record_id)
    if not qs.exists():
        return candidate
    suffix = uuid.uuid4().hex[:8]
    tail = f"-{suffix}"
    candidate = (base[: 255 - len(tail)] + tail)[:255]
    return candidate
