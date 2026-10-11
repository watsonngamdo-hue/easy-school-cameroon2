import os
import uuid
from django.db import models
from django.template.defaultfilters import slugify
from ckeditor.fields import RichTextField
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.utils.deconstruct import deconstructible

from Elearning.storage import private_storage


UserRegistration = settings.AUTH_USER_MODEL

# information about the subjectfrom django.template.defaultfilters import slugify
from django.urls import reverse

@deconstructible
class PathRename(object):

    def __init__(self, prefix):
        self.path = prefix

    def __call__(self, instance, filename):
        ext = filename.split('.')[-1]
        # get filename
        if instance.pk:
            identifier = instance.pk
            filename = '{}.{}.{}'.format(self.path, identifier, ext)
        else:
            # set filename as random string
            random_id = "rid_%s" % (uuid.uuid4().hex,)
            filename = '{}.{}.{}'.format(self.path, random_id, ext)
            # return the whole path to the file
        return os.path.join(self.path, filename)

class Niveaux(models.Model):
    niveau = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(null=True, max_length=5000, blank=True, unique=True)
    description = models.TextField(blank=True, null=True)
    ordre = models.PositiveSmallIntegerField(default=99, help_text="1 = 6e … 7 = Terminale")

    class Meta:
        verbose_name = ('Niveau')
        verbose_name_plural = ('Niveaux')
        ordering = ['ordre', 'niveau']


    def __str__(self):
        return self.libelle

    @property
    def libelle(self):
        """Nom affiché avec accents : « Première » au lieu de « PREMIERE »."""
        from .programme_officiel import LIBELLES
        return LIBELLES.get(self.ordre, (self.niveau.capitalize(), ""))[0]

    @property
    def abrege(self):
        from .programme_officiel import LIBELLES
        return LIBELLES.get(self.ordre, ("", ""))[1]

    @property
    def repere(self):
        from .programme_officiel import REPERES
        return REPERES.get(self.ordre, "")

    def save(self, *args, **kwargs):
        from .programme_officiel import ordre_classe
        self.slug = slugify(self.niveau)
        self.niveau = self.niveau.upper()
        if self.ordre == 99:
            self.ordre = ordre_classe(self.niveau)
        super().save(*args, **kwargs)  


class Matiere(models.Model):
    matiere_id = models.CharField(unique=True, max_length=40)
    nom = models.CharField(max_length=5000, unique=True)
    slug = models.SlugField(null=True, max_length=5000, blank=True, unique=True)
    niveau = models.ForeignKey(Niveaux, on_delete=models.CASCADE, related_name='matieres')
    image = models.ImageField(upload_to=PathRename('matieres'), validators=[FileExtensionValidator(['png', 'jpeg', 'jpg'])], blank=True)
    description = RichTextField()


    def __str__(self):
        return f"{self.nom} pour la {self.niveau}"

    @property
    def nom_court(self):
        """« Mathématiques (TERMINALE) » → « Mathématiques »."""
        import re
        return re.sub(r"\s*\(.*?\)\s*$", "", self.nom)


    def save(self, *args, **kwargs):
        self.slug = slugify(f"{self.nom}/{self.niveau}")  
        super().save(*args, **kwargs)  

        class Meta:
            verbose_name = ('Matiere')
            verbose_name_plural = ('Matieres')
class Lesson(models.Model):
    lesson_id = models.CharField(unique=True, max_length=40)
    niveau = models.ForeignKey(Niveaux, on_delete=models.CASCADE)
    creer_par = models.ForeignKey(UserRegistration, on_delete=models.CASCADE)
    matiere = models.ForeignKey(Matiere, on_delete=models.CASCADE, related_name='lessons')
    nom = models.CharField(max_length=5000, unique=True) 
    description = RichTextField(blank=True, null=True) 
    date_ajout = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(blank=True, max_length=5000, null=True, unique=True)
    position = models.PositiveSmallIntegerField(verbose_name='chapitre no')  
    url = models.URLField(blank=True, null=True)
    fpe = models.FileField(upload_to=PathRename("FPE"), storage=private_storage, validators=[FileExtensionValidator(['pdf', 'txt', 'docx', 'zip', 'rar', 'xlsx'])], null=True, blank=True, verbose_name="fiche de presentation")
    pdf = models.FileField(upload_to=PathRename("PDF"), storage=private_storage, validators=[FileExtensionValidator(['pdf', 'txt', 'docx', 'zip', 'rar', 'xlsx'])], null=True, blank=True, verbose_name="lecon en pdf")
    exercice = models.FileField(upload_to=PathRename("Exercice"), storage=private_storage, validators=[FileExtensionValidator(['pdf', 'txt', 'docx', 'zip', 'rar', 'xlsx'])], null=True, blank=True, verbose_name="exercice en pdf")

    class Meta:
        ordering = ['-position']
        verbose_name = ('Leçon')
        verbose_name_plural = ('Leçons')


    def __str__(self):
        return f"{self.nom} de {self.matiere}"


    def save(self, *args, **kwargs):
        self.slug = slugify(f"{self.niveau}/{self.nom}/{self.nom}")  
        super().save(*args, **kwargs)  

    def get_absolute_url(self):
        return reverse("programme:lessonlist", kwargs={"slug": self.matiere.slug, "niveau": self.niveau.slug})


