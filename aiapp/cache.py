"""Réutilisation des réponses de l'IA pour les questions déjà posées."""
import hashlib
import re
import unicodedata

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from .models import ReponseEnCache


def normaliser_question(texte):
    texte = unicodedata.normalize("NFKD", texte or "")
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    texte = re.sub(r"\s+", " ", texte).strip()
    texte = re.sub(r"\s+([?!.,;:])", r"\1", texte)   # « ? » collé ou non
    return texte.rstrip(" ?!.")


def cle_cache(modele, question):
    base = f"{modele}\n{normaliser_question(question)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def peut_utiliser_cache(question, a_un_fichier, a_un_historique):
    return bool(normaliser_question(question)) and not a_un_fichier and not a_un_historique


def chercher(modele, question):
    """Retourne la réponse en cache (et compte la réutilisation) ou None."""
    entree = ReponseEnCache.objects.filter(cle=cle_cache(modele, question), actif=True).first()
    if entree is None:
        return None
    ReponseEnCache.objects.filter(pk=entree.pk).update(
        utilisations=F("utilisations") + 1, derniere_utilisation=timezone.now()
    )
    return entree.reponse


def enregistrer(modele, question, reponse):
    """Mémorise une réponse réussie (jamais un message d'erreur)."""
    if not reponse or "[Erreur" in reponse:
        return
    cle = cle_cache(modele, question)
    try:
        ReponseEnCache.objects.update_or_create(
            cle=cle,
            defaults={
                "modele": modele,
                "question": question[:8000],
                "question_normalisee": normaliser_question(question)[:8000],
                "reponse": reponse,
                "actif": True,
            },
        )
    except IntegrityError:
        pass  # enregistrée au même instant par une autre requête
