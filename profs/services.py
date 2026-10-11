import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from authapp.models import UserRegistration

from .models import AbonnementProf, DemandeRetrait, MouvementProf, ProfilProfesseur

DUREE_ABONNEMENT = datetime.timedelta(days=30)


class OperationRefusee(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def commission():
    return getattr(settings, "PROF_COMMISSION_PLATEFORME", 30)


def repartition(montant):
    part_plateforme = round(montant * commission() / 100)
    return montant - part_plateforme, part_plateforme


def abonnement_actif(user, profil):
    if not user.is_authenticated:
        return None
    return AbonnementProf.objects.filter(eleve=user, professeur=profil, fin__gt=timezone.now()).order_by("-fin").first()


def a_acces(user, cours):
    if not user.is_authenticated:
        return False
    if user.is_staff or cours.professeur.user_id == user.pk:
        return True
    return abonnement_actif(user, cours.professeur) is not None


def abonner(eleve, profil):
    """Débite le solde de l'élève, ouvre 30 jours d'accès et crédite le professeur (70 %)."""
    if not profil.est_verifie:
        raise OperationRefusee("Ce professeur n'accepte pas encore d'abonnements.")
    if profil.user_id == eleve.pk:
        raise OperationRefusee("Tu ne peux pas t'abonner à ta propre chaîne.")
    prix = profil.prix_mensuel
    with transaction.atomic():
        compte = UserRegistration.objects.select_for_update().get(pk=eleve.pk)
        if compte.somme < prix:
            raise OperationRefusee(f"Solde insuffisant : l'abonnement coûte {prix} F et ton solde est de {compte.somme} F.")
        compte.somme -= prix
        compte.save(update_fields=["somme"])
        maintenant = timezone.now()
        en_cours = abonnement_actif(compte, profil)
        debut = en_cours.fin if en_cours else maintenant
        part_prof, part_plateforme = repartition(prix)
        abonnement = AbonnementProf.objects.create(
            eleve=compte, professeur=profil, debut=debut, fin=debut + DUREE_ABONNEMENT,
            montant=prix, part_professeur=part_prof, part_plateforme=part_plateforme,
        )
        delai = datetime.timedelta(days=getattr(settings, "PROF_DELAI_DISPONIBILITE_JOURS", 7))
        MouvementProf.objects.create(
            professeur=profil, type=MouvementProf.Type.VENTE, montant=part_prof, abonnement=abonnement,
            disponible_le=maintenant + delai,
            libelle=f"Abonnement de {compte.first_name or 'un élève'} ({prix} F, part professeur {100 - commission()} %)",
        )
    eleve.somme = compte.somme
    return abonnement


def demander_retrait(profil, montant):
    minimum = getattr(settings, "PROF_RETRAIT_MINIMUM", 5000)
    if not profil.est_verifie:
        raise OperationRefusee("Les retraits sont ouverts une fois ton identité vérifiée.")
    if montant < minimum:
        raise OperationRefusee(f"Le retrait minimum est de {minimum} F.")
    with transaction.atomic():
        profil = ProfilProfesseur.objects.select_for_update().get(pk=profil.pk)
        if DemandeRetrait.objects.filter(professeur=profil, statut=DemandeRetrait.Statut.EN_ATTENTE).exists():
            raise OperationRefusee("Tu as déjà une demande de retrait en cours de traitement.")
        disponible = profil.solde_disponible()
        if montant > disponible:
            raise OperationRefusee(f"Ton solde disponible est de {disponible} F.")
        retrait = DemandeRetrait.objects.create(
            professeur=profil, montant=montant, operateur=profil.operateur, numero=profil.numero_retrait,
        )
        MouvementProf.objects.create(
            professeur=profil, type=MouvementProf.Type.RETRAIT, montant=-montant, retrait=retrait,
            disponible_le=timezone.now(), libelle=f"Retrait vers {profil.get_operateur_display()} {profil.numero_retrait}",
        )
    return retrait


def marquer_retrait_paye(retrait, reference):
    if not reference:
        raise OperationRefusee("Indique la référence de la transaction Mobile Money.")
    DemandeRetrait.objects.filter(pk=retrait.pk, statut=DemandeRetrait.Statut.EN_ATTENTE).update(
        statut=DemandeRetrait.Statut.PAYEE, reference_paiement=reference[:100], date_traitement=timezone.now(),
    )


def refuser_retrait(retrait, motif=""):
    with transaction.atomic():
        retrait = DemandeRetrait.objects.select_for_update().get(pk=retrait.pk)
        if retrait.statut != DemandeRetrait.Statut.EN_ATTENTE:
            return
        retrait.statut = DemandeRetrait.Statut.REFUSEE
        retrait.motif_refus = motif[:300]
        retrait.date_traitement = timezone.now()
        retrait.save(update_fields=["statut", "motif_refus", "date_traitement"])
        MouvementProf.objects.create(
            professeur=retrait.professeur, type=MouvementProf.Type.REMBOURSEMENT_RETRAIT, montant=retrait.montant,
            retrait=retrait, disponible_le=timezone.now(), libelle=f"Retrait refusé : {motif[:150] or 'voir avec l’équipe'}",
        )
