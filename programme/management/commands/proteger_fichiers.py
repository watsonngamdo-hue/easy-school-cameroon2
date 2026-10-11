"""Déplace les fichiers payants déjà en ligne vers le stockage privé.

À lancer une fois après la mise à jour (build.sh le fait automatiquement) :
    python manage.py proteger_fichiers
Les anciennes adresses publiques (/media/PDF/…, /media/epreuves/…) cessent alors de fonctionner.
"""
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from programme.models import AncienEpreuve, Lesson


class Command(BaseCommand):
    help = "Déplace les PDF des leçons et des anciennes épreuves vers le stockage privé."

    def handle(self, *args, **options):
        deplaces = manquants = 0
        elements = [(l, c) for l in Lesson.objects.all() for c in ("fpe", "pdf", "exercice")]
        elements += [(e, "fichier") for e in AncienEpreuve.objects.all()]
        for objet, champ in elements:
            fichier = getattr(objet, champ)
            if not fichier:
                continue
            prive = fichier.storage
            if prive.exists(fichier.name):
                continue
            if not default_storage.exists(fichier.name):
                manquants += 1
                continue
            with default_storage.open(fichier.name, "rb") as source:
                nouveau = prive.save(fichier.name, source)
            if nouveau != fichier.name:
                setattr(objet, champ, nouveau)
                objet.save(update_fields=[champ])
            default_storage.delete(fichier.name)
            deplaces += 1
        self.stdout.write(self.style.SUCCESS(f"{deplaces} fichier(s) protégé(s), {manquants} introuvable(s)."))
