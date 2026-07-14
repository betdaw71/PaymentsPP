from pdfclassifiers.sberclassisifier import SberChecker

sber_checker = SberChecker()


def check_pdf(order, filestream):
    if order.payment_system == "Sber":
        return sber_checker.check_order_pdf(order, filestream)
