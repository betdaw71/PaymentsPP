from trade.routing.sber import SberRouting
from trade.routing.sberpay import SberPayRouting
from trade.routing.sbp import SBPRouting
from trade.routing.sberdep import SberDepRouting
from rest_framework.exceptions import ValidationError
from titanpay.settings import (
    C2C_NAME,
    C2CMMK_NAME,
    C2CTRY_NAME,
    CONCORDED_KBZPAY_PS_NAME,
    CONCORDED_WAVEPAY_PS_NAME,
    PROTOCOL_C2C_NAME,
    PLUTUS_TEST_PS_NAME,
    SBERDEP_NAME,
    SBERPAY_NAME,
    SBER_NAME,
    SBP_NAME,
    UPI_INTENT_NAME,
)

sber = SberRouting()
sberpay = SberPayRouting()
sbp = SBPRouting()
sberdep = SberDepRouting()


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
    elif payment_system.name in _c2c_style_ps_names():
        # C2C / PSP H2H (в т.ч. MMK KBZPay, WavePay через Concored)
        return sber
    raise ValidationError("There is no routing for this payment system")


def _c2c_style_ps_names():
    names = {
        C2C_NAME,
        PROTOCOL_C2C_NAME,
        C2CTRY_NAME,
        CONCORDED_KBZPAY_PS_NAME,
        CONCORDED_WAVEPAY_PS_NAME,
        C2CMMK_NAME,
    }
    test_ps = (PLUTUS_TEST_PS_NAME or "").strip()
    if test_ps:
        names.add(test_ps)
    return names