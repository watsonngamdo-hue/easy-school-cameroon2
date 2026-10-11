from django import forms
from django.db.models import Case, IntegerField, Value, When
from django.db.models.functions import Lower

from Elearning.sanitize import clean_html
from Elearning.validators import validate_upload

from .models import Forum, ForumPrivate

DOC_EXT = {".pdf", ".txt", ".docx", ".zip", ".rar", ".xlsx"}
IMG_EXT = {".png", ".jpg", ".jpeg"}
MAX_DESTINATAIRES = 20


class _UploadMixin:
    def clean_message(self):
        message = clean_html(self.cleaned_data.get("message") or "")
        if len(message) > 20000:
            raise forms.ValidationError("Message trop long.")
        return message

    def clean_fichier(self):
        return validate_upload(self.cleaned_data.get("fichier"), DOC_EXT, max_mb=10)

    def clean_image(self):
        return validate_upload(self.cleaned_data.get("image"), IMG_EXT, max_mb=5)


class ForumForm(_UploadMixin, forms.ModelForm):
    class Meta:
        model = Forum
        fields = ["message", "fichier", "image", "reply_to"]
        labels = {"message": ""}
        widgets = {
            "fichier": forms.FileInput(attrs={"class": "form-control col-md-6"}),
            "image": forms.FileInput(attrs={"class": "form-control col-md-6"}),
            "reply_to": forms.HiddenInput(),
        }

    def __init__(self, *args, niveau=None, matiere=None, **kwargs):
        super().__init__(*args, **kwargs)
        # On ne peut répondre qu'à un message du même forum.
        qs = Forum.objects.filter(deleted=False)
        if niveau is not None and matiere is not None:
            qs = qs.filter(niveau=niveau, matiere=matiere)
        self.fields["reply_to"].queryset = qs


class AdminStyledSelectMultiple(forms.SelectMultiple):
    """Ajoute data-is-admin aux options correspondant à un membre de l'équipe."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        user = getattr(value, "instance", None)
        if user and (getattr(user, "is_superuser", False) or getattr(user, "is_staff", False)):
            option["attrs"]["data-is-admin"] = "true"
        return option


class ForumFormPrivate(_UploadMixin, forms.ModelForm):
    class Meta:
        model = ForumPrivate
        fields = ["message", "to_message", "fichier", "image", "reply_to"]
        labels = {
            "message": "",
            "to_message": "Sélectionner le(s) destinataire(s)",
            "image": "Choisir une image",
            "fichier": "Choisir un fichier",
        }
        widgets = {
            "to_message": AdminStyledSelectMultiple(attrs={"class": "form-control"}),
            "fichier": forms.FileInput(attrs={"class": "form-control col-md-6 custom-file-input"}),
            "image": forms.FileInput(attrs={"class": "form-control col-md-6 custom-file-input"}),
            "reply_to": forms.HiddenInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        qs = self.fields["to_message"].queryset.filter(is_active=True)
        if user is not None:
            qs = qs.exclude(pk=user.pk)
        qs = qs.annotate(
            is_admin_order=Case(
                When(is_superuser=True, then=Value(0)),
                When(is_staff=True, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            lower_first_name=Lower("first_name"),
            lower_last_name=Lower("last_name"),
        ).order_by("is_admin_order", "lower_first_name", "lower_last_name")
        self.fields["to_message"].queryset = qs
        self.fields["to_message"].label_from_instance = lambda obj: f"{obj.first_name} {obj.last_name}"

        # On ne peut répondre qu'à une conversation à laquelle on participe
        # (sinon le texte cité d'un message privé d'autrui serait divulgué).
        reply_qs = ForumPrivate.objects.none()
        if user is not None:
            reply_qs = ForumPrivate.objects.filter(deleted=False).filter(
                pk__in=ForumPrivate.objects.filter(from_message=user).values("pk")
            ) | ForumPrivate.objects.filter(deleted=False).filter(
                pk__in=ForumPrivate.objects.filter(to_message=user).values("pk")
            )
        self.fields["reply_to"].queryset = reply_qs

    def clean_to_message(self):
        recipients = self.cleaned_data.get("to_message")
        is_staff = bool(self.user and self.user.is_staff)
        if recipients is not None and recipients.count() > MAX_DESTINATAIRES and not is_staff:
            raise forms.ValidationError(f"{MAX_DESTINATAIRES} destinataires maximum par message.")
        return recipients
