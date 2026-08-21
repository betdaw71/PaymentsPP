from trade.utils2 import expire, update_balances, update_pd, expire_pay_outs, update_ps
import logging


def update_all():

    logging.debug('Updating balances')
    try:
        update_balances()
    except Exception as e:
        logging.error(f"update_balances failed: {e}")
    logging.debug('Updating PDs')
    try:
        update_pd()
    except Exception as e:
        print(e)

    logging.debug('expiring')
    try:
        expire()
    except Exception as e:
        logging.error(f"expire failed: {e}")

    logging.debug('Updating rates')
    try:
        update_ps()
    except Exception as e:
        logging.error(f"update_ps failed: {e}")

