from django.apps import AppConfig


class BpmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bpm"
    label = "bpm"
    verbose_name = "Бизнес-процессы"
