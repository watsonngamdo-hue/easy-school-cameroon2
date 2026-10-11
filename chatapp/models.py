from django.db import models
from ckeditor.fields import RichTextField
from programme.models import PathRename
from programme.models import Matiere, Niveaux, UserRegistration
from django.core.validators import FileExtensionValidator

# Create your models here.
class Forum(models.Model):
    message = RichTextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(UserRegistration, on_delete=models.CASCADE)
    niveau = models.ForeignKey(Niveaux, on_delete=models.CASCADE)
    matiere = models.ForeignKey(Matiere, on_delete=models.CASCADE)
    fichier = models.FileField(upload_to=PathRename('chatpdfs'), validators=[FileExtensionValidator(['pdf', 'txt', 'docx', 'zip', 'rar', 'xlsx'])], help_text="Ce champ vous permet d'entre des fichiers numeriques docx, pdf etc. Si vous voulez envoyer", null=True, blank=True)
    image = models.FileField(upload_to=PathRename('chatimages'), validators=[FileExtensionValidator(['png', 'jpeg', 'jpg'])], help_text="Ce champ vous permet d'entre des images png, jpeg etc. Si vous voulez envoyer", null=True, blank=True)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)
    
    def __str__(self):
        return str(self.user)


class ForumPrivate(models.Model):
    message = RichTextField()
    from_message = models.ManyToManyField(UserRegistration, related_name='form_messages')
    to_message = models.ManyToManyField(UserRegistration, related_name='to_messages')
    fichier = models.FileField(upload_to=PathRename('chatpdfs'), validators=[FileExtensionValidator(['pdf', 'txt', 'docx', 'zip', 'rar', 'xlsx'])], help_text="Ce champ vous permet d'entre des fichiers numeriques docx, pdf etc. Si vous voulez envoyer", null=True, blank=True)
    image = models.FileField(upload_to=PathRename('chatimages'), validators=[FileExtensionValidator(['png', 'jpeg', 'jpg'])], help_text="Ce champ vous permet d'entre des images png, jpeg etc. Si vous voulez envoyer", null=True, blank=True)
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)
    deleted = models.BooleanField(default=False)
    read_by = models.ManyToManyField(UserRegistration, related_name='read_private_messages', blank=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return str(self.from_message)