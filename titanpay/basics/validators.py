from django.core.validators import RegexValidator


card_validator = RegexValidator(regex=r'^\d{16}$', message="Enter a valid card number in format of 16 digits", code="invalid_card_number")
ru_phone_validator = RegexValidator(regex=r'^\+79\d{9}$', message="Enter a valid phone number", code="invalid_phone_number")
sber_deposit_number_validator = RegexValidator(
    regex=r'^\d{9,20}$',
    message="Enter a valid account number (9-20 digits)",
    code="invalid_deposit_number",
)
bic_validator = RegexValidator(
    regex=r'^(\d{9}|[A-Z]{4}0[A-Z0-9]{6})$',
    message="Enter a valid BIC (9 digits) or IFSC (11 chars)",
    code="invalid_bic",
)
