import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from authapp.models import UserRegistration

from .models import AIMessage, AIModel, AISettings, ReponseEnCache


def faux_flux(*args, **kwargs):
    yield "Une fonction affine "
    yield "s'écrit f(x) = ax + b."


def flux_erreur(*args, **kwargs):
    yield "[Erreur : Le service est actuellement très sollicité.]"


class CacheIATests(TestCase):
    def setUp(self):
        AISettings.objects.create(id=1, default_daily_credits=0, file_upload_cost=20)
        AIModel.objects.create(name="GPT-4o mini", api_value="gpt-4o-mini", model_type="chat", provider="openai", cost=10)
        AIModel.objects.create(name="Gemini", api_value="gemini-3-flash-preview", model_type="chat", provider="gemini", cost=15)
        self.a = UserRegistration.objects.create_user(email="a@t.cm", password="x-Pass-1234", wallet_credits=100)
        self.b = UserRegistration.objects.create_user(email="b@t.cm", password="x-Pass-1234", wallet_credits=100)

    def poser(self, user, question, model="gpt-4o-mini", conversation_id=None):
        self.client.force_login(user)
        payload = {"action": "chat", "message": question, "model": model}
        if conversation_id:
            payload["conversation_id"] = conversation_id
        r = self.client.post(reverse("aiapp:index"), data=json.dumps(payload), content_type="application/json",
                             HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        corps = b"".join(r.streaming_content).decode()
        meta, _, texte = corps.partition("\n")
        return json.loads(meta), texte

    def credits(self, user):
        user.refresh_from_db()
        return user.daily_credits + user.wallet_credits

    @patch("aiapp.views.AIService.stream_chat_response", side_effect=faux_flux)
    def test_meme_question_sans_appel_api_mais_eleve_debite(self, mock_api):
        _, t1 = self.poser(self.a, "Qu'est-ce qu'une fonction affine ?")
        _, t2 = self.poser(self.b, "  qu'est-ce qu'une FONCTION affine?")  # même question, écrite autrement
        self.assertEqual(mock_api.call_count, 1)
        self.assertEqual(t1, t2)
        self.assertEqual(self.credits(self.a), 190)
        self.assertEqual(self.credits(self.b), 190)  # débité malgré la réutilisation
        self.assertTrue(AIMessage.objects.get(user=self.b).depuis_cache)
        self.assertEqual(ReponseEnCache.objects.get().utilisations, 1)

    @patch("aiapp.views.AIService.stream_chat_response", side_effect=faux_flux)
    def test_autre_modele_rappelle_l_api(self, mock_api):
        self.poser(self.a, "Qu'est-ce qu'une fonction affine ?")
        self.poser(self.b, "Qu'est-ce qu'une fonction affine ?", model="gemini-3-flash-preview")
        self.assertEqual(mock_api.call_count, 2)

    @patch("aiapp.views.AIService.stream_chat_response", side_effect=faux_flux)
    def test_question_dans_une_conversation_non_reutilisee(self, mock_api):
        meta, _ = self.poser(self.a, "Explique les suites.")
        self.poser(self.b, "Et pour n = 3 ?")
        self.poser(self.a, "Et pour n = 3 ?", conversation_id=meta["conversation_id"])  # dépend du contexte
        self.assertEqual(mock_api.call_count, 3)

    @patch("aiapp.views.AIService.stream_chat_response", side_effect=flux_erreur)
    def test_erreur_non_mise_en_cache_et_remboursee(self, mock_api):
        self.poser(self.a, "Qu'est-ce qu'une fonction affine ?")
        self.assertEqual(ReponseEnCache.objects.count(), 0)
        self.assertEqual(self.credits(self.a), 200)

    @patch("aiapp.views.AIService.stream_chat_response", side_effect=faux_flux)
    def test_reponse_desactivee_par_l_admin(self, mock_api):
        self.poser(self.a, "Qu'est-ce qu'une fonction affine ?")
        ReponseEnCache.objects.update(actif=False)
        self.poser(self.b, "Qu'est-ce qu'une fonction affine ?")
        self.assertEqual(mock_api.call_count, 2)
