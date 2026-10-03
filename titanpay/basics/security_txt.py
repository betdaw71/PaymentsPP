from pathlib import Path

from django.http import HttpResponse

_SECURITY_TXT_FALLBACK = """\
Contact: mailto:support@avapay.net
Contact: https://t.me/avapay_manager
Expires: 2027-12-31T23:59:59.000Z
Preferred-Languages: en, ru
Canonical: https://avapay.net/.well-known/security.txt
Policy: https://avapay.net/
"""


def security_txt(_request):
    path = Path(__file__).resolve().parent.parent / "wellknown" / "security.txt"
    body = path.read_text(encoding="utf-8") if path.is_file() else _SECURITY_TXT_FALLBACK
    return HttpResponse(body, content_type="text/plain; charset=utf-8")
