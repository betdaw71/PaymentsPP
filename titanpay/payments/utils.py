import json
import uuid
import boto3
from botocore.exceptions import NoCredentialsError
import dotenv
import os
from io import BytesIO
from json import JSONEncoder
from titanpay.settings import PAYMENT_PAGE_URL, S3_ENDPOINT, ACCESS_KEY, SECRET_KEY, BUCKET_NAME, SECRET_S3_KEY


def translate_bank(name):
    if name == 'Sber':
        return 'Сбербанк'
    elif name == 'Tinkoff':
        return 'Тинькофф'


class UUIDEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


def generate_link(order_id, ps_name):
    if ps_name == 'SberPay':
        return f"https://payments.{PAYMENT_PAGE_URL}/{order_id}"
    elif ps_name == 'SBP':
        return f"https://payment.{PAYMENT_PAGE_URL}/{order_id}"
    else:
        return f"https://pay.{PAYMENT_PAGE_URL}/{order_id}"





def s3_configured() -> bool:
    return bool(BUCKET_NAME and S3_ENDPOINT and ACCESS_KEY and SECRET_S3_KEY)


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_S3_KEY,
    )


def s3_object_key_from_url(url: str) -> str | None:
    if not url or not BUCKET_NAME:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = (parsed.path or "").lstrip("/")
    if not path:
        return None

    if path.startswith(f"{BUCKET_NAME}/"):
        return path[len(BUCKET_NAME) + 1 :]

    if S3_ENDPOINT:
        prefix = f"{S3_ENDPOINT.rstrip('/')}/{BUCKET_NAME}/"
        if url.startswith(prefix):
            return url[len(prefix) :]

    host = (parsed.hostname or "").lower()
    if host == f"{BUCKET_NAME}.storage.yandexcloud.net":
        return path

    return None


def public_storage_url(url: str, *, expires_in: int = 3600) -> str:
    """Публичная ссылка: presigned URL для приватного S3, иначе как есть."""
    if not url:
        return url
    key = s3_object_key_from_url(url)
    if not key or not s3_configured():
        return url
    try:
        return _s3_client().generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception:
        return url


def upload_to_s3(file, object_name):
    if not s3_configured():
        raise ValueError(
            "S3 is not configured: set BUCKET_NAME, S3_ENDPOINT, ACCESS_KEY, SECRET_S3_KEY in .env"
        )
    s3_client = boto3.client('s3',
                             endpoint_url=S3_ENDPOINT,
                             aws_access_key_id=ACCESS_KEY,
                             aws_secret_access_key=SECRET_S3_KEY)

    s3_client.upload_fileobj(file, BUCKET_NAME, object_name)

    file_url = f"{S3_ENDPOINT}/{BUCKET_NAME}/{object_name}"
    return file_url


def upload_receipt_storage(file, object_name: str) -> str:
    """S3 если настроен, иначе локально в MEDIA_ROOT (docker volume media_files)."""
    if s3_configured():
        if hasattr(file, "seek"):
            file.seek(0)
        return upload_to_s3(file, object_name)

    from django.conf import settings
    from titanpay.settings import PUBLIC_API_URL

    local_path = os.path.join(settings.MEDIA_ROOT, object_name)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    if hasattr(file, "seek"):
        file.seek(0)
    with open(local_path, "wb") as dest:
        dest.write(file.read())

    base = (PUBLIC_API_URL or "").rstrip("/")
    return f"{base}{settings.MEDIA_URL}{object_name}"

