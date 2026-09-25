import logging

import requests
import json
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from titanpay.settings import CRYPTO_URL
from decimal import Decimal, InvalidOperation
import requests


def generate_address():
    r = requests.post(f'{CRYPTO_URL}/create/')

    data = r.json()

    return data.get("address")


def get_binance_rate(currency_code, payment_system_name):
    json_data = {
        'fiat': currency_code,
        'page': 1,
        'rows': 10,
        'tradeType': 'BUY',
        'asset': 'USDT',
        'countries': [],
        'proMerchantAds': False,
        'shieldMerchantAds': False,
        'publisherType': 'merchant',
        'payTypes': [
            payment_system_name,
        ],
    }

    response = requests.post(
        'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search',
        json=json_data,
    )
    # print(response.json())
    # print(response.json()['data'])

    if not response.json()['data']:
        json_data['publisherType'] = None

    response = requests.post(
        'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search',
        json=json_data,
    )

    prices = [float(adv['adv']['price']) for adv in response.json()['data'][:3]]
    return round(sum(prices[:min(len(prices), 3)]) / min(len(prices), 3), 3)


def get_garantex_rate():
    market = "usdtrub"
    response = requests.get(f"https://garantex.org/api/v2/depth?market={market}")
    return round(float(response.json()['asks'][0]['price']) * 1.0025, 3)


def get_usdt_rate(currency_code, payment_system_name):
    # return 1
    if currency_code == 'RUB':
        return get_garantex_rate()
    else:
        return get_binance_rate(currency_code, payment_system_name)


def get_range(_min, _max):
    if _min == _max:
        return [0, _max]
    return [_min, _max]


def get_forex_rate(currency):
    url = "https://api.apilayer.com/currency_data/convert"
    params = {"to": currency, "from": "USD", "amount": 1}
    payload = {}
    headers = {
      "apikey": "OkmvwfIuJ1HbaO06LpyCWpai46zuvquS"
    }

    response = requests.request("GET", url, headers=headers, data=payload, params=params)

    status_code = response.status_code
    if status_code != 200:
        return False, 1
    else:
        result = response.json()
        return True, result['result']


import requests
from decimal import Decimal


import uuid


def check_pd_data(data, *, require_deposit=False):
    if data.get('phone') == '':
        data['phone'] = None
    if data.get('card_number') == '':
        data['card_number'] = None
    if data.get('sberpay_enabled') == '':
        data['sberpay_enabled'] = False
    if data.get('sbp_enabled') == '':
        data['sbp_enabled'] = False

    if data.get('phone') is None and (data.get('sbp_enabled') or data.get('sberpay_enabled')):
        raise ValidationError({'details': 'Phone cannot be empty if SBP or SberPay is enabled'})

    deposit = data.get('deposit_number')
    if deposit in (None, ''):
        if require_deposit:
            raise ValidationError({'deposit_number': ['This field is required.']})
        # Колонка NOT NULL + unique среди active — для карт подставляем служебный номер.
        data['deposit_number'] = str(uuid.uuid4().int % 10**20).zfill(20)
    return data


