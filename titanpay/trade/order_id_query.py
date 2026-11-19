"""Поиск заявки по ID из кабинета.

В таблице показывается только последний кусок UUID (`formatUUID`), а фильтр
раньше требовал UUID целиком. Из‑за этого вставка видимого ID ничего не находила.
"""
from __future__ import annotations

import uuid

from django.db.models import Q, TextField
from django.db.models.functions import Cast


def apply_order_id_filter(queryset, raw: str, pay_fk: str):
    value = (raw or "").strip()
    if not value:
        return queryset
    try:
        uid = uuid.UUID(value)
    except ValueError:
        uid = None
    if uid is not None:
        return queryset.filter(Q(id=uid) | Q(**{pay_fk: uid}))

    token = value.replace("-", "").lower()
    if len(token) < 8 or any(ch not in "0123456789abcdef" for ch in token):
        return queryset.none()
    return queryset.annotate(
        _order_id_text=Cast("id", TextField()),
        _pay_id_text=Cast(pay_fk, TextField()),
    ).filter(Q(_order_id_text__iendswith=token) | Q(_pay_id_text__iendswith=token))
