from decimal import Decimal

import pytz
from django.db import transaction
from django.utils import timezone
from trade.models import InOrder, OutOrder, InOrderStatusChange, InOrderStatus, OutOrderStatus
from basics.models import PaymentSystem, PaymentDetails, PaymentDetailsGroup
import logging
from titanpay.settings import SYSTEM_INTERVAL_VALUE
from basics.utils import get_balances, get_binance_kzt_halyk_rate, get_bybit_rate, get_bybit_kzt_rate
from trade.models import Address
from django.utils import timezone
from payments.models import PayOut, PayOutStatus
import json
import os
import uuid
import requests
import pandas as pd
from io import BytesIO
from django.http import HttpResponse, JsonResponse
from rest_framework.exceptions import ValidationError
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from payments.utils import upload_to_s3
from titanpay.settings import S3_ENDPOINT, ACCESS_KEY, SECRET_S3_KEY, BUCKET_NAME

AUTOCHECKER_URL = (os.getenv('AUTOCHECKER_URL') or '').strip() or None


def _s3_configured() -> bool:
    return all([S3_ENDPOINT, ACCESS_KEY, SECRET_S3_KEY, BUCKET_NAME])


def _upload_receipt_or_placeholder(order_id, file) -> str:
    object_name = f"out-orders/{order_id}-{getattr(file, 'name', 'receipt.pdf')}"
    if not _s3_configured():
        logging.warning('S3 is not configured; receipt file will not be stored')
        return f'https://storage-not-configured/{object_name}'

    if hasattr(file, 'seek'):
        file.seek(0)
    try:
        return upload_to_s3(file, object_name)
    except (BotoCoreError, ClientError, NoCredentialsError) as exc:
        logging.error('S3 upload failed: %s', exc)
        raise ValidationError({'error': 'Failed to upload receipt file'})


def update_balances():
    deposits = get_balances()
    for deposit in deposits:
        if deposit["amount"] == 0:
            continue
        # try:
        address = Address.objects.get(address_public=deposit["address"])
        with transaction.atomic():
            address.update_balance(Decimal(deposit["amount"]))
        # except:
        #     continue


def update_pd():
    from payments.psp_payin import is_psp_trader

    pd = PaymentDetailsGroup.objects.all()
    for p in pd:
        try:
            uname = ""
            if p.trader_id and getattr(p.trader, "user", None):
                uname = p.trader.user.username or ""
            if is_psp_trader(p.trader) or uname in _liveness_exempt_trader_usernames():
                # Виртуальные PSP / тестовые трейдеры: без SMS, liveness не применяем.
                fields = []
                if p.status == 5:
                    p.status = 1
                    fields.append("status")
                p.auto_live = timezone.now()
                fields.append("auto_live")
                p.save(update_fields=fields)
                continue
            if int(p.updated_at.timestamp()) // SYSTEM_INTERVAL_VALUE != int(timezone.now().timestamp()) // SYSTEM_INTERVAL_VALUE:
                p.update_current_volume()
        except Exception:
            logging.info(f'Updating PD {p.id} failed')

    active_pd = pd.filter(status=1).exclude(trader__user__username__in=_liveness_exempt_trader_usernames())
    for p in active_pd:
        try:
            p.check_liveness()
        except Exception:
            logging.info(f'Updating PD {p.id} failed')

    setup_pd = pd.filter(status=7).exclude(trader__user__username__in=_liveness_exempt_trader_usernames())
    for p in setup_pd:
        try:
            p.check_liveness()
        except Exception:
            logging.info(f'Updating PD {p.id} failed')


def _psp_trader_usernames() -> list[str]:
    from django.conf import settings

    names = []
    for key in ("FAIRPAY_TRADER_USERNAME", "EXPAYONE_TRADER_USERNAME", "PROTOCOL_TRADER_USERNAME", "PLAYMENTS_TRADER_USERNAME", "BITZONE_TRADER_USERNAME", "PLUTUS_TRADER_USERNAME"):
        val = (getattr(settings, key, None) or "").strip()
        if val:
            names.append(val)
    return names or ["fairpay_agg", "expayone1", "protocol1", "playments1"]


