# from django.apps import AppConfig
#
#
# class SetUpConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'trade'
#
#     def ready(self):
#         from trade.create_defaults import create_defaults
#         create_defaults()


from django.apps import AppConfig


class BasicsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trade'