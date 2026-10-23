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

    logging.debug('psp freeze reconcile')
    try:
        from payments.psp_payin import reconcile_stuck_psp_inorder_freezes

        released = reconcile_stuck_psp_inorder_freezes(limit=200)
        if released:
            logging.info("reconcile_stuck_psp_inorder_freezes: %s order(s)", released)
    except Exception as e:
        logging.error(f"psp freeze reconcile failed: {e}")

    logging.debug('Updating rates')
    try:
        update_ps()
    except Exception as e:
        logging.error(f"update_ps failed: {e}")

    logging.debug("provider appeal nudges")
    try:
        from appeals.notify import nudge_unanswered_provider_appeals

        nudge_unanswered_provider_appeals()
    except Exception as e:
        logging.error("provider appeal nudges failed: %s", e)

    logging.debug("admin balance alerts")
    try:
        from payments.admin_alerts import check_merchant_balance_alerts

        check_merchant_balance_alerts()
    except Exception as e:
        logging.error("admin balance alerts failed: %s", e)

    logging.debug("admin bot commands")
    try:
        from payments.admin_bot import poll_admin_bot

        poll_admin_bot()
    except Exception as e:
        logging.error("admin bot poll failed: %s", e)