def get_binance_kzt_halyk_rate():
    """
    USDT/KZT с Binance P2P: Halyk Bank, среднее со 2–4 объявления (индексы 1–3).
    payTypes задаётся PROTOCOL_BINANCE_PAY_TYPE (по умолчанию HalykBank).
    """
    from django.conf import settings

    pay_type = getattr(settings, "PROTOCOL_BINANCE_PAY_TYPE", "HalykBank")
    json_data = {
        "fiat": "KZT",
        "page": 1,
        "rows": 10,
        "tradeType": "BUY",
        "asset": "USDT",
        "countries": [],
        "proMerchantAds": False,
        "shieldMerchantAds": False,
        "publisherType": "merchant",
        "payTypes": [pay_type],
    }
    try:
        response = requests.post(
            "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search",
            json=json_data,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json().get("data") or []
        if not data:
            json_data["publisherType"] = None
            response = requests.post(
                "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search",
                json=json_data,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json().get("data") or []
        if len(data) < 2:
            logging.warning("Binance KZT Halyk: not enough ads (%s)", len(data))
            return None
        slice_end = min(4, len(data))
        prices = [float(adv["adv"]["price"]) for adv in data[1:slice_end]]
        if not prices:
            return None
        avg = sum(prices) / len(prices)
        logging.info("Binance KZT Halyk rate (ads 2-%s): %s", slice_end, avg)
        return Decimal(str(round(avg, 3)))
    except Exception as exc:
        logging.error("Binance KZT Halyk rate failed: %s", exc)
        return None


DEFAULT_XE_KZT_MARKUP = Decimal("1.05")


def _xe_kzt_markup_map() -> dict[str, Decimal]:
    from django.conf import settings

    raw = getattr(settings, "XE_KZT_MARKUP_BY_PS", None) or ""
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(str(raw)) if str(raw).strip() else {}
        except Exception:
            logging.warning("XE_KZT_MARKUP_BY_PS is not valid JSON: %s", raw)
            return {}
    out = {}
    for key, val in (data or {}).items():
        try:
            out[str(key)] = Decimal(str(val))
        except Exception:
            continue
    return out


def xe_kzt_markup_for_ps(ps_name: str | None = None) -> Decimal:
    """Наценка XE USD/KZT. Сначала XE_KZT_MARKUP_BY_PS, иначе XE_KZT_MARKUP, иначе +5%."""
    from django.conf import settings

    by_ps = _xe_kzt_markup_map()
    if ps_name and ps_name in by_ps:
        return by_ps[ps_name]
    markup_override = getattr(settings, "XE_KZT_MARKUP", None)
    if markup_override:
        try:
            return Decimal(str(markup_override))
        except Exception:
            pass
    return DEFAULT_XE_KZT_MARKUP


def get_xe_kzt_base_rate():
    """USD/KZT mid-market с xe.com без наценки."""
    try:
        response = requests.get(
            "https://www.xe.com/api/protected/midmarket-converter/",
            headers={
                "Authorization": "Basic bG9kZXN0YXI6cHVnc25heA==",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        rates = data.get("rates", {})
        kzt = rates.get("KZT")
        if kzt is None:
            logging.error("XE KZT rate: KZT not found in response keys=%s", list(rates.keys())[:10])
            return None
        return Decimal(str(kzt))
    except Exception as exc:
        logging.error("XE KZT rate failed: %s", exc)
        return None


def get_xe_kzt_rate(markup: Decimal | None = None, ps_name: str | None = None):
    """
    Курс USDT/KZT через xe.com: USD/KZT + наценка (по умолчанию +5%).
    USDT ≈ 1 USD, поэтому берём USD/KZT напрямую.
    Наценку: xe_kzt_markup_for_ps (XE_KZT_MARKUP_BY_PS / XE_KZT_MARKUP).
    """
    if markup is None:
        markup = xe_kzt_markup_for_ps(ps_name)
    base_rate = get_xe_kzt_base_rate()
    if base_rate is None:
        return None
    result = (base_rate * markup).quantize(Decimal("0.001"))
    logging.info("KZT rate XE.com (USD/KZT + %s%%): base=%s result=%s", (markup - 1) * 100, base_rate, result)
    return result




BYBIT_KZT_KASPI_PAYMENT_ID = "150"
BYBIT_KZT_DEFAULT_AMOUNT = "50000"
BYBIT_KZT_DEFAULT_ROWS = (15, 16)


def _bybit_kzt_settings():
    from django.conf import settings

    amount = str(getattr(settings, "BYBIT_KZT_AMOUNT", None) or BYBIT_KZT_DEFAULT_AMOUNT).strip() or BYBIT_KZT_DEFAULT_AMOUNT
    raw_auth = getattr(settings, "BYBIT_KZT_AUTH_MAKER", True)
    if isinstance(raw_auth, str):
        auth_maker = raw_auth.strip().lower() in ("1", "true", "yes")
    else:
        auth_maker = bool(raw_auth)
    rows_raw = getattr(settings, "BYBIT_KZT_ROWS", None)
    rows = list(BYBIT_KZT_DEFAULT_ROWS)
    if rows_raw:
        try:
            if isinstance(rows_raw, (list, tuple)):
                parts = [int(x) for x in rows_raw]
            else:
                parts = [int(p.strip()) for p in str(rows_raw).split(",") if p.strip()]
            if parts:
                rows = parts
        except (TypeError, ValueError):
            rows = list(BYBIT_KZT_DEFAULT_ROWS)
    return amount, auth_maker, rows


def _price_from_bybit_item(item) -> Decimal | None:
    if not isinstance(item, dict):
        return None
    try:
        price = Decimal(str(item.get("price") or "0"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return price if price > 0 else None


def get_bybit_kzt_rate_quote():
    """
    Красный стакан Bybit P2P USDT/KZT: Kaspi, сумма 50 000, проверенные мерчанты,
    среднее по строкам 15–16 (как в стакане, без своей сортировки).
    """
    amount, auth_maker, rows = _bybit_kzt_settings()
    json_data = {
        "userId": "",
        "tokenId": "USDT",
        "currencyId": "KZT",
        "payment": [BYBIT_KZT_KASPI_PAYMENT_ID],
        "side": "1",
        "size": "50",
        "page": "1",
        "amount": amount,
        "authMaker": auth_maker,
        "canTrade": False,
    }

    try:
        response = requests.post(
            "https://api2.bybit.com/fiat/otc/item/online",
            json=json_data,
            timeout=15,
        )
        response.raise_for_status()
    except Exception as exc:
        logging.error("Bybit P2P request failed: %s", exc)
        return None

    data = response.json()
    if data.get("ret_code") != 0:
        logging.error("Bybit API error: %s", data.get("ret_msg"))
        return None

    items = data.get("result", {}).get("items") or []
    prices = []
    for item in items:
        payments = item.get("payments") or []
        payment_ids = {str(p) for p in payments}
        if BYBIT_KZT_KASPI_PAYMENT_ID not in payment_ids:
            continue
        price = _price_from_bybit_item(item)
        if price is not None:
            prices.append(price)

    if not prices:
        logging.warning("Bybit KZT: no Kaspi ads in red book")
        return None

    one_based = [r for r in rows if isinstance(r, int) and r >= 1]
    if not one_based:
        one_based = list(BYBIT_KZT_DEFAULT_ROWS)

    selected = []
    used_rows = []
    for row in one_based:
        idx = row - 1
        if idx < len(prices):
            selected.append(prices[idx])
            used_rows.append(row)

    if not selected:
        take = min(len(one_based), len(prices))
        selected = prices[-take:]
        used_rows = list(range(len(prices) - take + 1, len(prices) + 1))
        logging.warning(
            "Bybit KZT: book has %s Kaspi ads, using last %s as fallback rows=%s",
            len(prices),
            take,
            used_rows,
        )

    avg_price = (sum(selected) / Decimal(len(selected))).quantize(Decimal("0.01"))
    logging.info(
        "Bybit KZT Kaspi red book amount=%s authMaker=%s rows=%s prices=%s avg=%s ads=%s",
        amount,
        auth_maker,
        used_rows,
        selected,
        avg_price,
        len(prices),
    )
    return {
        "rate": avg_price,
        "prices": selected,
        "rows": used_rows,
        "amount": int(Decimal(amount)) if amount.isdigit() else amount,
        "payment": "Kaspi",
        "payment_id": BYBIT_KZT_KASPI_PAYMENT_ID,
        "verified": auth_maker,
        "side": "sell",
        "ads_count": len(prices),
        "source": "bybit_kaspi",
    }


def get_bybit_kzt_rate():
    """Среднее USDT/KZT с красного стакана Bybit (Kaspi, 50k, строки 15–16)."""
    quote = get_bybit_kzt_rate_quote()
    if not quote:
        return None
    return quote["rate"]

def get_bybit_rate(payment_system_name):
    json_data = {
        'userId': '',
        'tokenId': 'USDT',
        'currencyId': 'RUB',
        'payment': [
            '582',
        ],
        'side': '1',
        'size': '10',
        'page': '1',
        'amount': '100000',
        'authMaker': False,
        'canTrade': False,
    }

    response = requests.post('https://api2.bybit.com/fiat/otc/item/online', json=json_data)
    
    result = response.json().get('result', {}).get('items', [])
    
    # Защита от пустого результата
    if not result:
        logging.error("No items returned from Bybit for RUB rate")
        return Decimal('90')  # fallback курс (можно изменить)
    
    start_from = 0 if len(result) == 1 else 1
    end_at = min(6, len(result))
    
    # Защита от пустого списка цен
    prices = []
    for i in range(start_from, end_at):
        try:
            price = Decimal(result[i]['price'])
            if price > 0:
                prices.append(price)
        except (KeyError, ValueError, IndexError) as e:
            logging.error(f"Error parsing price: {e}")
            continue
    
    if not prices:
        logging.error("No valid prices found for RUB rate")
        return Decimal('90')  # fallback курс
    
    avg_price = sum(prices) / Decimal(len(prices))
    return avg_price


def get_balances():
    r = requests.post(f'{CRYPTO_URL}/deposits/')

    deposits = r.json().get('deposits', [])
    logging.debug(f"Deposits: {deposits}")
    return deposits
