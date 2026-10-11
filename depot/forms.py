import datetime
import re

from django import forms

from programme.models import Matiere, Niveaux

from .models import EpreuveSoumise


def annees_scolaires():
    an = datetime.date.today().year
    # L'année scolaire camerounaise commence en septembre.
    courante = an if datetime.date.today().month >= 9 else an - 1
    return [(f"{a}-{a + 1}", f"{a}-{a + 1}") for a in range(courante, courante - 8, -1)]


class DepotForm(forms.Form):
    titre = forms.CharField(
        label="Titre de l'épreuve", max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Ex. Mathématiques – 2e séquence", "autocomplete": "off"}),
    )
    niveau = forms.ModelChoiceField(label="Classe", queryset=Niveaux.objects.all(), empty_label="Choisir la classe")
    matiere = forms.ModelChoiceField(label="Matière", queryset=Matiere.objects.select_related("niveau").order_by("niveau__ordre", "nom"), empty_label="Choisir la matière")
    etablissement = forms.CharField(
        label="Établissement", max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Ex. Lycée bilingue de Deïdo", "autocomplete": "organization"}),
    )
    type_evaluation = forms.ChoiceField(label="Évaluation", choices=[("", "Choisir l'évaluation")] + list(EpreuveSoumise.Type.choices))
    annee_scolaire = forms.ChoiceField(label="Année scolaire")
    fichier = forms.FileField(
        label="Fichier de l'épreuve",
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/*"}),
    )
    certification = forms.BooleanField(
        label="Je certifie que ce document est une vraie épreuve de classe et que je peux la partager.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["annee_scolaire"].choices = annees_scolaires()
        self.fields["matiere"].label_from_instance = lambda m: m.nom

    def clean_titre(self):
        titre = re.sub(r"\s+", " ", self.cleaned_data["titre"]).strip()
        if len(titre) < 5:
            raise forms.ValidationError("Donne un titre plus précis (5 caractères minimum).")
        return titre

    def clean_etablissement(self):
        nom = re.sub(r"\s+", " ", self.cleaned_data["etablissement"]).strip()
        if len(nom) < 3:
            raise forms.ValidationError("Indique le nom complet de l'établissement.")
        return nom

    def clean(self):
        data = super().clean()
        niveau, matiere = data.get("niveau"), data.get("matiere")
        if niveau and matiere and matiere.niveau_id != niveau.pk:
            self.add_error("matiere", "Cette matière n'appartient pas à la classe choisie.")
        return data
