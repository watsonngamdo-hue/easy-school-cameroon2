import uuid

from django.conf import settings
from django.db import models

from programme.models import AncienEpreuve, Matiere, Niveaux


from Elearning.storage import private_storage  # noqa: E402  (réexporté pour les migrations)


def chemin_epreuve(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"epreuves/{instance.niveau_id}/{uuid.uuid4().hex}.{ext}"


class EpreuveSoumise(models.Model):
    class Type(models.TextChoices):
        SEQUENCE_1 = "seq1", "1re séquence"
        SEQUENCE_2 = "seq2", "2e séquence"
        SEQUENCE_3 = "seq3", "3e séquence"
        SEQUENCE_4 = "seq4", "4e séquence"
        SEQUENCE_5 = "seq5", "5e séquence"
        SEQUENCE_6 = "seq6", "6e séquence"
        TRIMESTRE_1 = "trim1", "Examen du 1er trimestre"
        TRIMESTRE_2 = "trim2", "Examen du 2e trimestre"
        TRIMESTRE_3 = "trim3", "Examen du 3e trimestre"
        EXAMEN_BLANC = "blanc", "Examen blanc"
        EXAMEN_OFFICIEL = "officiel", "Examen officiel (BEPC, Probatoire, BAC…)"
        DEVOIR = "devoir", "Devoir / interrogation"

    class Statut(models.TextChoices):
        RECUE = "recue", "Reçue"
        VALIDEE = "validee", "Validée"
        REJETEE = "rejetee", "Rejetée"

    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="epreuves_soumises")
    titre = models.CharField(max_length=200)
    niveau = models.ForeignKey(Niveaux, on_delete=models.PROTECT, related_name="epreuves_soumises")
    matiere = models.ForeignKey(Matiere, on_delete=models.PROTECT, related_name="epreuves_soumises")
    etablissement = models.CharField("établissement", max_length=200)
    type_evaluation = models.CharField("type d'évaluation", max_length=10, choices=Type.choices)
    annee_scolaire = models.CharField("année scolaire", max_length=9, help_text="Format 2025-2026")

    fichier = models.FileField(upload_to=chemin_epreuve, storage=private_storage, max_length=255)
    nom_original = models.CharField(max_length=255)
    type_fichier = models.CharField(max_length=10)
    taille = models.PositiveIntegerField()
    nombre_pages = models.PositiveSmallIntegerField(default=1)

    # --- Empreintes servant à reconnaître une épreuve déjà reçue ---
    # SHA-256 du fichier exact : bloque le renvoi du même fichier.
    empreinte_fichier = models.CharField(max_length=64, unique=True, editable=False)
    # SHA-256 du texte normalisé (PDF) : bloque une copie renommée ou ré-enregistrée.
    empreinte_texte = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    # Signature visuelle (vignette 32×32 du contenu) : bloque une image ou un scan
    # recompressé, redimensionné ou recadré.
    empreinte_visuelle = models.TextField(null=True, blank=True, editable=False)
    # Clé « établissement + classe + matière + évaluation + année » : bloque une
    # autre photo ou un autre scan de la même épreuve.
    cle_epreuve = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)

    # Copie publiée dans la banque « Anciennes épreuves » (visible par les abonnés de la classe).
    publication = models.OneToOneField(
        AncienEpreuve, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="depot",
    )
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.RECUE)
    recompense = models.PositiveIntegerField(default=0, editable=False)
    motif_rejet = models.CharField(max_length=300, blank=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True, editable=False)
    date_envoi = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "épreuve soumise"
        verbose_name_plural = "épreuves soumises"
        ordering = ["-date_envoi"]
        indexes = [models.Index(fields=["eleve", "date_envoi"])]

    def __str__(self):
        return f"{self.titre} – {self.etablissement} ({self.annee_scolaire})"


class MouvementSolde(models.Model):
    """Journal de chaque crédit/débit du solde lié au dépôt d'épreuves (traçabilité)."""

    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mouvements_depot")
    epreuve = models.ForeignKey(EpreuveSoumise, on_delete=models.PROTECT, related_name="mouvements")
    montant = models.IntegerField()
    motif = models.CharField(max_length=200)
    solde_apres = models.IntegerField()
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mouvement de solde"
        verbose_name_plural = "mouvements de solde"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.montant:+d} F – {self.eleve}"
