import json
from fastapi import FastAPI
from pydantic import BaseModel, Extra
from typing import Optional
import requests
import dotenv
import os
from bot import send_emergency


# dotenv.load_dotenv()
BACKEND_ENDPOINT = os.getenv('BACKEND_ENDPOINT')

app = FastAPI()


class Alert(BaseModel):
    block_type: str
    text: str
    owner: str
    user_id: int


@app.post("/alert/")
async def process_sms(alert: Alert):
    send_emergency(alert.block_type, alert.owner, alert.text, alert.user_id)
    return True



