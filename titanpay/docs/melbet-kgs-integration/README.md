# Melbet KG (KGS) — интеграционные анкеты AvaPay / PayPlat

Три заполненные анкеты для методов:

| Файл | Melbet method | Описание |
|------|---------------|----------|
| `AvaPay_Integration_information_qr_kgs_KG_e497.docx` | `qr_kgs` | ELQR / QR |
| `AvaPay_Integration_information_phone_kgs_KG_924d.docx` | `phone_kgs` | перевод по телефону (мобильный) |
| `AvaPay_Integration_information_card2card_kgs_KG_8c48.docx` | `card2card_kgs` | перевод по карте |

Перегенерация: `python3 fill_ankety.py`

## Общие креды (все 3 метода)

- **x-api-key:** `vJ-57rbr1kVRsUNo9xKiGNOqtBFal-G3gnpC7RZCNwo`
- **Secret (HMAC-SHA256 / x-signature):** `2d26e0fd362931148aef4e71e3f93f5d595d4300539949b916045384d01b405b`
- **Deposit:** `POST https://api.avapay.net/api/v1/integrations/melbet/deposit/`
- **Withdrawal:** `POST https://api.avapay.net/api/v1/integrations/melbet/withdrawal/`
- **Status:** `GET https://api.avapay.net/api/v1/integrations/melbet/transactions/{transaction_id}/`

## ЛК / пароль

Пароль сменён менеджером Melbet — доступа нет. Поддержка: Telegram **@avapay_support5**.

## Коммерческие условия (зафиксировано)

- GEO: Киргизия; валюта запроса: **KGS**; валюта баланса / settlement: **USDT**
- Трафик: первичный + вторичный; конверсия: 50%; интеграция: H2H / Redirect
- MID limits: неограниченно
- In: min **500** / max **1 000 000** KGS; fee in **7%**
- Out: min **5 000** / max **1 000 000** KGS; fee out **3.2%**; выплаты по QR 1–3 чека
- Settlement: USDT, fee 0%, T+0, от 3 000 USDT
- Курс: [XE](https://www.xe.com) + 2%

## Callback (депозит и вывод)

```http
POST {callback_url}
Content-Type: application/json
x-api-key: …
x-signature: …

{"order_id":"MB-123456789"}
```

Сумма — в `GET /transactions/{id}/` (поле `amount`, GROSS KGS).
