"""Поиск заявки по ID из кабинета.

В таблице показывается последний кусок UUID (`formatUUID`). PayIn висит на
заявке обратной связью `pay_in`, поля `pay_in_id` у InOrder нет. Фильтр по
несуществующему полю ронял список с FieldError и ответом 500.
"""
from __future__ import annotations

import uuid

from django.db.models import Q, TextField, Value
from django.db.models.functions import Cast, Replace


def apply_order_id_filter(queryset, raw: str, pay_relation: str):
    value = (raw or "").strip()
    if not value:
        return queryset

    rel = queryset.model._meta.get_field(pay_relation)
    pay_model = rel.related_model
    owner_fk = f"{rel.field.name}_id"

    try:
        uid = uuid.UUID(value)
    except ValueError:
        uid = None
    if uid is not None:
        linked_orders = pay_model.objects.filter(id=uid).values(owner_fk)
        return queryset.filter(Q(id=uid) | Q(id__in=linked_orders))

    token = value.replace("-", "").lower()
    if len(token) < 8 or any(ch not in "0123456789abcdef" for ch in token):
        return queryset.none()

    order_ids = queryset.model.objects.annotate(_id_hex=_hex_uuid("id")).filter(
        _id_hex__iendswith=token
    ).values("id")
    linked_orders = pay_model.objects.annotate(_id_hex=_hex_uuid("id")).filter(
        _id_hex__iendswith=token
    ).values(owner_fk)
    return queryset.filter(Q(id__in=order_ids) | Q(id__in=linked_orders))


def _hex_uuid(field_name: str):
    return Replace(
        Cast(field_name, TextField()),
        Value("-"),
        Value(""),
        output_field=TextField(),
    )
