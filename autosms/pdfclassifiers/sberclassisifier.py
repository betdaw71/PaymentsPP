import pdfplumber
from io import BytesIO

class SberChecker:
    def __init__(self):
        self.page_width = 300
        self.page_height = 699

        self.text_cleaned = """Чек по операции
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Операция
Перевод клиенту СберБанка
ФИО получателя
Телефон получателя
Номер карты получателя
ФИО отправителя
Счёт отправителя
Сумма перевода
Комиссия
Номер документа
Код авторизации
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Дополнительная информация
Если вы отправили деньги не тому человеку,
обратитесь к получателю перевода.
Деньги может вернуть только получатель"""

        self.creators = ['JasperReports Library version 6.5.1']
        self.producers = ['iText 2.1.7 by 1T3XT']

    def extract_text_and_metadata(self, pdf_stream):
        success = True
        try:
            with pdfplumber.open(pdf_stream) as pdf:
                metadata = pdf.metadata

                if len(pdf.pages) > 1:
                    return False, None, None, None, None

                text = pdf.pages[0].extract_text()
                width = pdf.pages[0].width
                height = pdf.pages[0].height
            return success, text, metadata, width, height
        except:
            return False, None, None, None, None

    def get_lines(self, text):
        lines = text.split('\n')

        data = {
            "date": lines[1],
            "receive_fio": lines[6],
            "phone": lines[8],
            "receive_card": lines[10],
            "sender_fio": lines[12],
            "sender_deposit_number": lines[14],
            "amount": lines[16],
            "commission": lines[18],
            "doc_number": lines[20],
            "authorization_code": lines[22],
        }

        indexes_to_remove = [1, 6, 8, 10, 12, 14, 16, 18, 20, 22]

        new_lines = [item for idx, item in enumerate(lines) if idx not in indexes_to_remove]

        new_text = ""
        for line in new_lines:
            new_text += line + '\n'

        new_text = new_text[:-1]
        return new_text, data

    def check_text(self, text):
        return text == self.text_cleaned

    def check_amount(self, order, data):
        currency = data["amount"][-2:]
        if currency != " ₽":
            return False

        amount = data["amount"][:-2]
        if amount[-3] != ',':
            return False

        if float(amount.replace(',', '.')) != order.amount:
            return False

        return True

    def check_commission(self, order, data):
        if data["commission"][-2:] != " ₽":
            return False

        return True

    def check_receive_card(self, order, data):
        if data["receive_card"][:5] != "**** ":
            return False

        if order.destination_details.card_number[-4:] != data["receive_card"][-4:]:
            return False

        return True

    def check_deposit_number(self, order, data):
        if data["sender_deposit_number"][:5] != "**** ":
            return False

        if order.payment_details.deposit_number != data["sender_deposit_number"][-4:]:
            return False

        return True

    def check_owner(self, order, data):
        return True

    def check_metadata(self, metadata):
        return metadata['Creator'] in self.creators and metadata['Producer'] in self.producers

    def check_order_pdf(self, order, pdf_stream):
        success, text, metadata, width, height = self.extract_text_and_metadata(BytesIO(pdf_stream))

        if not success:
            return False, "PDF file problem"

        if width != self.page_width or height != self.page_height:
            return False, "Dimension mismatch"

        if not self.check_metadata(metadata):
            return False, "Metadata mismatch"

        new_text, data = self.get_lines(text)

        if not self.check_text(new_text):
            return False, "Clean text mismatch"

        if not self.check_owner(order, data):
            return False, "Owner mismatch"

        if not self.check_amount(order, data):
            return False, "Amount mismatch"

        if not self.check_commission(order, data):
            return False, "Commission mismatch"

        if not self.check_receive_card(order, data):
            return False, "Receive card mismatch"

        if not self.check_deposit_number(order, data):
            return False, "Deposit number mismatch"

        return True, "Success"


order = {
    "amount": 0.1,
    "destination_details": {"card_number": "0000111122229112"},
    "payment_details": {"deposit_number": "5428"}
}

# pdf_path = "testcheck.pdf"
#
# checker = SberChecker()
#
# success, comment = checker.check_order_pdf(order, pdf_path)
#
# print(success, comment)




