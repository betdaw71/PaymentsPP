import re


class Tink:

    @staticmethod
    def clean(text):
        return text.replace(' ', ' ')

    def regex_list(self):
        return [
            {"regex": "(?:MIR-|VISA|МИР-|ECMC|УЭК|МИР|MIR)(\d{4}) .*? перевод (\d{1,4}(?: \d{3})*)р .*? Баланс: (\d+(?: \d{3})*(?:\.\d{2})?)р", "fields": ["card_number", "amount", "balance"], "direction": "out", "methods": ["Sber"]},
            {"regex": "СЧЁТ(\d{4}) .*? (?:Оплата|перевод) (\d{1,4}(?: \d{3})*)р.*? Баланс: (\d+(?: \d{3})*(?:\.\d{2})?)р", "fields": ["deposit_number", "amount", "balance"], "direction": "out", "methods": ["Sber", "SBP"]},
            {"regex": "СЧЁТ(\d{4}) .*? (?:Оплата|перевод) (\d{1,4}(?: \d{3})*)р.*? Баланс: (\d+(?: \d{3})*(?:\.\d{2})?)р", "fields": ["deposit_number", "amount", "balance"], "direction": "out", "methods": ["Sber", "SBP"]},
            {"regex": "(?:MIR-|VISA|МИР-|ECMC|УЭК|МИР|MIR)(\d{4}) .*? зачисление (\d{1,4}(?: \d{3})*)р .*? Баланс: (\d+(?: \d{3})*(?:\.\d{2})?)р", "fields": ["card_number", "amount", "balance"], "direction": "in", "methods": ["Sber"]},
            {"regex": "(?:MIR-|VISA|МИР-|ECMC|УЭК|МИР|MIR)(\d{4}) .*? Перевод (\d{1,4}(?: \d{3})*)р от .*? Баланс: (\d+(?: \d{3})*(?:\.\d{2})?)р", "fields": ["card_number", "amount", "balance"], "direction": "in", "methods": ["Sber"]},
            {"regex": "(?:MIR-|VISA|МИР-|ECMC|УЭК|МИР|MIR)(\d{4}) .*? перевел\(а\) вам (\d{1,4}(?: \d{3})*)р", "fields": ["card_number", "amount", "balance"], "direction": "in", "methods": ["Sber"]},
            {"regex": "СЧЁТ(\d{4}) .*? Перевод (\d{1,4}(?: \d{3})*)р от .*? Баланс: (\d+(?: \d{3})*(?:\.\d{2})?)р", "fields": ["deposit_number", "amount", "balance"], "direction": "in", "methods": ["SBP", "SberPay"]},
            {"regex": "СЧЁТ(\d{4}) .*? Перевод из .*? \+(\d{1,4}(?: \d{3})*)р .*? Баланс: (\d+(?: \d{3})*(?:\.\d{2})?)р", "fields": ["deposit_number", "amount", "balance"], "direction": "in", "methods": ["SBP", "SberPay"]},
            {"regex": "(?:СЧЁТ|ПЛАТ\.СЧЕТ)(\d{4}) .*? зачислен перевод .*?(\d{1,4}(?: \d{3})*)р из .*?от.*", "fields": ["deposit_number", "amount"], "direction": "in", "methods": ["SBP", "SberPay"]},
        ]

    def check_block(self, text):
        block_type = None
        if "Для безопасности ваших средств банк остановил подозрительный перевод и заблокировал СберБанк Онлайн" in text:
            block_type = 'red-block'
        elif "СберБанк Онлайн заблокирован" in text or "115-ФЗ" in text or "сомнительного характера" in text:
            block_type = "fz-block"
        elif "СберБанк Онлайн заблокирован" in text or "115-ФЗ" in text:
            block_type = "fz-block"
        elif "компромета" in text:
            block_type = "compr-block"
        else:
            return False, None

        if "Комментарий" in text or "Сообщение" in text or "«" in text:
            return False, None

        return True, block_type

    def classify(self, text):
        text = self.clean(text)

        data = {}

        for mask in self.regex_list():
            matches = re.findall(mask['regex'], text)
            extracted_numbers = [num.replace(' ', '') for match in matches for num in match]

            if len(extracted_numbers) > len(mask['fields']):
                extracted_numbers = extracted_numbers[:len(mask['fields'])]

            for field, value in zip(mask['fields'], extracted_numbers):
                if field == 'amount' or field == 'balance':
                    data[field] = float(value)
                else:
                    data[field] = value

            if data:
                data['direction'] = mask['direction']
                data['payment_system'] = "Sber"
                data['methods'] = mask['methods']
                data['success'] = True
                data['blocked'] = False
                data['text'] = text
                return data

        data["success"] = False
        data['payment_system'] = "Tinkoff"
        data['text'] = text
        return data

    def check(self, text):

        data = {}
        data["success"] = False
        data["blocked"] = False
        data['payment_system'] = "Tinkoff"
        data['text'] = text

        return data
