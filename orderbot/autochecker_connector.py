import json
import os

import aiohttp
import logging

import requests
from dotenv import load_dotenv

# load_dotenv()

AUTOCHECKER_URL = os.getenv('AUTOCHECKER_URL')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_to_fastapi(order: dict, file_bytes: bytes) -> dict:
    files = {'file': ('document.pdf', file_bytes, 'application/pdf')}
    data = {'order': json.dumps(order)}
    response = requests.post(AUTOCHECKER_URL + '/pdf/', data=data, files=files)
    if response.status_code == 200:
        return response.json()

    return {"success": False, "comment": "Analysing error, contact support"}
