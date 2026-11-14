from django.core.management.base import BaseCommand

from appeals.notify import nudge_unanswered_provider_appeals


class Command(BaseCommand):
    help = "Send '?' in provider chats for unanswered appeals older than 1h / 3h."

    def handle(self, *args, **options):
        sent = nudge_unanswered_provider_appeals()
        self.stdout.write(self.style.SUCCESS(f"nudged {sent} appeal(s)"))
