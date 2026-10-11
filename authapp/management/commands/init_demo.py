"""Prépare une base de démonstration : contenu pédagogique + comptes de test.

    python manage.py init_demo

Les identifiants sont lus dans DEMO_ADMIN_EMAIL / DEMO_ADMIN_PASSWORD et
DEMO_ELEVE_EMAIL / DEMO_ELEVE_PASSWORD (aucun mot de passe n'est écrit en dur).
"""
import datetime
import os

from allauth.account.models import EmailAddress
from django.core.management import call_command
from django.core.management.base import BaseCommand

from authapp.models import UserRegistration
from programme.models import Lesson, Matiere, Niveaux, Payment
from programme.programme_officiel import completer_programme


class Command(BaseCommand):
    help = "Initialise la base de démonstration (idempotent)."

    def _user(self, email, password, **extra):
        user, created = UserRegistration.objects.get_or_create(email=email, defaults=extra)
        if created:
            user.set_password(password)
            user.save()
        EmailAddress.objects.get_or_create(user=user, email=email, defaults={"verified": True, "primary": True})
        return user, created

    def handle(self, *args, **options):
        admin_email = os.environ.get("DEMO_ADMIN_EMAIL")
        admin_pwd = os.environ.get("DEMO_ADMIN_PASSWORD")
        if not (admin_email and admin_pwd):
            self.stderr.write("DEMO_ADMIN_EMAIL et DEMO_ADMIN_PASSWORD sont requis.")
            return
        admin, _ = self._user(admin_email, admin_pwd, first_name="Admin", last_name="EasySchool",
                              is_staff=True, is_superuser=True, ville="Douala")
        if not Lesson.objects.exists() and not Niveaux.objects.exists():
            # Les leçons du fichier de démonstration sont rattachées à l'utilisateur n°1.
            if admin.pk != 1:
                self.stderr.write("Le compte administrateur doit être le premier utilisateur créé.")
                return
            call_command("loaddata", "contenu_demo", verbosity=0)
            self.stdout.write("Contenu pédagogique chargé.")
        classes, matieres = completer_programme(Niveaux, Matiere)
        if classes or matieres:
            self.stdout.write(f"{classes} classe(s) et {matieres} matière(s) ajoutée(s) (6e à Terminale).")

        eleve_email = os.environ.get("DEMO_ELEVE_EMAIL")
        eleve_pwd = os.environ.get("DEMO_ELEVE_PASSWORD")
        if eleve_email and eleve_pwd:
            eleve, created = self._user(eleve_email, eleve_pwd, first_name="Awa", last_name="Démo",
                                        ville="Yaoundé", bonus_bienvenue_recu=True, is_first_login=False)
            if created:
                niveau = Niveaux.objects.filter(slug="terminale").first() or Niveaux.objects.last()
                if niveau:
                    eleve.classe.add(niveau)
                    today = datetime.date.today()
                    Payment.objects.create(user=eleve, niveau=niveau, montant=3000, date_pay=today,
                                           date_expired=today + datetime.timedelta(days=90))
                eleve.somme = 1500
                eleve.save(update_fields=["somme"])
        self.stdout.write(self.style.SUCCESS("Base de démonstration prête."))
