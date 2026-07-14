import os

import aiohttp
import logging
from dotenv import load_dotenv

load_dotenv()

AUTOCHECKER_URL = os.getenv('AUTOCHECKER_URL')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def send_to_fastapi(order: dict, file_bytes: bytes) -> dict:
    files = {'file': ('document.pdf', file_bytes, 'application/pdf')}

    async with aiohttp.ClientSession() as session:
        async with session.post(AUTOCHECKER_URL + '/pdf/', data={'order': order, 'file': aiohttp.FormData(files)}) as response:
            if response.status == 200:
                logger.info("File successfully uploaded and processed.")
                return await response.json()
            else:
                logger.error(f"Failed to upload file: {await response.text()}")
                return {"success": False, "comment": "Analysing error, contact support"}
