# classifier/gazprom.py
import re

class Gazprom:
    
    @staticmethod
    def clean(text):
        return text.replace(' ', ' ').replace('\u2009', ' ').strip()
    
    def regex_list(self):
        return [
            {
                "regex": r"\*(\d{4}) Получен перевод (\d+(?:\.\d{2})?)р SBP C2C ZACHISLENIE Доступно (\d+(?:\.\d{2})?)р",
                "fields": ["card_number", "amount", "balance"],
                "direction": "in",
                "methods": ["SBP"]
            },
            {
                "regex": r"\*(\d{4}) Списание (\d+(?:\.\d{2})?)р SBP C2C Доступно (\d+(?:\.\d{2})?)р",
                "fields": ["card_number", "amount", "balance"],
                "direction": "out", 
                "methods": ["SBP"]
            },
            {
                "regex": r"\*(\d{4}) Оплата (\d+(?:\.\d{2})?)р.*?Доступно (\d+(?:\.\d{2})?)р",
                "fields": ["card_number", "amount", "balance"],
                "direction": "out",
                "methods": ["Card"]
            },
            {
                "regex": r"\*(\d{4}) Зачисление (\d+(?:\.\d{2})?)р.*?Доступно (\d+(?:\.\d{2})?)р",
                "fields": ["card_number", "amount", "balance"],
                "direction": "in",
                "methods": ["Card"]
            }
        ]
    
    def check_block(self, text):
        # Пока не известно о блокировках в Газпромбанке
        return False, None
    
    def classify(self, text):
        text = self.clean(text)
        data = {}
        
        for mask in self.regex_list():
            matches = re.findall(mask['regex'], text)
            if matches:
                extracted_data = list(matches[0])
                
                for field, value in zip(mask['fields'], extracted_data):
                    if field in ['amount', 'balance']:
                        data[field] = float(value)
                    else:
                        data[field] = value
                
                if data:
                    data['direction'] = mask['direction']
                    data['payment_system'] = "Gazprom"
                    data['methods'] = mask['methods']
                    data['success'] = True
                    data['blocked'] = False
                    data['text'] = text
                    return data
        
        data["success"] = False
        data['payment_system'] = "Gazprom"
        data['text'] = text
        return data
    
    def check(self, text):
        blocked, status = self.check_block(text)
        
        if blocked:
            return {
                "success": True, 
                "blocked": True, 
                "block_type": status, 
                'text': text,
                'payment_system': "Gazprom"
            }
        
        return self.classify(text)