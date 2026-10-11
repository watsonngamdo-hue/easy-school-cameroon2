"""Espace professeurs : chaînes de cours vidéo/PDF vendues par abonnement mensuel."""
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.text import slugify

from Elearning.storage import private_storage
from programme.models import Matiere, Niveaux

User = settings.AUTH_USER_MODEL


def chemin_piece(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"profs/pieces/{instance.profil_id}/{uuid.uuid4().hex}.{ext}"


def chemin_video(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    return f"profs/videos/{uuid.uuid4().hex}.{ext}"


def chemin_pdf(instance, filename):
    return f"profs/pdf/{uuid.uuid4().hex}.pdf"


def chemin_image(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"profs/images/{uuid.uuid4().hex}.{ext}"


class ProfilProfesseur(models.Model):
    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Dossier incomplet"
        EN_ATTENTE = "attente", "En cours de vérification"
        VERIFIE = "verifie", "Identité vérifiée"
        REFUSE = "refuse", "Refusé"
        SUSPENDU = "suspendu", "Suspendu"

    class Operateur(models.TextChoices):
        ORANGE = "orange", "Orange Money"
        MTN = "mtn", "MTN Mobile Money"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profil_prof")
    nom_public = models.CharField("nom affiché", max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    bio = models.TextField("présentation", max_length=2000)
    etablissement = models.CharField("établissement où tu enseignes", max_length=200, blank=True)
    niveaux = models.ManyToManyField(Niveaux, verbose_name="classes", related_name="professeurs")
    matieres_texte = models.CharField("matières enseignées", max_length=200)
    photo = models.ImageField(upload_to=chemin_image, blank=True, null=True)
    prix_mensuel = models.PositiveIntegerField(
        "prix de l'abonnement mensuel (FCFA)", default=1000,
        validators=[MinValueValidator(500), MaxValueValidator(20000)],
    )
    operateur = models.CharField("opérateur pour les retraits", max_length=10, choices=Operateur.choices)
    numero_retrait = models.CharField("numéro Mobile Money pour les retraits", max_length=20)

    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    motif_decision = models.CharField(max_length=300, blank=True)
    date_demande = models.DateTimeField(null=True, blank=True)
    date_decision = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "professeur"
        verbose_name_plural = "professeurs"
        ordering = ["nom_public"]

    def __str__(self):
        return self.nom_public

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nom_public)[:120] or "prof"
            slug, n = base, 2
            while ProfilProfesseur.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def est_verifie(self):
        return self.statut == self.Statut.VERIFIE

    def abonnes_actifs(self):
        return self.abonnements.filter(fin__gt=timezone.now()).values("eleve").distinct().count()

    def solde_disponible(self):
        return self.mouvements.filter(disponible_le__lte=timezone.now()).aggregate(t=Sum("montant"))["t"] or 0

    def solde_en_attente(self):
        return self.mouvements.filter(disponible_le__gt=timezone.now()).aggregate(t=Sum("montant"))["t"] or 0

    def gains_totaux(self):
        return self.mouvements.filter(type=MouvementProf.Type.VENTE).aggregate(t=Sum("montant"))["t"] or 0


class PieceIdentite(models.Model):
    class Type(models.TextChoices):
        CNI_RECTO = "cni_recto", "CNI — recto"
        CNI_VERSO = "cni_verso", "CNI — verso"
        SELFIE = "selfie", "Selfie en tenant la CNI"
        JUSTIFICATIF = "justificatif", "Diplôme ou attestation de l'établissement"

    profil = models.ForeignKey(ProfilProfesseur, on_delete=models.CASCADE, related_name="pieces")
    type = models.CharField(max_length=20, choices=Type.choices)
    fichier = models.FileField(upload_to=chemin_piece, storage=private_storage)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pièce d'identité"
        verbose_name_plural = "pièces d'identité"
        unique_together = [("profil", "type")]


class CoursProf(models.Model):
    professeur = models.ForeignKey(ProfilProfesseur, on_delete=models.CASCADE, related_name="cours")
    titre = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(max_length=3000)
    niveau = models.ForeignKey(Niveaux, on_delete=models.PROTECT, related_name="cours_profs")
    matiere = models.ForeignKey(Matiere, on_delete=models.SET_NULL, null=True, blank=True, related_name="cours_profs")
    miniature = models.ImageField(upload_to=chemin_image, blank=True, null=True)
    publie = models.BooleanField(default=False)
    bloque_par_admin = models.BooleanField(default=False, help_text="Retire le cours du site (contenu signalé).")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_maj = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cours de professeur"
        verbose_name_plural = "cours de professeurs"
        ordering = ["-date_creation"]

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.titre)[:150] or "cours"
            self.slug = f"{base}-{uuid.uuid4().hex[:6]}"
        super().save(*args, **kwargs)

    @property
    def visible(self):
        return self.publie and not self.bloque_par_admin and self.professeur.est_verifie


class LeconProf(models.Model):
    class Type(models.TextChoices):
        VIDEO = "video", "Vidéo"
        PDF = "pdf", "Document PDF"

    cours = models.ForeignKey(CoursProf, on_delete=models.CASCADE, related_name="lecons")
    titre = models.CharField(max_length=160)
    ordre = models.PositiveSmallIntegerField(default=1)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.VIDEO)
    video = models.FileField(upload_to=chemin_video, storage=private_storage, blank=True, null=True)
    pdf = models.FileField(upload_to=chemin_pdf, storage=private_storage, blank=True, null=True)
    duree_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    apercu_gratuit = models.BooleanField("aperçu gratuit", default=False,
                                         help_text="Visible sans abonnement, pour donner envie de s'abonner.")
    vues = models.PositiveIntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "leçon de professeur"
        verbose_name_plural = "leçons de professeurs"
        ordering = ["ordre", "pk"]

    def __str__(self):
        return self.titre


class AbonnementProf(models.Model):
    eleve = models.ForeignKey(User, on_delete=models.PROTECT, related_name="abonnements_profs")
    professeur = models.ForeignKey(ProfilProfesseur, on_delete=models.PROTECT, related_name="abonnements")
    debut = models.DateTimeField()
    fin = models.DateTimeField(db_index=True)
    montant = models.PositiveIntegerField()
    part_professeur = models.PositiveIntegerField()
    part_plateforme = models.PositiveIntegerField()
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "abonnement à un professeur"
        verbose_name_plural = "abonnements aux professeurs"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.eleve} → {self.professeur} ({self.montant} F)"

    @property
    def actif(self):
        return self.fin > timezone.now()