class Commentaire(models.Model):
    nom_lesson = models.ForeignKey(Lesson, null=True, on_delete=models.CASCADE, related_name='comments')
    nom_comm = models.CharField(max_length=100, blank=True)
    # reponse = models.ForeignKey('Commentaire', null=True, blank=True, on_delete=models.CASCADE, related_name='reponses')
    auteur = models.ForeignKey(UserRegistration, on_delete=models.CASCADE)
    corps = models.TextField()
    date_added = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.nom_comm = slugify(f"commente par  {str(self.auteur)}  {str(self.date_added)}")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom_comm

    class Meta:
        ordering = ['-date_added']        


class Reponse(models.Model):
    nom_comm = models.ForeignKey(Commentaire, on_delete=models.DO_NOTHING, related_name='reponses')      
    corps = models.TextField()
    auteur = models.ForeignKey(UserRegistration, on_delete=models.CASCADE)
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"reponse a {str(self.nom_comm.nom_comm)}"

from datetime import date


class Payment(models.Model):
    user = models.ForeignKey(UserRegistration, on_delete=models.CASCADE)
    niveau = models.ForeignKey(Niveaux, on_delete=models.CASCADE)
    montant = models.PositiveBigIntegerField()
    date_pay = models.DateField()
    date_expired = models.DateField()

    class Meta:
        ordering = ['-date_pay']

    def __str__(self):
        return f"{self.user}-{self.montant}"

    @property
    def is_past_due(self):
        return date.today() > self.date_expired    

class PaymentIssue(models.Model):
    numero = models.CharField(max_length=100)
    description = models.TextField()
    reference = models.CharField(max_length=100)
    date_added = models.DateTimeField(auto_now_add=True, null=True)
    user = models.ForeignKey(UserRegistration, on_delete=models.CASCADE)
    date = models.CharField(max_length=100)
    montant = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return self.numero

        

class Newsletter(models.Model):
    email = models.EmailField()
    creer_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

class Contact(models.Model):
    nom = models.CharField(max_length=150)
    email = models.EmailField()
    sujet = models.CharField(max_length=300)
    message = models.TextField()
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} le {self.date}"
class Ecole(models.Model):
    nom = models.CharField(max_length=200, unique=True)
    logo = models.ImageField(upload_to=PathRename('ecoles'), validators=[FileExtensionValidator(['png', 'jpeg', 'jpg'])], blank=True, null=True)
    adresse = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        verbose_name = 'École'
        verbose_name_plural = 'Écoles'

    def __str__(self):
        return self.nom

class AncienEpreuve(models.Model):
    titre = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    fichier = models.FileField(upload_to=PathRename('epreuves'), storage=private_storage, validators=[FileExtensionValidator(['pdf'])], verbose_name="Épreuve en PDF")
    niveau = models.ForeignKey(Niveaux, on_delete=models.CASCADE, related_name='anciennes_epreuves')
    ecole = models.ForeignKey(Ecole, on_delete=models.CASCADE, related_name='anciennes_epreuves')
    matiere = models.ForeignKey(Matiere, on_delete=models.SET_NULL, null=True, blank=True, related_name='anciennes_epreuves', verbose_name="Matière")
    annee = models.IntegerField(verbose_name="Année", blank=True, null=True)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Ancienne Épreuve'
        verbose_name_plural = 'Anciennes Épreuves'
        ordering = ['-date_ajout']

    def __str__(self):
        return f"{self.titre} - {self.ecole} ({self.annee})"

class ReseauxSociaux(models.Model):
    facebook = models.URLField(max_length=200, blank=True, null=True, verbose_name="Facebook")
    tiktok = models.URLField(max_length=200, blank=True, null=True, verbose_name="TikTok")
    instagram = models.URLField(max_length=200, blank=True, null=True, verbose_name="Instagram")
    twitter = models.URLField(max_length=200, blank=True, null=True, verbose_name="Twitter")
    youtube = models.URLField(max_length=200, blank=True, null=True, verbose_name="YouTube")
    linkedin = models.URLField(max_length=200, blank=True, null=True, verbose_name="LinkedIn")

    class Meta:
        verbose_name = "Réseaux Sociaux"
        verbose_name_plural = "Réseaux Sociaux"

    def __str__(self):
        return "Configuration des Réseaux Sociaux"

class PaymentSettings(models.Model):
    orange_number = models.CharField(max_length=20, default="+237 693 157 507")
    orange_name = models.CharField(max_length=100, default="Orange Money (Nom à vérifier lors du paiement)")
    mtn_number = models.CharField(max_length=20, default="+237 672 168 452")
    mtn_name = models.CharField(max_length=100, default="MTN Mobile Money")

    class Meta:
        verbose_name = "Paramètres de Paiement"
        verbose_name_plural = "Paramètres de Paiement"

    def __str__(self):
        return "Configuration des Paiements"


class AccesDocument(models.Model):
    """Journal de chaque ouverture d'un document payant (détection des partages anormaux)."""
    utilisateur = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name="acces_documents")
    type_document = models.CharField(max_length=30)
    objet_id = models.PositiveIntegerField()
    titre = models.CharField(max_length=300)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    appareil = models.CharField(max_length=300, blank=True)
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "accès à un document"
        verbose_name_plural = "accès aux documents"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.utilisateur} – {self.titre}"
