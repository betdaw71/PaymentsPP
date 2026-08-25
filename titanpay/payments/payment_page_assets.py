"""Статика платёжной страницы без collectstatic (Kaspi guide и т.д.)."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404

_ASSETS_DIR = Path(__file__).resolve().parent / "static" / "payment_page"

_KNOWN = {
    "kaspi-international-transfers-guide.png": "image/png",
}


def serve_payment_page_asset(request, filename: str):
    safe = Path(filename).name
    if safe not in _KNOWN:
        raise Http404("Asset not found")
    path = _ASSETS_DIR / safe
    if not path.is_file():
        raise Http404("Asset not found")
    response = FileResponse(path.open("rb"), content_type=_KNOWN[safe])
    response["Cache-Control"] = "public, max-age=86400"
    return response


def kaspi_guide_public_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", None) or "").rstrip("/")
    path = "/payment-page-assets/kaspi-international-transfers-guide.png"
    return f"{base}{path}" if base else path
