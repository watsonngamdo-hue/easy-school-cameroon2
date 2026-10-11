from django.db import models
from django.conf import settings
import uuid

class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=200, default="New Conversation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.user.email})"

class AIMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_messages')
    user_message = models.TextField()
    ai_response = models.TextField(blank=True, null=True)
    mode = models.CharField(max_length=10, default='chat', choices=[('chat', 'Chat'), ('image', 'Image')])
    image = models.ImageField(upload_to='ai_images/', blank=True, null=True)
    file = models.FileField(upload_to='ai_files/', blank=True, null=True)
    file_type = models.CharField(max_length=100, blank=True, null=True)  # Store content type
    modele = models.CharField(max_length=100, blank=True, default="", verbose_name="Modèle d'IA")
    depuis_cache = models.BooleanField(default=False, verbose_name="Réponse réutilisée (sans appel API)")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Chat by {self.user.email} at {self.created_at}"

class AISettings(models.Model):
    default_daily_credits = models.IntegerField(default=100, verbose_name="Crédits journaliers par défaut")
    file_upload_cost = models.IntegerField(default=20, verbose_name="Coût par upload de fichier")
    
    openai_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="Clé API OpenAI")
    gemini_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="Clé API Gemini")
    
    class Meta:
        verbose_name = "Paramètres IA"
        verbose_name_plural = "Paramètres IA"


    def __str__(self):
        return "Paramètres IA Globaux"

class AIModel(models.Model):
    PROVIDER_CHOICES = [
        ('openai', 'OpenAI'),
        ('deepseek', 'DeepSeek'),
        ('gemini', 'Google Gemini'),
    ]
    TYPE_CHOICES = [
        ('chat', 'Chat'),
        ('image', 'Image Generation'),
    ]

    name = models.CharField(max_length=100, verbose_name="Nom affiché")
    api_value = models.CharField(max_length=100, verbose_name="Valeur API (ID Modèle)")
    model_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='chat')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='openai')
    cost = models.IntegerField(default=10, verbose_name="Coût en crédits")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    
    def __str__(self):
        return f"{self.name} ({self.get_provider_display()}) - {self.cost} Cr"

class Pack(models.Model):
    name = models.CharField(max_length=100)
    price = models.IntegerField()
    credit = models.IntegerField()
    icon = models.CharField(max_length=50, default='bolt')
    popular = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.credit} Credits - {self.price} FCFA)"


class ReponseEnCache(models.Model):
    """Réponse de l'IA réutilisable quand la même question est reposée.

    La clé combine le modèle choisi et la question normalisée (minuscules, sans
    accents ni espaces superflus). Seules les questions posées sans fichier et
    en début de conversation sont mises en cache : leur réponse ne dépend
    d'aucun contexte et peut donc servir à tous les élèves.
    """
    cle = models.CharField(max_length=64, unique=True)
    modele = models.CharField(max_length=100)
    question = models.TextField()
    question_normalisee = models.TextField()
    reponse = models.TextField()
    utilisations = models.PositiveIntegerField(default=0, verbose_name="Réutilisations (appels API évités)")
    actif = models.BooleanField(default=True, help_text="Décocher pour forcer une nouvelle réponse de l'IA.")
    date_creation = models.DateTimeField(auto_now_add=True)
    derniere_utilisation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "réponse en cache"
        verbose_name_plural = "réponses en cache"
        ordering = ["-utilisations", "-date_creation"]

    def __str__(self):
        return self.question[:80]
