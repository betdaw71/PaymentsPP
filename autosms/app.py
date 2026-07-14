import json
import logging

from fastapi import FastAPI, Request
from pydantic import BaseModel, Extra
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Extra
from classifier.route import route
from fastapi import UploadFile, File
from s3uploader import upload_to_s3
from typing import Optional
from pdfclassifiers.route import check_pdf
import requests
import dotenv
import os

# dotenv.load_dotenv()
BACKEND_ENDPOINT = os.getenv('BACKEND_ENDPOINT')

app = FastAPI()


class DestinationDetails(BaseModel):
    card_number: Optional[str] = None
    customer: Optional[str] = None


class PaymentDetails(BaseModel):
    deposit_number: Optional[str] = None


class Order(BaseModel):
    id: str
    amount: float
    payment_system: str
    destination_details: Optional[DestinationDetails] = None
    payment_details: Optional[DestinationDetails] = None

    class Config:
        extra = Extra.allow


class SMS(BaseModel):
    from_number: Optional[str] = ''
    from_bank: Optional[str] = ''
    text: str
    received_at: int
    group: str


class GroupInfo(BaseModel):
    group: str


@app.post("/sms/")
async def process_sms(sms: SMS, request: Request):
    headers = request.headers
    data = route(sms)
    logging.debug(data)
    url = BACKEND_ENDPOINT + 'process-sms/'
    headers = {"Authorization": headers['authorization'], "GATE": "lwkdo3di4ndRrncr4295"}
    response = requests.post(url, json=data, headers=headers)
    return True


@app.post("/live/")
async def process_live(group_info: GroupInfo, request: Request):
    headers = request.headers
    url = BACKEND_ENDPOINT + 'liveness/'
    data = {"group": group_info.group}
    headers = {"Authorization": headers['authorization'], "GATE": "lwkdo3di4ndRrncr4295"}
    response = requests.post(url, json=data, headers=headers)
    return True


@app.post("/pdf/")
async def process_pdf(order: str = Form(...), file: UploadFile = File(...)):
    try:
        order_dict = json.loads(order)
        order_obj = Order(**order_dict)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    file_bytes = await file.read()
    file_name = f"out-{order_obj.id[:8]}"
    file_url = upload_to_s3(file_bytes, f"{file_name}.pdf")

    success, comment = check_pdf(order_obj, file_bytes)
    data = {
        "file_url": file_url,
        "success": success,
        "comment": comment,
    }
    return data

