from django.core.management.base import BaseCommand

from programme.models import Matiere, Niveaux
from programme.programme_officiel import completer_programme


class Command(BaseCommand):
    help = "Ajoute les classes de la 6e à la Terminale et leurs matières de base manquantes (sans rien supprimer)."

    def handle(self, *args, **options):
        classes, matieres = completer_programme(Niveaux, Matiere)
        self.stdout.write(self.style.SUCCESS(f"{classes} classe(s) et {matieres} matière(s) ajoutée(s)."))
