from django.db import models
from django.contrib.auth.models import AbstractUser
from phonenumber_field.modelfields import PhoneNumberField
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.base_user import BaseUserManager
from multiselectfield import MultiSelectField

from programme.models import Niveaux


class UserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """
    def create_user(self, email, password, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self.create_user(email, password, **extra_fields)
class UserRegistration(AbstractUser):
    email = models.EmailField(_('Email address'), unique=True)
    numero_telephone = PhoneNumberField()
    ville = models.CharField(max_length=100)
    classe = models.ManyToManyField(Niveaux, related_name='users', blank=True)
    somme = models.IntegerField(_('Frais d\'utilisation'), default=0)
    # AI Credits System
    daily_credits = models.IntegerField(default=100, verbose_name="Crédits journaliers")
    wallet_credits = models.IntegerField(default=0, verbose_name="Portefeuille crédits")
    last_daily_reset = models.DateField(auto_now_add=True, null=True, blank=True)   
    is_first_login = models.BooleanField(default=True)
    bonus_bienvenue_recu = models.BooleanField(default=False, editable=False)
    avater = models.ImageField(upload_to='profiles', blank=True, null=True) 
    username = None

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return f"{self.first_name} { self.last_name}"


class SessionAppareil(models.Model):
    """Appareils connectés à un compte (limite le partage d'identifiants)."""
    utilisateur = models.ForeignKey(UserRegistration, on_delete=models.CASCADE, related_name="appareils")
    session_key = models.CharField(max_length=40, unique=True)
    appareil = models.CharField(max_length=300, blank=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "appareil connecté"
        verbose_name_plural = "appareils connectés"
