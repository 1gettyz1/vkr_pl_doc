from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Полная очистка БД и загрузка демо-сценария seed_demo"

    def handle(self, *args, **options):
        self.stdout.write("Очистка базы данных...")
        call_command("flush", interactive=False, verbosity=1)
        self.stdout.write("Загрузка seed_demo...")
        call_command("seed_demo")
        self.stdout.write(self.style.SUCCESS("База очищена и заполнена заново."))
