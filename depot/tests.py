import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

from authapp.models import UserRegistration
import datetime

from programme.models import AncienEpreuve, Ecole, Matiere, Niveaux, Payment

from .models import EpreuveSoumise, MouvementSolde
from .services import publier_epreuve, rejeter_epreuve

TMP = tempfile.mkdtemp()


def pdf_epreuve(lignes, auteur="Lycée"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setAuthor(auteur)  # change les octets sans changer le texte
    y = 800
    for ligne in lignes:
        c.drawString(60, y, ligne)
        y -= 18
    c.save()
    return buf.getvalue()


SUJET_A = [
    "LYCEE BILINGUE DE DEIDO - DEUXIEME SEQUENCE - MATHEMATIQUES - TERMINALE C",
    "Exercice 1 : On considere la suite (un) definie par u0 = 1 et un+1 = 2un + 3.",
    "1. Montrer que la suite vn = un + 3 est geometrique.",
    "2. En deduire l'expression de un en fonction de n.",
    "Exercice 2 : Resoudre dans C l'equation z^2 - 2z + 5 = 0.",
]
SUJET_B = [
    "LYCEE DE JOSS - TROISIEME SEQUENCE - PHYSIQUE - TERMINALE C",
    "Exercice 1 : Un solide de masse m = 2 kg glisse sur un plan incline.",
    "1. Faire le bilan des forces appliquees au solide.",
    "2. Calculer l'acceleration du solide en appliquant le theoreme du centre d'inertie.",
    "Exercice 2 : Etude d'un circuit RLC serie en regime sinusoidal force.",
]


def photo(seed=0, size=(1200, 1600), qualite=90, redim=None):
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i in range(40):
        y = 60 + i * 36
        d.rectangle([80 + (i * 37 + seed * 101) % 200, y, 900 - (i * 53 + seed * 61) % 300, y + 14], fill="black")
    if redim:
        img = img.resize(redim)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=qualite)
    return out.getvalue()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        "private": {"BACKEND": "Elearning.storage.StockagePrive", "OPTIONS": {"location": TMP}},
    },
    DEPOT_RECOMPENSE_FCFA=25,
    MEDIA_ROOT=TMP,
)
class DepotTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.admin = UserRegistration.objects.create_superuser(email="admin@test.cm", password="x-Adm1n-pass")
        self.niveau = Niveaux.objects.create(niveau="Terminale")
        self.maths = Matiere.objects.create(matiere_id="M1", nom="Mathematiques Tle", niveau=self.niveau, description="-")
        self.pct = Matiere.objects.create(matiere_id="P1", nom="Physique Tle", niveau=self.niveau, description="-")
        self.autre_niveau = Niveaux.objects.create(niveau="Seconde")
        self.maths2 = Matiere.objects.create(matiere_id="M2", nom="Mathematiques 2nde", niveau=self.autre_niveau, description="-")
        self.eleve = UserRegistration.objects.create_user(email="eleve@test.cm", password="x-Eleve-pass", somme=100)
        self.eleve2 = UserRegistration.objects.create_user(email="eleve2@test.cm", password="x-Eleve-pass", somme=0)
        self.client.force_login(self.eleve)

    def envoyer(self, contenu, nom="epreuve.pdf", **extra):
        data = {
            "titre": "Maths 2e séquence",
            "niveau": self.niveau.pk,
            "matiere": self.maths.pk,
            "etablissement": "Lycée bilingue de Deïdo",
            "type_evaluation": "seq2",
            "annee_scolaire": "2025-2026",
            "certification": "on",
            "fichier": SimpleUploadedFile(nom, contenu),
        }
        data.update(extra)
        return self.client.post(reverse("depot:accueil"), data)

    def solde(self, user=None):
        return UserRegistration.objects.get(pk=(user or self.eleve).pk).somme

    # --- cas nominal -----------------------------------------------------
    def test_envoi_credite_25_et_enregistre(self):
        r = self.envoyer(pdf_epreuve(SUJET_A))
        self.assertRedirects(r, reverse("depot:merci"), fetch_redirect_response=False)
        self.assertEqual(EpreuveSoumise.objects.count(), 1)
        self.assertEqual(self.solde(), 125)
        e = EpreuveSoumise.objects.get()
        self.assertEqual(e.recompense, 25)
        self.assertIsNotNone(e.empreinte_texte)
        self.assertEqual(MouvementSolde.objects.get().montant, 25)
        self.assertEqual(MouvementSolde.objects.get().solde_apres, 125)

    # --- doublons --------------------------------------------------------
    def test_meme_fichier_refuse(self):
        contenu = pdf_epreuve(SUJET_A)
        self.envoyer(contenu)
        r = self.envoyer(contenu, nom="autre-nom.pdf", type_evaluation="seq3")
        self.assertContains(r, "déjà dans notre base")
        self.assertEqual(EpreuveSoumise.objects.count(), 1)
        self.assertEqual(self.solde(), 125)

    def test_meme_fichier_refuse_pour_un_autre_eleve(self):
        contenu = pdf_epreuve(SUJET_A)
        self.envoyer(contenu)
        self.client.force_login(self.eleve2)
        r = self.envoyer(contenu, type_evaluation="seq4")
        self.assertContains(r, "déjà dans notre base")
        self.assertEqual(self.solde(self.eleve2), 0)

    def test_meme_texte_reenregistre_refuse(self):
        self.envoyer(pdf_epreuve(SUJET_A, auteur="A"))
        copie = pdf_epreuve(SUJET_A, auteur="Copie modifiée")
        r = self.envoyer(copie, type_evaluation="seq5")
        self.assertContains(r, "même contenu")
        self.assertEqual(EpreuveSoumise.objects.count(), 1)

    def test_meme_evaluation_meme_etablissement_refusee(self):
        self.envoyer(pdf_epreuve(SUJET_A))
        # Autre fichier, mais même établissement (écrit autrement), classe, matière, séquence, année.
        r = self.envoyer(photo(1), nom="photo.jpg", etablissement="LYCEE BILINGUE DEIDO")
        self.assertContains(r, "a déjà été envoyée")
        self.assertEqual(self.solde(), 125)

    def test_image_recompressee_refusee(self):
        self.envoyer(photo(3, qualite=92), nom="a.jpg")
        r = self.envoyer(photo(3, qualite=60, redim=(900, 1200)), nom="b.jpg", type_evaluation="seq6")
        self.assertContains(r, "image identique")
        self.assertEqual(EpreuveSoumise.objects.count(), 1)

    def test_epreuves_differentes_acceptees(self):
        self.envoyer(pdf_epreuve(SUJET_A))
        self.envoyer(pdf_epreuve(SUJET_B), titre="Physique 3e séquence", matiere=self.pct.pk, type_evaluation="seq3",
                     etablissement="Lycée de Joss")
        self.envoyer(photo(7), nom="devoir.jpg", type_evaluation="devoir", titre="Devoir de maths")
        self.assertEqual(EpreuveSoumise.objects.count(), 3)
        self.assertEqual(self.solde(), 175)

    # --- validations ----------------------------------------------------
    def test_faux_pdf_refuse(self):
        r = self.envoyer(b"<html><script>alert(1)</script></html>", nom="piege.pdf")
        self.assertContains(r, "pas un vrai PDF")
        self.assertEqual(self.solde(), 100)

    def test_extension_interdite(self):
        r = self.envoyer(b"MZ\x90\x00", nom="virus.exe")
        self.assertContains(r, "Format non accepté")

    def test_matiere_d_une_autre_classe_refusee(self):
        r = self.envoyer(pdf_epreuve(SUJET_A), matiere=self.maths2.pk)
        self.assertContains(r, "n&#x27;appartient pas")
        self.assertEqual(EpreuveSoumise.objects.count(), 0)

    def test_certification_obligatoire(self):
        data_sans = {"certification": ""}
        r = self.envoyer(pdf_epreuve(SUJET_A), **data_sans)
        self.assertEqual(EpreuveSoumise.objects.count(), 0)
        self.assertEqual(r.status_code, 200)

    def test_anonyme_redirige_vers_connexion(self):
        self.client.logout()
        r = self.envoyer(pdf_epreuve(SUJET_A))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])
        self.assertEqual(EpreuveSoumise.objects.count(), 0)

    # --- rejet et accès aux fichiers ---------------------------------------
    def test_rejet_reprend_la_recompense(self):
        self.envoyer(pdf_epreuve(SUJET_A))
        rejeter_epreuve(EpreuveSoumise.objects.get(), "Illisible")
        self.assertEqual(self.solde(), 100)
        self.assertEqual(MouvementSolde.objects.count(), 2)
        # Rejeter deux fois ne reprend pas deux fois.
        rejeter_epreuve(EpreuveSoumise.objects.get(), "Illisible")
        self.assertEqual(self.solde(), 100)

    def test_fichier_prive_inaccessible_aux_autres_eleves(self):
        self.envoyer(pdf_epreuve(SUJET_A))
        e = EpreuveSoumise.objects.get()
        self.assertEqual(self.client.get(reverse("depot:fichier", args=[e.pk])).status_code, 200)
        self.client.force_login(self.eleve2)
        self.assertEqual(self.client.get(reverse("depot:fichier", args=[e.pk])).status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("depot:fichier", args=[e.pk])).status_code, 200)

    def test_pdf_scanne_reenregistre_refuse(self):
        def scan_pdf(qualite):
            img = Image.open(io.BytesIO(photo(5, qualite=qualite)))
            out = io.BytesIO()
            img.save(out, format="PDF", resolution=100)
            return out.getvalue()
        self.envoyer(scan_pdf(90), nom="scan.pdf")
        r = self.envoyer(scan_pdf(55), nom="scan-copie.pdf", type_evaluation="trim1")
        self.assertContains(r, "image identique")
        self.assertEqual(EpreuveSoumise.objects.count(), 1)

    # --- publication automatique dans la banque d'épreuves ---------------
    def test_publication_automatique_visible_par_les_abonnes(self):
        self.envoyer(pdf_epreuve(SUJET_A))
        e = EpreuveSoumise.objects.get()
        pub = AncienEpreuve.objects.get()
        self.assertEqual(e.publication, pub)
        self.assertEqual((pub.niveau, pub.matiere, pub.annee), (self.niveau, self.maths, 2026))
        self.assertEqual(pub.ecole.nom, "Lycée bilingue de Deïdo")
        with pub.fichier.open("rb") as f:
            self.assertTrue(f.read(4) == b"%PDF")
        # Un autre élève abonné à la classe la voit dans la banque.
        today = datetime.date.today()
        Payment.objects.create(user=self.eleve2, niveau=self.niveau, montant=1000, date_pay=today,
                               date_expired=today + datetime.timedelta(days=30))
        self.client.force_login(self.eleve2)
        r = self.client.get(reverse("programme:liste_anciennes_epreuves", args=[self.niveau.slug]))
        self.assertContains(r, "Maths 2e séquence")
        self.assertContains(r, "Mathematiques Tle")

    def test_photo_convertie_en_pdf(self):
        self.envoyer(photo(9), nom="photo.jpg", type_evaluation="trim2")
        with AncienEpreuve.objects.get().fichier.open("rb") as f:
            self.assertEqual(f.read(4), b"%PDF")

    def test_meme_etablissement_ecrit_autrement_une_seule_ecole(self):
        self.envoyer(pdf_epreuve(SUJET_A))
        self.envoyer(pdf_epreuve(SUJET_B), titre="Physique 3e séquence", matiere=self.pct.pk,
                     type_evaluation="seq3", etablissement="LYCEE BILINGUE DEIDO")
        self.assertEqual(Ecole.objects.count(), 1)
        self.assertEqual(AncienEpreuve.objects.count(), 2)

    def test_rejet_retire_de_la_banque(self):
        self.envoyer(pdf_epreuve(SUJET_A))
        rejeter_epreuve(EpreuveSoumise.objects.get(), "Illisible")
        self.assertEqual(AncienEpreuve.objects.count(), 0)
        self.assertIsNone(EpreuveSoumise.objects.get().publication)

    def test_publication_manuelle_si_desactivee(self):
        with self.settings(DEPOT_PUBLICATION_AUTO=False):
            self.envoyer(pdf_epreuve(SUJET_A))
        self.assertEqual(AncienEpreuve.objects.count(), 0)
        self.assertEqual(self.solde(), 125)
        publier_epreuve(EpreuveSoumise.objects.get())
        self.assertEqual(AncienEpreuve.objects.count(), 1)
