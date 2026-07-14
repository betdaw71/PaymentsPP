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





def upload_to_s3(file, object_name):
    if not BUCKET_NAME or not S3_ENDPOINT:
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

