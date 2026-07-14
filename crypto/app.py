import os
from decimal import Decimal

from crypto import get_deposits, process_deposits, create_address
from database import setup_db
from fastapi import FastAPI

setup_db()

app = FastAPI()
FEE_VALUE = Decimal(os.getenv('FEE_VALUE'))


@app.post("/deposits/")
async def deps():
    deposits = get_deposits()
    print(deposits)
    process_deposits(deposits)
    for deposit in deposits:
        deposit["amount"] -= FEE_VALUE
    return {"deposits": deposits}


@app.post("/create/")
async def create_addr():
    address = create_address()
    return {"address": address}
