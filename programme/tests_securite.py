"""Tests de non-régression des failles corrigées."""
import datetime
import json

from django.test import TestCase
from django.urls import reverse

from aiapp.models import Pack
from authapp.models import UserRegistration
from programme.models import Commentaire, Lesson, Matiere, Niveaux, Payment


class SecuriteTests(TestCase):
    def setUp(self):
        self.admin = UserRegistration.objects.create_superuser(email="admin@t.cm", password="x-Adm1n-pass")
        self.user = UserRegistration.objects.create_user(email="u@t.cm", password="x-User-pass", somme=1000)
        self.n1 = Niveaux.objects.create(niveau="Seconde")
        self.n2 = Niveaux.objects.create(niveau="Terminale")
        self.m1 = Matiere.objects.create(matiere_id="a", nom="Maths 2nde", niveau=self.n1, description="-")
        self.m2 = Matiere.objects.create(matiere_id="b", nom="Maths Tle", niveau=self.n2, description="-")
        self.l1 = Lesson.objects.create(lesson_id="l1", niveau=self.n1, creer_par=self.admin, matiere=self.m1, nom="Fonctions", position=1)
        self.l2 = Lesson.objects.create(lesson_id="l2", niveau=self.n2, creer_par=self.admin, matiere=self.m2, nom="Integrales", position=1)
        today = datetime.date.today()
        Payment.objects.create(user=self.user, niveau=self.n1, montant=1000, date_pay=today, date_expired=today + datetime.timedelta(days=30))
        self.user.classe.add(self.n1)
        self.client.force_login(self.user)

    def test_achat_credits_montant_negatif_refuse(self):
        r = self.client.post(reverse("aiapp:buy_credits"), {"amount": "-100000"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.somme, 1000)

    def test_achat_credits_pack_valide(self):
        Pack.objects.create(name="Starter", price=500, credit=100)
        self.client.post(reverse("aiapp:buy_credits"), {"amount": "100"})
        self.user.refresh_from_db()
        self.assertEqual((self.user.somme, self.user.wallet_credits), (500, 100))

    def test_lecon_d_un_niveau_non_paye_inaccessible(self):
        # Abonné en Seconde, tente d'ouvrir une leçon de Terminale via l'URL de Seconde.
        url = reverse("programme:lecon_detail", args=[self.n1.slug, self.m1.slug, self.l2.slug])
        self.assertEqual(self.client.get(url).status_code, 404)
        ok = reverse("programme:lecon_detail", args=[self.n1.slug, self.m1.slug, self.l1.slug])
        self.assertEqual(self.client.get(ok).status_code, 200)

    def test_commentaire_html_echappe(self):
        url = reverse("programme:lecon_detail", args=[self.n1.slug, self.m1.slug, self.l1.slug])
        self.client.post(url, {"corps": "<script>alert('xss')</script>"})
        self.assertTrue(Commentaire.objects.exists())
        r = self.client.get(url)
        self.assertNotContains(r, "<script>alert('xss')</script>", html=False)
        self.assertContains(r, "&lt;script&gt;")

    def test_deconnexion_par_get_impossible(self):
        self.client.get("/accounts/logout/")
        self.assertIn("_auth_user_id", self.client.session)

    def test_assistant_ia_exige_csrf(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.user)
        r = c.post(reverse("aiapp:index"), data=json.dumps({"action": "new_conversation"}),
                   content_type="application/json", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 403)

    def test_paiement_anonyme_redirige(self):
        self.client.logout()
        r = self.client.post(reverse("programme:pay"), {"numero": "1", "reference": "x"})
        self.assertEqual(r.status_code, 302)

    def test_abonnement_solde_insuffisant(self):
        r = self.client.post(reverse("programme:billing"), {"niveau": self.n2.pk, "montant": 5000})
        self.user.refresh_from_db()
        self.assertEqual(self.user.somme, 1000)
        self.assertFalse(self.user.classe.filter(pk=self.n2.pk).exists())

    def test_en_tetes_securite(self):
        r = self.client.get("/")
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
