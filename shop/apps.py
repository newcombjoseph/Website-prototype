from django.apps import AppConfig

class ShopConfig(AppConfig):
    name = 'shop'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from . import checks  # noqa: F401
