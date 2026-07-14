import re


class Alfa:

    @staticmethod
    def clean(text):
        return text.replace(' ', ' ')

    def regex_list(self):
        return [
            {"regex": "Пополнение \*(\d{4}) на (\d{1,4}(?: \d{3})*(?:,\d{2})?) RUR Баланс: (\d{1,4}(?: \d{3})*(?:,\d{2})?) RUR", "fields": ["card_number", "amount", "balance"], "direction": "in", "methods": ["Interbank", "SBP"]},
            {"regex": "Поступление (\d{1,4}(?: \d{3})*(?:\.\d{2})?) RUR по СБП от .+", "fields": ["amount"], "direction": "in", "methods": ["SBP"]},
        ]

    def check_block(self, text):
        return False, None

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
                    data[field] = float(value.replace(' ','').replace(',', '.'))
                else:
                    data[field] = value

            if data:
                data['direction'] = mask['direction']
                data['payment_system'] = "Alfa"
                data['methods'] = mask['methods']
                data['success'] = True
                data['blocked'] = False
                data['text'] = text
                return data

        data["success"] = False
        data['payment_system'] = "Alfa"
        data['text'] = text
        return data

    def check(self, text):

        blocked, status = self.check_block(text)

        if blocked:
            return {"success": True, "blocked": True, "block_type": status, 'text': text}

        return self.classify(text)
