import datetime
import io
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from reportlab.pdfgen import canvas

from authapp.models import UserRegistration
from programme.models import Matiere, Niveaux

from .models import AbonnementProf, CoursProf, DemandeRetrait, LeconProf, MouvementProf, PieceIdentite, ProfilProfesseur
from .services import OperationRefusee, abonner, demander_retrait, refuser_retrait

TMP = tempfile.mkdtemp()


def image(nom="photo.jpg"):
    out = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(out, format="JPEG")
    return SimpleUploadedFile(nom, out.getvalue(), content_type="image/jpeg")


def pdf_bytes(texte="Cours de maths"):
    out = io.BytesIO()
    c = canvas.Canvas(out)
    c.drawString(60, 760, texte)
    c.save()
    return out.getvalue()


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4000


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": TMP}},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        "private": {"BACKEND": "Elearning.storage.StockagePrive", "OPTIONS": {"location": TMP + "/prive"}},
    },
    MEDIA_ROOT=TMP, PROF_COMMISSION_PLATEFORME=30, PROF_DELAI_DISPONIBILITE_JOURS=7, PROF_RETRAIT_MINIMUM=5000,
)
class ProfsTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.niveau = Niveaux.objects.create(niveau="Terminale")
        self.maths = Matiere.objects.create(matiere_id="m", nom="Mathématiques (TERMINALE)", niveau=self.niveau, description="-")
        self.prof_user = UserRegistration.objects.create_user(email="prof@t.cm", password="x-Prof-1234", first_name="Jean")
        self.eleve = UserRegistration.objects.create_user(email="eleve@t.cm", password="x-Eleve-1234", somme=5000, first_name="Awa")
        self.autre = UserRegistration.objects.create_user(email="autre@t.cm", password="x-Eleve-1234", somme=0)
        self.admin = UserRegistration.objects.create_superuser(email="admin@t.cm", password="x-Admin-1234")

    def profil_verifie(self, prix=1000):
        p = ProfilProfesseur.objects.create(
            user=self.prof_user, nom_public="M. Ngono — Maths", bio="Prof de maths", matieres_texte="Maths",
            prix_mensuel=prix, operateur="mtn", numero_retrait="670000000", statut=ProfilProfesseur.Statut.VERIFIE,
        )
        p.niveaux.add(self.niveau)
        return p

    def cours_avec_lecons(self, profil):
        cours = CoursProf.objects.create(professeur=profil, titre="Suites numériques", description="Tout sur les suites",
                                         niveau=self.niveau, matiere=self.maths, publie=True)
        apercu = LeconProf(cours=cours, titre="Introduction", type="pdf", apercu_gratuit=True, ordre=1)
        apercu.pdf.save("a.pdf", ContentFile(pdf_bytes("Introduction")), save=True)
        payante = LeconProf(cours=cours, titre="Limites", type="pdf", ordre=2)
        payante.pdf.save("b.pdf", ContentFile(pdf_bytes("Limites")), save=True)
        video = LeconProf(cours=cours, titre="Vidéo", type="video", ordre=3)
        video.video.save("v.mp4", ContentFile(MP4), save=True)
        return cours, apercu, payante, video

    # --- inscription et vérification -------------------------------------
    def test_dossier_professeur_complet_passe_en_attente(self):
        self.client.force_login(self.prof_user)
        r = self.client.post(reverse("profs:devenir"), {
            "nom_public": "M. Ngono", "bio": "Bio", "etablissement": "Lycée de Joss", "niveaux": [self.niveau.pk],
            "matieres_texte": "Maths", "prix_mensuel": 1500, "operateur": "orange", "numero_retrait": "+237 690 00 00 00",
            "cni_recto": image("r.jpg"), "cni_verso": image("v.jpg"), "selfie": image("s.jpg"), "justificatif": image("j.jpg"),
        })
        self.assertRedirects(r, reverse("profs:studio"), fetch_redirect_response=False)
        p = ProfilProfesseur.objects.get()
        self.assertEqual(p.statut, "attente")
        self.assertEqual(p.numero_retrait, "690000000")
        self.assertEqual(p.pieces.count(), 4)
        # Les pièces sont privées : seul le staff peut les ouvrir.
        piece = p.pieces.first()
        self.assertNotEqual(self.client.get(reverse("profs:piece", args=[piece.pk])).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("profs:piece", args=[piece.pk])).status_code, 200)

    def test_cours_invisible_tant_que_non_verifie(self):
        p = self.profil_verifie()
        p.statut = ProfilProfesseur.Statut.EN_ATTENTE
        p.save()
        cours, *_ = self.cours_avec_lecons(p)
        self.assertEqual(self.client.get(reverse("profs:cours", args=[cours.slug])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("profs:catalogue")), "Suites numériques")

    # --- abonnement et partage des revenus -------------------------------
    def test_abonnement_debite_eleve_et_partage_70_30(self):
        p = self.profil_verifie(prix=1000)
        self.client.force_login(self.eleve)
        self.client.post(reverse("profs:abonner", args=[p.slug]))
        self.eleve.refresh_from_db()
        self.assertEqual(self.eleve.somme, 4000)
        a = AbonnementProf.objects.get()
        self.assertEqual((a.part_professeur, a.part_plateforme), (700, 300))
        self.assertAlmostEqual((a.fin - a.debut).days, 30)
        # Gain non retirable avant 7 jours
        self.assertEqual(p.solde_disponible(), 0)
        self.assertEqual(p.solde_en_attente(), 700)

    def test_reabonnement_prolonge(self):
        p = self.profil_verifie()
        a1 = abonner(self.eleve, p)
        a2 = abonner(self.eleve, p)
        self.assertEqual(a2.debut, a1.fin)

    def test_solde_insuffisant_refuse(self):
        p = self.profil_verifie()
        with self.assertRaises(OperationRefusee):
            abonner(self.autre, p)
        self.assertEqual(AbonnementProf.objects.count(), 0)

    def test_pas_d_abonnement_a_soi_meme(self):
        p = self.profil_verifie()
        self.prof_user.somme = 5000
        self.prof_user.save()
        with self.assertRaises(OperationRefusee):
            abonner(self.prof_user, p)

    # --- accès aux leçons --------------------------------------------------
    def test_acces_lecons(self):
        p = self.profil_verifie()
        cours, apercu, payante, video = self.cours_avec_lecons(p)
        self.client.force_login(self.autre)
        self.assertEqual(self.client.get(reverse("profs:lecon_media", args=[apercu.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("profs:lecon_media", args=[payante.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("profs:lecon", args=[payante.pk])).status_code, 302)
        abonner(self.eleve, p)
        self.client.force_login(self.eleve)
        r = self.client.get(reverse("profs:lecon_media", args=[payante.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        r = self.client.get(reverse("profs:lecon_media", args=[video.pk]), HTTP_RANGE="bytes=0-99")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Range"], f"bytes 0-99/{len(MP4)}")

    def test_abonnement_expire_coupe_l_acces(self):
        p = self.profil_verifie()
        cours, apercu, payante, video = self.cours_avec_lecons(p)
        a = abonner(self.eleve, p)
        AbonnementProf.objects.filter(pk=a.pk).update(fin=timezone.now() - datetime.timedelta(minutes=1))
        self.client.force_login(self.eleve)
        self.assertEqual(self.client.get(reverse("profs:lecon_media", args=[payante.pk])).status_code, 404)

    # --- retraits ----------------------------------------------------------
    def test_retrait(self):
        p = self.profil_verifie(prix=10000)
        for _ in range(1):
            abonner(self.eleve if self.eleve.somme >= 10000 else self._crediter(), p)
        MouvementProf.objects.update(disponible_le=timezone.now() - datetime.timedelta(days=1))
        self.assertEqual(p.solde_disponible(), 7000)
        with self.assertRaises(OperationRefusee):
            demander_retrait(p, 4000)  # sous le minimum
        r = demander_retrait(p, 6000)
        self.assertEqual(p.solde_disponible(), 1000)
        with self.assertRaises(OperationRefusee):
            demander_retrait(p, 1000)  # une demande déjà en cours
        refuser_retrait(r, "Numéro injoignable")
        self.assertEqual(p.solde_disponible(), 7000)
        self.assertEqual(DemandeRetrait.objects.get().statut, "refusee")

    def _crediter(self):
        self.eleve.somme = 20000
        self.eleve.save()
        return self.eleve

    def test_studio_ajout_lecon_video_refuse_un_faux_fichier(self):
        p = self.profil_verifie()
        cours = CoursProf.objects.create(professeur=p, titre="C", description="d", niveau=self.niveau)
        self.client.force_login(self.prof_user)
        r = self.client.post(reverse("profs:studio_cours", args=[cours.pk]), {
            "ajouter_lecon": "1", "titre": "Piège", "type": "video", "ordre": 1,
            "video": SimpleUploadedFile("x.mp4", b"<html>pas une video</html>"),
        })
        self.assertEqual(LeconProf.objects.count(), 0)
        self.assertContains(r, "pas une vraie vidéo")
        r = self.client.post(reverse("profs:studio_cours", args=[cours.pk]), {
            "ajouter_lecon": "1", "titre": "Bonne", "type": "video", "ordre": 1, "video": SimpleUploadedFile("x.mp4", MP4),
        })
        self.assertEqual(LeconProf.objects.count(), 1)

    def test_un_prof_ne_modifie_pas_le_cours_d_un_autre(self):
        p = self.profil_verifie()
        cours = CoursProf.objects.create(professeur=p, titre="C", description="d", niveau=self.niveau)
        self.client.force_login(self.eleve)
        ProfilProfesseur.objects.create(user=self.eleve, nom_public="Autre", bio="b", matieres_texte="x",
                                        operateur="mtn", numero_retrait="670000001")
        self.assertEqual(self.client.get(reverse("profs:studio_cours", args=[cours.pk])).status_code, 404)

    def test_tableau_de_bord_de_classe_affiche_les_cours_des_profs(self):
        p = self.profil_verifie()
        self.cours_avec_lecons(p)
        self.eleve.classe.add(self.niveau)
        self.client.force_login(self.eleve)
        r = self.client.get(reverse("programme:student_dashboard", args=[self.niveau.slug]))
        self.assertContains(r, "Cours des professeurs")
        self.assertContains(r, "Suites numériques")
        self.assertContains(r, reverse("profs:mes_abonnements"))  # bouton dans le menu utilisateur
