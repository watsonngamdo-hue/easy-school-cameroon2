import re

from django import forms
from django.conf import settings

from Elearning.validators import validate_upload
from programme.models import Matiere, Niveaux

from .models import CoursProf, LeconProf, PieceIdentite, ProfilProfesseur

IMAGES = {".jpg", ".jpeg", ".png", ".webp"}


class ProfilForm(forms.ModelForm):
    class Meta:
        model = ProfilProfesseur
        fields = ["nom_public", "bio", "etablissement", "niveaux", "matieres_texte", "photo",
                  "prix_mensuel", "operateur", "numero_retrait"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 5, "placeholder": "Ton parcours, ta méthode, ce que tes élèves vont apprendre."}),
            "niveaux": forms.CheckboxSelectMultiple(),
            "matieres_texte": forms.TextInput(attrs={"placeholder": "Ex. Mathématiques, Physique"}),
            "nom_public": forms.TextInput(attrs={"placeholder": "Ex. M. Ngono — Maths"}),
            "numero_retrait": forms.TextInput(attrs={"placeholder": "6XX XX XX XX", "inputmode": "tel"}),
            "photo": forms.FileInput(attrs={"accept": "image/*"}),
        }
        help_texts = {"prix_mensuel": "Entre 500 et 20 000 F. Tu reçois 70 % de chaque abonnement."}

    def clean_numero_retrait(self):
        numero = re.sub(r"[\s.\-]", "", self.cleaned_data["numero_retrait"])
        numero = re.sub(r"^(\+?237)", "", numero)
        if not re.fullmatch(r"6\d{8}", numero):
            raise forms.ValidationError("Numéro camerounais à 9 chiffres commençant par 6.")
        return numero

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "content_type"):
            validate_upload(photo, IMAGES, max_mb=3)
        return photo


class PiecesForm(forms.Form):
    cni_recto = forms.FileField(label="CNI — recto (photo)")
    cni_verso = forms.FileField(label="CNI — verso (photo)")
    selfie = forms.FileField(label="Selfie en tenant ta CNI près du visage")
    justificatif = forms.FileField(label="Diplôme ou attestation de l'établissement (photo ou PDF)")

    def __init__(self, *args, deja_fournies=(), **kwargs):
        super().__init__(*args, **kwargs)
        for nom in deja_fournies:
            if nom in self.fields:
                self.fields[nom].required = False
        for f in self.fields.values():
            f.widget.attrs["accept"] = "image/*,.pdf"

    def clean(self):
        data = super().clean()
        for nom, fichier in data.items():
            if fichier:
                autorises = IMAGES | {".pdf"} if nom == "justificatif" else IMAGES
                try:
                    validate_upload(fichier, autorises, max_mb=8)
                except forms.ValidationError as e:
                    self.add_error(nom, e)
        return data


class CoursForm(forms.ModelForm):
    class Meta:
        model = CoursProf
        fields = ["titre", "description", "niveau", "matiere", "miniature", "publie"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "miniature": forms.FileInput(attrs={"accept": "image/*"}),
        }
        labels = {"publie": "Publier le cours (visible par les élèves)", "miniature": "Image de couverture (16:9)"}

    def __init__(self, *args, profil=None, **kwargs):
        super().__init__(*args, **kwargs)
        if profil is not None:
            self.fields["niveau"].queryset = profil.niveaux.all() or Niveaux.objects.all()
        self.fields["matiere"].queryset = Matiere.objects.select_related("niveau").order_by("niveau__ordre", "nom")
        self.fields["matiere"].label_from_instance = lambda m: m.nom
        self.fields["matiere"].required = False

    def clean_miniature(self):
        image = self.cleaned_data.get("miniature")
        if image and hasattr(image, "content_type"):
            validate_upload(image, IMAGES, max_mb=3)
        return image

    def clean(self):
        data = super().clean()
        if data.get("matiere") and data.get("niveau") and data["matiere"].niveau_id != data["niveau"].pk:
            self.add_error("matiere", "Cette matière n'appartient pas à la classe choisie.")
        return data


def verifier_video(fichier):
    taille_max = getattr(settings, "PROF_VIDEO_TAILLE_MAX_MO", 300)
    ext = "." + fichier.name.rsplit(".", 1)[-1].lower() if "." in fichier.name else ""
    if ext not in {".mp4", ".webm", ".m4v"}:
        raise forms.ValidationError("Vidéo au format MP4 ou WEBM uniquement.")
    if fichier.size > taille_max * 1024 * 1024:
        raise forms.ValidationError(f"Vidéo trop lourde ({taille_max} Mo maximum). Compresse-la en 720p.")
    debut = fichier.read(12)
    fichier.seek(0)
    if not (debut[4:8] == b"ftyp" or debut.startswith(b"\x1a\x45\xdf\xa3")):
        raise forms.ValidationError("Le fichier n'est pas une vraie vidéo MP4/WEBM.")


class LeconForm(forms.ModelForm):
    class Meta:
        model = LeconProf
        fields = ["titre", "type", "video", "pdf", "duree_minutes", "apercu_gratuit", "ordre"]
        widgets = {
            "video": forms.FileInput(attrs={"accept": "video/mp4,video/webm"}),
            "pdf": forms.FileInput(attrs={"accept": "application/pdf"}),
            "type": forms.RadioSelect(),
        }
        labels = {"duree_minutes": "Durée (minutes)", "ordre": "Position dans le cours"}

    def clean(self):
        data = super().clean()
        type_ = data.get("type")
        if type_ == LeconProf.Type.VIDEO:
            video = data.get("video")
            if not video and not (self.instance.pk and self.instance.video):
                self.add_error("video", "Ajoute le fichier vidéo.")
            elif video and hasattr(video, "content_type"):
                try:
                    verifier_video(video)
                except forms.ValidationError as e:
                    self.add_error("video", e)
            data["pdf"] = None
        elif type_ == LeconProf.Type.PDF:
            pdf = data.get("pdf")
            if not pdf and not (self.instance.pk and self.instance.pdf):
                self.add_error("pdf", "Ajoute le document PDF.")
            elif pdf and hasattr(pdf, "content_type"):
                try:
                    validate_upload(pdf, {".pdf"}, max_mb=getattr(settings, "PROF_PDF_TAILLE_MAX_MO", 30))
                except forms.ValidationError as e:
                    self.add_error("pdf", e)
            data["video"] = None
        return data


class RetraitForm(forms.Form):
    montant = forms.IntegerField(label="Montant à retirer (FCFA)", min_value=1)
