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


def payment_page_public_base() -> str:
    """Базовый URL хоста платёжной страницы (pay.{domain}), не API."""
    page_domain = (getattr(settings, "PAYMENT_PAGE_URL", None) or "").strip().strip("/")
    if page_domain:
        return f"https://pay.{page_domain}"
    return (getattr(settings, "PUBLIC_API_URL", None) or "").rstrip("/")


def kaspi_guide_asset_path() -> str:
    return "/payment-page-assets/kaspi-international-transfers-guide.png"


def kaspi_guide_public_url() -> str:
    """Относительный путь — браузер грузит с того же хоста, что и pay-страница."""
    return kaspi_guide_asset_path()
