"""Renseigne le nom et le domaine du site (utilisés dans les e-mails et le plan du site).

    python manage.py configurer_site            # domaine lu dans SITE_DOMAIN ou RENDER_EXTERNAL_HOSTNAME
    python manage.py configurer_site --domaine easyschoolcameroon.com
"""
import os

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Configure le domaine et le nom du site."

    def add_arguments(self, parser):
        parser.add_argument("--domaine")

    def handle(self, *args, **options):
        domaine = (options.get("domaine") or os.environ.get("SITE_DOMAIN") or os.environ.get("RENDER_EXTERNAL_HOSTNAME")
                   or next((h for h in settings.ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1", "*")), "easyschoolcameroon.com"))
        site, _ = Site.objects.update_or_create(pk=settings.SITE_ID, defaults={"domain": domaine, "name": "EasySchool Cameroun"})
        self.stdout.write(self.style.SUCCESS(f"Site configuré : {site.name} ({site.domain})"))