def _liveness_exempt_trader_usernames() -> set[str]:
    from django.conf import settings

    names = set(_psp_trader_usernames())
    extra = getattr(settings, "LIVENESS_EXEMPT_TRADER_USERNAMES", "") or ""
    for part in str(extra).split(","):
        part = part.strip()
        if part:
            names.add(part)
    test_trader = (getattr(settings, "MELBET_KZT_TEST_TRADER_USERNAME", None) or "").strip()
    if test_trader:
        names.add(test_trader)
    return names

def update_ps():
    from django.conf import settings

    pss = PaymentSystem.objects.all()
    rub_rate = get_bybit_rate("Sber")
    kzt_bybit_kaspi = get_bybit_kzt_rate()
    kzt_binance_halyk = get_binance_kzt_halyk_rate()
    protocol_ps_name = getattr(settings, "PROTOCOL_C2C_NAME", "C2CKZT")
    playments_ps_name = getattr(settings, "PLAYMENTS_C2C_NAME", "C2CTRY")

    for ps in pss:
        try:
            currency = ps.currency.symbol if ps.currency else None
            if ps.name == playments_ps_name:
                continue
            if currency == "KZT":
                if ps.name == protocol_ps_name:
                    kzt_rate = kzt_binance_halyk
                    source = "Binance/Halyk"
                else:
                    kzt_rate = kzt_bybit_kaspi
                    source = "Bybit/Kaspi"
                if kzt_rate is None:
                    logging.warning("KZT rate skipped for %s (%s returned None)", ps.name, source)
                    continue
                ps.update_rate(kzt_rate)
                logging.info("KZT rate %s (%s): %s", ps.name, source, kzt_rate)
            elif currency == "RUB" and rub_rate is not None:
                ps.update_rate(rub_rate)
        except Exception:
            logging.info("Updating PS %s (%s) failed", ps.id, ps.name, exc_info=True)


def expire_pay_outs():
    payment_systems = PaymentSystem.objects.all()
    new_status = PayOutStatus.objects.get(name="New")
    for ps in payment_systems:
        time_constraint = timezone.now() - ps.expired_time_out
        expired_pay_outs = PayOut.objects.filter(payment_system=ps, created_at__lte=time_constraint, status=new_status)

        for pay_out in expired_pay_outs:
            pay_out.failed()


def expire():
    payment_systems = PaymentSystem.objects.all()

    for ps in payment_systems:
        time_in = timezone.now() - ps.expired_time_in
        time_out = timezone.now() - ps.expired_time_out
        arb_time_out = timezone.now() - ps.arbitrage_time_in
        expired_in_orders = InOrder.objects.filter(
            status__name="New",
            creation_date__lte=time_in,
            solution__payment_system=ps,
        )
        expired_out_orders = OutOrder.objects.filter(status__name="New", creation_date__lte=time_out, solution__payment_system=ps, sms_sent=False)
        arbitrage_orders_in = InOrder.objects.filter(status__name="Arbitrage", amount__lte=ps.auto_close_amount, solution__payment_system=ps, updated_date__lte=arb_time_out)

        for order in expired_in_orders:
            with transaction.atomic():
                order.deal_time_expired()

        for order in expired_out_orders:
            with transaction.atomic():
                order.deal_expired()

        for order in arbitrage_orders_in:
            with transaction.atomic():
                order = InOrder.objects.select_for_update().get(id=order.id)
                if order.status.name == "Arbitrage":
                    order.complete_after_arbitrage()

        not_confirmed_time_out = timezone.now() - ps.confirm_time_out
        finished_out_orders = OutOrder.objects.filter(status__name="Money sent by trader", updated_date__lte=not_confirmed_time_out, solution__payment_system=ps, pdf_sent=True, sms_sent=False)
        sms_out_orders = OutOrder.objects.filter(status__name="New", updated_date__lte=time_out, solution__payment_system=ps, pdf_sent=False, sms_sent=True)

        for order in finished_out_orders:
            with transaction.atomic():
                order.manual_check()

        for order in sms_out_orders:
            with transaction.atomic():
                order.manual_check()

    # time_fail_out = timezone.now() - ps.constrain_time_out
    # failed_out_orders_new = OutOrder.objects.filter(status=new_out, first_creation_date__lte=time_fail_out)
    # failed_out_orders_exp = OutOrder.objects.filter(status=expired_out, first_creation_date__lte=time_fail_out)
    #
    # for order in failed_out_orders_new:
    #     order.failed()
    # for order in failed_out_orders_exp:
    #     order.failed()


