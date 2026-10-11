"""Crée un professeur de démonstration vérifié avec deux cours (idempotent).

    python manage.py demo_professeur [--video chemin.mp4]
"""
import io
import os

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from authapp.models import UserRegistration
from profs.models import CoursProf, LeconProf, ProfilProfesseur
from programme.models import Matiere, Niveaux


def pdf(titre, lignes):
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(60, 780, titre)
    c.setFont("Helvetica", 12)
    y = 740
    for ligne in lignes:
        c.drawString(60, y, ligne)
        y -= 22
    c.save()
    return out.getvalue()


class Command(BaseCommand):
    help = "Crée un professeur de démonstration (identité vérifiée) avec des cours."

    def add_arguments(self, parser):
        parser.add_argument("--video", help="Fichier MP4 à utiliser pour la leçon vidéo")

    def handle(self, *args, **options):
        email = os.environ.get("DEMO_PROF_EMAIL", "prof.demo@easyschool.cm")
        user, cree = UserRegistration.objects.get_or_create(email=email, defaults={"first_name": "Paul", "last_name": "Ngono", "ville": "Douala"})
        if cree:
            mdp = os.environ.get("DEMO_PROF_PASSWORD")
            user.set_password(mdp) if mdp else user.set_unusable_password()
            user.save()
        tle = Niveaux.objects.filter(slug="terminale").first()
        if tle is None:
            self.stderr.write("Classe Terminale introuvable : lance d'abord completer_programme.")
            return
        profil, _ = ProfilProfesseur.objects.get_or_create(user=user, defaults={
            "nom_public": "M. Ngono — Mathématiques", "bio": "Professeur de mathématiques depuis 12 ans au lycée de Joss (Douala). "
            "Je prépare au Baccalauréat C et D avec des cours courts, des méthodes claires et beaucoup d'exercices corrigés.",
            "etablissement": "Lycée de Joss, Douala", "matieres_texte": "Mathématiques", "prix_mensuel": 1500,
            "operateur": "mtn", "numero_retrait": "670000000", "statut": ProfilProfesseur.Statut.VERIFIE,
        })
        profil.niveaux.add(tle)
        maths = Matiere.objects.filter(niveau=tle, nom__istartswith="Math").first()
        if profil.cours.exists():
            self.stdout.write("Professeur de démonstration déjà présent.")
            return
        cours = CoursProf.objects.create(professeur=profil, titre="Suites numériques — Terminale C et D", niveau=tle, matiere=maths, publie=True,
                                         description="Comprendre et maîtriser les suites : sens de variation, suites arithmétiques et géométriques, "
                                                     "limites et raisonnement par récurrence. Avec des exercices type Bac.")
        intro = LeconProf(cours=cours, titre="Introduction : qu'est-ce qu'une suite ?", type="pdf", ordre=1, apercu_gratuit=True, duree_minutes=10)
        intro.pdf.save("intro.pdf", ContentFile(pdf("Introduction aux suites", [
            "Une suite (un) associe a chaque entier naturel n un nombre reel un.",
            "Exemple : un = 2n + 1 donne 1, 3, 5, 7, ...",
            "On peut definir une suite de facon explicite ou par recurrence.",
        ])), save=True)
        if options.get("video") and os.path.exists(options["video"]):
            video = LeconProf(cours=cours, titre="Suites arithmético-géométriques", type="video", ordre=2, duree_minutes=12)
            with open(options["video"], "rb") as f:
                video.video.save("lecon.mp4", File(f), save=True)
        exos = LeconProf(cours=cours, titre="Exercices corrigés type Bac", type="pdf", ordre=3, duree_minutes=40)
        exos.pdf.save("exos.pdf", ContentFile(pdf("Exercices corriges", [
            "Exercice 1 : Soit u0 = 1 et un+1 = 2un + 3. Montrer que vn = un + 3 est geometrique.",
            "Corrige : vn+1 = un+1 + 3 = 2un + 6 = 2(un + 3) = 2vn. Donc (vn) est geometrique de raison 2.",
        ])), save=True)
        cours2 = CoursProf.objects.create(professeur=profil, titre="Fonction logarithme népérien", niveau=tle, matiere=maths, publie=True,
                                          description="Définition, propriétés algébriques, étude de fonctions et limites de référence.")
        l = LeconProf(cours=cours2, titre="Propriétés de ln", type="pdf", ordre=1, apercu_gratuit=True, duree_minutes=15)
        l.pdf.save("ln.pdf", ContentFile(pdf("Proprietes de ln", ["ln(ab) = ln(a) + ln(b)", "ln(a/b) = ln(a) - ln(b)"])), save=True)
        self.stdout.write(self.style.SUCCESS("Professeur de démonstration créé."))
