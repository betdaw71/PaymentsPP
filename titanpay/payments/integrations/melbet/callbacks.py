from __future__ import annotations

import json
import logging

import requests
from django.db import transaction

from payments.integrations.melbet.crypto import sign_body
from payments.integrations.melbet.mapping import TERMINAL_CALLBACK_STATUSES
from payments.integrations.melbet.models import MelbetIntegrationConfig, MelbetTransactionSession

logger = logging.getLogger(__name__)


def _melbet_session_for_payin(pay_in) -> MelbetTransactionSession | None:
    try:
        return pay_in.melbet_session
    except MelbetTransactionSession.DoesNotExist:
        return None
    except AttributeError:
        return None


def _melbet_session_for_payout(pay_out) -> MelbetTransactionSession | None:
    try:
        return pay_out.melbet_session
    except MelbetTransactionSession.DoesNotExist:
        return None
    except AttributeError:
        return None


def _melbet_config_for_merchant(merchant) -> MelbetIntegrationConfig | None:
    if merchant is None:
        return None
    try:
        return merchant.melbet_integration
    except MelbetIntegrationConfig.DoesNotExist:
        return None
    except AttributeError:
        return None


def _order_id_candidates(order_id: str) -> list[str]:
    raw = (order_id or "").strip()
    if not raw:
        return []
    out = [raw]
    if raw.lower().startswith("w") and raw[1:].isdigit():
        out.append(raw[1:])
    elif raw.isdigit():
        out.append(f"w{raw}")
        out.append(f"W{raw}")
    if raw != raw.lower():
        out.append(raw.lower())
    if raw != raw.upper():
        out.append(raw.upper())
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def ensure_melbet_payout_session(pay_out) -> MelbetTransactionSession | None:
    """
    Melbet payout CB требует MelbetTransactionSession.
    Сессия создаётся при Melbet withdrawal create; если потеряна — восстановить
    по merchant MelbetIntegrationConfig, иначе Melbet получит AvaPay-формат и проигнорирует.
    """
    session = _melbet_session_for_payout(pay_out)
    if session is not None:
        return session

    moid = (getattr(pay_out, "merchant_order_id", None) or "").strip()
    for oid in _order_id_candidates(moid):
        session = (
            MelbetTransactionSession.objects.filter(order_id=oid)
            .select_related("config")
            .first()
        )
        if session is None:
            continue
        if session.pay_out_id and session.pay_out_id != pay_out.id:
            logger.warning(
                "Melbet session order_id=%s linked to other PayOut=%s (want %s)",
                oid,
                session.pay_out_id,
                pay_out.id,
            )
            continue
        if session.pay_out_id is None:
            session.pay_out = pay_out
            session.save(update_fields=["pay_out"])
            logger.info("Reattached Melbet payout session order_id=%s pay_out=%s", oid, pay_out.id)
        return session

    config = _melbet_config_for_merchant(getattr(pay_out, "merchant", None))
    if config is None:
        return None

    details = pay_out.details if isinstance(getattr(pay_out, "details", None), dict) else {}
    account = (
        (details.get("phone") or details.get("card") or details.get("account") or "")
        if isinstance(details, dict)
        else ""
    ).strip()
    ps = getattr(pay_out, "payment_system", None)
    method = (getattr(ps, "name", None) or "") if ps is not None else ""

    session = MelbetTransactionSession.objects.create(
        config=config,
        pay_out=pay_out,
        order_id=moid or str(pay_out.id),
        melbet_method=method,
        account_number=account,
    )
    logger.warning(
        "Recreated MelbetTransactionSession for PayOut=%s order_id=%s (was missing)",
        pay_out.id,
        session.order_id,
    )
    return session


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
        logger.info(
            "Melbet callback posted order_id=%s url=%s http=%s",
            session.order_id,
            callback_url,
            status_code,
        )
    except Exception as exc:
        logger.error("Melbet callback failed url=%s order_id=%s: %s", callback_url, session.order_id, exc)
    return status_code


def _schedule_melbet_callback(session: MelbetTransactionSession, callback_url: str) -> None:
    """
    Post the Melbet callback only after the current DB transaction commits.

    Status updates (Success/Failed/…) are often saved inside transaction.atomic()
    (PSP webhooks, order completion). Sending the HTTP callback synchronously
    lets the merchant poll before our commit is visible and read PENDING.
    """
    session_pk = session.pk
    order_id = session.order_id

    def _send() -> None:
        try:
            fresh = MelbetTransactionSession.objects.select_related("config").get(pk=session_pk)
        except MelbetTransactionSession.DoesNotExist:
            logger.error("Melbet callback session missing order_id=%s", order_id)
            return
        _post_melbet_callback(fresh, callback_url)

    transaction.on_commit(_send)


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
    _schedule_melbet_callback(session, pay_in.callback_url)
    return True


def try_send_melbet_payout_callback(pay_out, *, status_name: str | None) -> bool:
    """
    True — Melbet owns this payout callback (do not send AvaPay JSON).
    Melbet expects signed {"order_id"} then polls status; AvaPay-format CB is ignored.
    """
    session = ensure_melbet_payout_session(pay_out)
    if session is None:
        # Not a Melbet-integrated merchant payout
        return False
    if status_name not in TERMINAL_CALLBACK_STATUSES:
        return True
    if not pay_out.callback_url:
        logger.error(
            "Melbet payout CB skipped: empty callback_url pay_out=%s order_id=%s status=%s",
            getattr(pay_out, "id", None),
            session.order_id,
            status_name,
        )
        return True
    _schedule_melbet_callback(session, pay_out.callback_url)
    return True