def send_to_fastapi(order: dict, file) -> dict:
    """PDF check via autochecker; без AUTOCHECKER_URL — загрузка в S3 или заглушка URL."""

    order_id = order.get('id', str(uuid.uuid4()))

    if AUTOCHECKER_URL is None:
        file_url = _upload_receipt_or_placeholder(order_id, file)
        return {'file_url': file_url, 'success': True, 'comment': ''}

    files = {
        'file': (file.name, file, file.content_type)
    }
    data = {'order': json.dumps(order)}
    try:
        response = requests.post(AUTOCHECKER_URL + '/pdf/', data=data, files=files, timeout=60)
    except requests.RequestException as exc:
        logging.error('Autochecker request failed: %s', exc)
        raise ValidationError({'error': 'PDF verification service unavailable'})

    if response.status_code != 200:
        logging.error('Autochecker returned %s: %s', response.status_code, response.text[:500])
        raise ValidationError({'error': 'PDF verification failed'})

    return response.json()


def build_orders_excel_buffer(queryset, *, for_merchant: bool = False, payment_fk_id_field: str = 'pay_in__id'):
    payment_column_key = 'payment_id'
    value_fields = [
        'id',
        payment_fk_id_field,
        'status__name',
        'amount',
        'usd_amount',
        'merchant_fee',
        'solution__payment_system__name',
        'creation_date',
        'merchant_order_id',
    ]
    if not for_merchant:
        value_fields.extend([
            'trader_fee',
            'payment_details__group__owner',
        ])

    data = list(queryset.values(*value_fields))

    for item in data:
        item[payment_column_key] = item.pop(payment_fk_id_field, None)
        if item['creation_date']:
            item['creation_date'] = item['creation_date'].astimezone(pytz.utc).replace(tzinfo=None)
        if not for_merchant:
            mf = Decimal(str(item.get('merchant_fee') or 0))
            tf = Decimal(str(item.get('trader_fee') or 0))
            item['platform_commission'] = mf - tf

    df = pd.DataFrame(data)

    payment_label = 'PayOut ID' if payment_fk_id_field == 'pay_out__id' else 'PayIn ID'
    column_mapping = {
        'id': 'ID (Order)',
        payment_column_key: payment_label,
        'status__name': 'Статус',
        'amount': 'Сумма (Фиат)',
        'usd_amount': 'Сумма (USDT)',
        'merchant_fee': 'Комиссия мерчанта (USDT)',
        'merchant_order_id': 'Merchant order ID',
        'solution__payment_system__name': 'Платёжная система',
        'creation_date': 'Дата создания',
    }
    if not for_merchant:
        column_mapping.update({
            'trader_fee': 'Комиссия трейдера (USDT)',
            'platform_commission': 'Комиссия платформы (USDT)',
            'payment_details__group__owner': 'ФИО',
        })

    df.rename(columns=column_mapping, inplace=True)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return buffer


def orders_excel_http_response(
    queryset,
    *,
    filename_prefix: str = "orders",
    for_merchant: bool = False,
    payment_fk_id_field: str = 'pay_in__id',
):
    buffer = build_orders_excel_buffer(
        queryset,
        for_merchant=for_merchant,
        payment_fk_id_field=payment_fk_id_field,
    )
    filename = f"{filename_prefix}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_to_excel(queryset):
    """Legacy: upload to S3 and return public URL. Requires BUCKET_NAME in .env."""
    buffer = build_orders_excel_buffer(queryset)
    object_name = f"exports/orders_{uuid.uuid4().hex}.xlsx"
    file_url = upload_to_s3(buffer, object_name)
    return file_url
