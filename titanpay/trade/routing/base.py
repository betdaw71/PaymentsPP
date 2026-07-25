from trade.routing.sber import SberRouting
from trade.routing.sberpay import SberPayRouting
from trade.routing.sbp import SBPRouting
from trade.routing.sberdep import SberDepRouting
from trade.routing.inrbank import IndiaBankRouting
from rest_framework.exceptions import ValidationError
from titanpay.settings import (
    SBER_NAME,
    SBERPAY_NAME,
    SBP_NAME,
    SBERDEP_NAME,
    UPI_INTENT_NAME,
    C2C_NAME,
    PROTOCOL_C2C_NAME,
    C2CTRY_NAME,
    RTGS_NAME,
    IMPS_NAME,
)

sber = SberRouting()
sberpay = SberPayRouting()
sbp = SBPRouting()
sberdep = SberDepRouting()
inrbank = IndiaBankRouting()


def route(payment_system):
    if payment_system.name == SBER_NAME:
        return sber
    elif payment_system.name == SBERPAY_NAME:
        return sberpay
    elif payment_system.name == SBP_NAME:
        return sbp
    elif payment_system.name == SBERDEP_NAME:
        return sberdep
    elif payment_system.name == UPI_INTENT_NAME:
        # FairPay: локальная группа трейдера (fairpay_agg) с «картой» — тот же отбор, что SberRouting
        return sber
    elif payment_system.name in (C2C_NAME, PROTOCOL_C2C_NAME, C2CTRY_NAME):
        # KZT C2C / C2CKZT / TRY C2CTRY: pay-in по карте (card_number), PSP-трейдеры
        return sber
    elif payment_system.name in (RTGS_NAME, IMPS_NAME):
        return inrbank
    raise ValidationError("There is no routing for this payment system")