from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments'

    def ready(self):
        from django.db.models.signals import post_save

        from payments.integrations.melbet import models as _melbet_models  # noqa: F401
        from payments.admin_alerts import on_payout_saved
        from payments.models import PayOut

        post_save.connect(on_payout_saved, sender=PayOut, dispatch_uid="admin_alert_payout")
