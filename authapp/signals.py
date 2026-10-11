from allauth.account.signals import email_confirmed
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.contrib import messages
from django.db import transaction
from django.dispatch import receiver

from .models import SessionAppareil, UserRegistration

BONUS_FCFA = 1000
BONUS_CREDITS_IA = 500


@receiver(email_confirmed)
def award_onboarding_bonus(request, email_address, **kwargs):
    """Offre le bonus de bienvenue UNE SEULE FOIS par compte.

    Avant : le bonus dépendait de is_first_login, si bien qu'un utilisateur
    pouvait le recevoir plusieurs fois en ajoutant puis confirmant d'autres
    adresses e-mail avant de terminer l'accueil.
    """
    with transaction.atomic():
        user = UserRegistration.objects.select_for_update().get(pk=email_address.user_id)
        if user.bonus_bienvenue_recu:
            return
        user.somme += BONUS_FCFA
        user.wallet_credits += BONUS_CREDITS_IA
        user.bonus_bienvenue_recu = True
        user.save(update_fields=["somme", "wallet_credits", "bonus_bienvenue_recu"])
    if request is not None:
        messages.success(
            request,
            f"Félicitations ! Vous avez reçu {BONUS_FCFA} FCFA et {BONUS_CREDITS_IA} crédits IA pour commencer.",
            fail_silently=True,
        )


@receiver(user_logged_in)
def limiter_appareils(sender, request, user, **kwargs):
    """Un compte ne reste connecté que sur MAX_APPAREILS_PAR_COMPTE appareils :
    la connexion d'un nouvel appareil déconnecte le plus ancien. Partager ses
    identifiants avec des camarades devient donc pénible."""
    if request is None or not hasattr(request, "session"):
        return
    if request.session.session_key is None:
        request.session.save()
    cle = request.session.session_key
    SessionAppareil.objects.update_or_create(
        session_key=cle,
        defaults={
            "utilisateur": user,
            "appareil": request.META.get("HTTP_USER_AGENT", "")[:300],
            "adresse_ip": (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                           or request.META.get("REMOTE_ADDR") or None),
        },
    )
    maximum = getattr(settings, "MAX_APPAREILS_PAR_COMPTE", 2)
    if user.is_staff or maximum <= 0:
        return
    anciens = list(SessionAppareil.objects.filter(utilisateur=user).order_by("-date")[maximum:])
    if anciens:
        cles = [a.session_key for a in anciens]
        Session.objects.filter(session_key__in=cles).delete()
        SessionAppareil.objects.filter(session_key__in=cles).delete()
        messages.info(request, f"Ton compte peut être connecté sur {maximum} appareils au maximum : "
                               "le plus ancien a été déconnecté.", fail_silently=True)
