from .models import Commentaire, Payment, Reponse, UserRegistration
from django import forms 

class ComForm(forms.ModelForm):
    def clean_corps(self):
        corps = (self.cleaned_data.get("corps") or "").strip()
        if not corps:
            raise forms.ValidationError("Le commentaire est vide.")
        if len(corps) > 3000:
            raise forms.ValidationError("Commentaire trop long (3000 caractères maximum).")
        return corps

    class Meta:
        model = Commentaire
        fields = ('corps',)
        labels = {'corps': ''}
        widgets = {
            'corps':forms.Textarea(attrs={
                'class':'form-control',
                'rows':4,
                'cols':70,
                'placeholder':'Entrez votre commentaire ici.'
            })
        }        

class RepForm(forms.ModelForm):
    class Meta:
        model = Reponse
        fields = ('corps',)
        labels = {'corps': 'Reponses'}
        widgets = {
            'corps':forms.Textarea(attrs={
                'class':'form-control',
                'rows':2,
                'cols':10,
                'placeholder':'Repondez a ce commentaire ici.'
            })
        }
class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            'niveau',
            'montant'
        ]

        widgets = {
            'niveau': forms.Select(attrs={
                'class':'form-control'
            }),
             'montant': forms.TextInput(attrs={
                'class':'form-control'
            }),
        }