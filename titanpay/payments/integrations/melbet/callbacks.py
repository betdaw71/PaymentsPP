from __future__ import annotations

import json
import logging

import requests

from payments.integrations.melbet.crypto import sign_body
from payments.integrations.melbet.mapping import TERMINAL_CALLBACK_STATUSES
from payments.integrations.melbet.models import MelbetTransactionSession

logger = logging.getLogger(__name__)


def _melbet_session_for_payin(pay_in) -> MelbetTransactionSession | None:
    try:
        return pay_in.melbet_session
    except MelbetTransactionSession.DoesNotExist:
        return None


def _melbet_session_for_payout(pay_out) -> MelbetTransactionSession | None:
    try:
        return pay_out.melbet_session
    except MelbetTransactionSession.DoesNotExist:
        return None


def _post_melbet_callback(session: MelbetTransactionSession, callback_url: str) -> int:
    config = session.config
    body_str = json.dumps({"order_id": session.order_id}, separators=(",", ":"))
    body_bytes = body_str.encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": config.public_key,
        "x-signature": sign_body(body_bytes, config.secret_key),
    }
    status_code = 500
    try:
        response = requests.post(callback_url, data=body_bytes, headers=headers, timeout=30)
        status_code = response.status_code
    except Exception as exc:
        logger.error("Melbet callback failed url=%s order_id=%s: %s", callback_url, session.order_id, exc)
    return status_code


def try_send_melbet_payin_callback(pay_in, *, status_name: str | None) -> bool:
    """
    True — callback handled by Melbet integration (standard merchant callback must be skipped).
    False — use standard AvaPay callback.
    """
    session = _melbet_session_for_payin(pay_in)
    if session is None:
        return False
    if status_name not in TERMINAL_CALLBACK_STATUSES:
        return True
    if not pay_in.callback_url:
        return True
    _post_melbet_callback(session, pay_in.callback_url)
    return True


def try_send_melbet_payout_callback(pay_out, *, status_name: str | None) -> bool:
    session = _melbet_session_for_payout(pay_out)
    if session is None:
        return False
    if status_name not in TERMINAL_CALLBACK_STATUSES:
        return True
    if not pay_out.callback_url:
        return True
    _post_melbet_callback(session, pay_out.callback_url)
    return True
