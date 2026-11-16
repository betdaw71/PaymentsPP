from django.core.validators import RegexValidator


card_validator = RegexValidator(regex=r'^\d{16}$', message="Enter a valid card number in format of 16 digits", code="invalid_card_number")
# РФ (+79…) и Кыргызстан (+996…), плюс общий E.164 для локальных PS.
ru_phone_validator = RegexValidator(
    regex=r'^\+\d{10,15}$',
    message="Enter a valid phone number in international format (+…)",
    code="invalid_phone_number",
)
sber_deposit_number_validator = RegexValidator(regex=r'^\d{20}$', message="Enter a valid deposit number", code="invalid_deposit_number")
bic_validator = RegexValidator(regex=r'^\d{9}$', message="Enter a valid BIC", code="invalid_bic")