class DemandeRetrait(models.Model):
    class Statut(models.TextChoices):
        EN_ATTENTE = "attente", "En attente"
        PAYEE = "payee", "Payée"
        REFUSEE = "refusee", "Refusée"

    professeur = models.ForeignKey(ProfilProfesseur, on_delete=models.PROTECT, related_name="retraits")
    montant = models.PositiveIntegerField()
    operateur = models.CharField(max_length=10, choices=ProfilProfesseur.Operateur.choices)
    numero = models.CharField(max_length=20)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_ATTENTE)
    reference_paiement = models.CharField("référence de la transaction Mobile Money", max_length=100, blank=True)
    motif_refus = models.CharField(max_length=300, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "demande de retrait"
        verbose_name_plural = "demandes de retrait"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.professeur} – {self.montant} F ({self.get_statut_display()})"


class MouvementProf(models.Model):
    """Journal des gains et retraits : le solde du professeur se calcule à partir de ce journal."""

    class Type(models.TextChoices):
        VENTE = "vente", "Abonnement vendu"
        RETRAIT = "retrait", "Retrait"
        REMBOURSEMENT_RETRAIT = "annul_retrait", "Retrait refusé (recrédité)"
        AJUSTEMENT = "ajustement", "Ajustement"

    professeur = models.ForeignKey(ProfilProfesseur, on_delete=models.PROTECT, related_name="mouvements")
    type = models.CharField(max_length=15, choices=Type.choices)
    montant = models.IntegerField()
    abonnement = models.ForeignKey(AbonnementProf, on_delete=models.PROTECT, null=True, blank=True)
    retrait = models.ForeignKey(DemandeRetrait, on_delete=models.PROTECT, null=True, blank=True)
    disponible_le = models.DateTimeField(db_index=True)
    libelle = models.CharField(max_length=200)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mouvement du solde professeur"
        verbose_name_plural = "mouvements des soldes professeurs"
        ordering = ["-date"]
