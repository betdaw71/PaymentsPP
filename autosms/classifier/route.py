import os

from classifier.alfa import Alfa
from classifier.otp import OTP
from classifier.sber import Sber
from classifier.tink import Tink
from classifier.gazprom import Gazprom
import dotenv

dotenv.load_dotenv()

SBER_PHONE = os.getenv('SBER_PHONE')
ALFA_PHONE = os.getenv('ALFA_PHONE')
gazprom_obj = Gazprom() 

sber_obj = Sber()
tink_obj = Tink()
otp_obj = OTP()
alfa_obj = Alfa()

banks_push = {"ru.ozon.fintech.finance": "Ozon",
"ru.ozon.app.android": "Ozon",
"ru.alfabank.mobile.android": "Alfa",
"ru.raiffeisennews": "Raif",
"ru.rosbank.android.beta": "RosBank",
"ru.otpbank.mobile": "OTP",
"ru.akbars.mobile": "AkBars",
"ru.zenitonline.android": "Zenit",
"ru.gazprombank.android.mobilebank.app": "Gazprom",
"ru.vtb24.mobilebanking.android": "VTB",
"com.bankffin.portfolio": "FreedomFin",
"ru.ftc.faktura.primsoc": "Tavr",
"com.idamob.tinkoff.android": "Tinkoff",
"com.bifit.rncbbeta": "RNKB",
"com.yandex.bank": "YaPay",
"ru.rshb.dbo": "RSHB",
"ru.bankuralsib.mb.android": "UrlaSib",
"ru.mts.bank": "MTS",
"cz.bsc.rc": "BSC",
"ru.simpls.brs2.mobbank": "RusStandard"}


def route(sms):
    # Обработка по номеру телефона
    if sms.from_number == SBER_PHONE:
        data = sber_obj.check(text=sms.text)
        data['group'] = sms.group
        return data
    elif sms.from_number == ALFA_PHONE:
        data = alfa_obj.check(text=sms.text)
        data['group'] = sms.group
        return data
    
    # Обработка пуш-уведомлений из приложений банков
    elif sms.from_bank in banks_push.keys():
        bank_name = banks_push[sms.from_bank]
        
        if bank_name == "Gazprom":
            data = gazprom_obj.check(text=sms.text)
        elif bank_name == "Tinkoff":
            data = tink_obj.check(text=sms.text)
        elif bank_name == "Alfa":
            data = alfa_obj.check(text=sms.text)
        elif bank_name == "OTP":
            data = otp_obj.check(text=sms.text)
        else:
            # Для остальных банков используем Tinkoff как fallback
            data = tink_obj.check(text=sms.text)
        
        data['group'] = sms.group
        return data
    else:
        return {"success": False}

