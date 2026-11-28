"""
Проверка подписи Bitzone webhook локально (тот же алгоритм, что bitzone_client.verify_webhook_signature).

Пример:
  docker compose exec app python manage.py shell -c "
import json
from payments.bitzone_client import verify_webhook_signature
body = open('/tmp/bz_webhook.json','rb').read()
sig = 'PASTE_X_SIGNATURE_HEX'
print(verify_webhook_signature(body, sig))
"
"""
from payments.bitzone_client import _hmac_sha256_hex, _signing_keys_for_webhook, _webhook_body_candidates


def diagnose(raw_body: bytes, signature: str) -> None:
    keys = _signing_keys_for_webhook()
    print(f"keys configured: {len(keys)}")
    print(f"body_len={len(raw_body)} sig_len={len(signature or '')}")
    messages = _webhook_body_candidates(raw_body)
    print(f"body variants: {len(messages)}")
    sig = (signature or "").strip().lower()
    for ki, key in enumerate(keys):
        for mi, msg in enumerate(messages):
            exp = _hmac_sha256_hex(key, msg)
            if exp == sig:
                print(f"MATCH key_index={ki} body_variant={mi}")
                return
    print("NO MATCH — сверьте BITZONE_API_KEY / BITZONE_WEBHOOK_SECRET с ЛК Bitzone")


run = diagnose
