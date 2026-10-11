import datetime
import io
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from authapp.models import SessionAppareil, UserRegistration
from programme.models import AccesDocument, AncienEpreuve, Ecole, Lesson, Matiere, Niveaux, Payment

TMP = tempfile.mkdtemp()


def pdf_bytes():
    out = io.BytesIO()
    c = canvas.Canvas(out)
    c.drawString(60, 760, "Sujet de mathematiques")
    c.save()
    return out.getvalue()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": TMP}},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        "private": {"BACKEND": "Elearning.storage.StockagePrive", "OPTIONS": {"location": TMP + "/prive"}},
    },
    MEDIA_ROOT=TMP, MAX_APPAREILS_PAR_COMPTE=2,
)
class ProtectionTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.admin = UserRegistration.objects.create_superuser(email="admin@t.cm", password="x-Admin-1234")
        self.abonne = UserRegistration.objects.create_user(email="abonne@t.cm", password="x-Pass-1234", first_name="Awa", last_name="Ngo")
        self.non_abonne = UserRegistration.objects.create_user(email="libre@t.cm", password="x-Pass-1234")
        self.niveau = Niveaux.objects.create(niveau="Terminale")
        m = Matiere.objects.create(matiere_id="m", nom="Maths", niveau=self.niveau, description="-")
        self.lecon = Lesson.objects.create(lesson_id="l", niveau=self.niveau, creer_par=self.admin, matiere=m, nom="Suites", position=1)
        self.lecon.pdf.save("lecon.pdf", ContentFile(pdf_bytes()))
        self.epreuve = AncienEpreuve(titre="Maths seq 2", niveau=self.niveau, ecole=Ecole.objects.create(nom="Lycée"))
        self.epreuve.fichier.save("e.pdf", ContentFile(pdf_bytes()))
        today = datetime.date.today()
        Payment.objects.create(user=self.abonne, niveau=self.niveau, montant=1000, date_pay=today, date_expired=today + datetime.timedelta(days=30))

    def test_fichiers_hors_media_public(self):
        self.assertEqual(self.lecon.pdf.url, "")
        self.assertIn("prive", self.lecon.pdf.storage.location)

    def test_document_filigrane_au_nom_de_l_eleve(self):
        self.client.force_login(self.abonne)
        r = self.client.get(reverse("programme:document_epreuve", args=[self.epreuve.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r["Cache-Control"])
        texte = PdfReader(io.BytesIO(r.content)).pages[0].extract_text()
        self.assertIn("abonne@t.cm", texte)
        self.assertIn("Awa Ngo", texte)
        self.assertEqual(AccesDocument.objects.filter(utilisateur=self.abonne).count(), 1)

    def test_non_abonne_et_anonyme_refuses(self):
        self.client.force_login(self.non_abonne)
        self.assertEqual(self.client.get(reverse("programme:document_lecon", args=[self.lecon.pk, "pdf"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("programme:lire_lecon", args=[self.lecon.pk, "pdf"])).status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("programme:document_lecon", args=[self.lecon.pk, "pdf"])).status_code, 302)

    def test_champ_inconnu(self):
        self.client.force_login(self.abonne)
        self.assertEqual(self.client.get(reverse("programme:document_lecon", args=[self.lecon.pk, "secret"])).status_code, 404)

    def test_limite_d_appareils(self):
        clients = []
        for i in range(3):
            c = Client(HTTP_USER_AGENT=f"Telephone {i}")
            self.assertTrue(c.login(email="abonne@t.cm", password="x-Pass-1234"))
            clients.append(c)
        self.assertEqual(SessionAppareil.objects.filter(utilisateur=self.abonne).count(), 2)
        # Le premier appareil a été déconnecté, les deux derniers restent connectés.
        r = clients[0].get(reverse("programme:lire_epreuve", args=[self.epreuve.pk]))
        self.assertEqual(r.status_code, 302)
        r = clients[2].get(reverse("programme:lire_epreuve", args=[self.epreuve.pk]))
        self.assertEqual(r.status_code, 200)

    def test_fichier_manquant_ne_plante_pas(self):
        self.lecon.pdf.storage.delete(self.lecon.pdf.name)
        self.client.force_login(self.abonne)
        r = self.client.get(reverse("programme:document_lecon", args=[self.lecon.pk, "pdf"]))
        self.assertEqual(r.status_code, 404)
