from allauth.account.forms import SignupForm, LoginForm
from authapp.models import UserRegistration
from django import forms
from django.utils.translation import gettext as _

from Elearning.validators import validate_upload


class MyCustomSignupForm(SignupForm, forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(MyCustomSignupForm, self).__init__(*args, **kwargs)

        self.fields['first_name'].label = 'Prénom'
        self.fields['last_name'].label = 'Nom'
        self.fields['numero_telephone'].label = 'Téléphone'
        self.fields['numero_telephone'].widget.attrs.update({'placeholder': '+237 6XX XX XX XX', 'autocomplete': 'tel'})
        self.fields['ville'].label = 'Ville'
        self.fields['email'].label = 'Adresse e-mail'
        self.fields['password1'].label = 'Mot de passe'
        self.fields['password2'].label = 'Confirme le mot de passe'
        self.fields['classe'].required = True

    class Meta:
        model = UserRegistration
        fields = [
            'first_name',
            'last_name',
            'email',
            'numero_telephone',
            'classe',
            'ville',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_telephone': forms.TextInput(attrs={'class': 'form-control'}),
            # Define classe widget here in Meta (not in __init__) so it
            # is not overwritten by the SignupForm + ModelForm MRO
            'classe': forms.CheckboxSelectMultiple(),
            'ville': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def save(self, request):
        user = super(MyCustomSignupForm, self).save(request)

        classe = self.cleaned_data.get('classe')
        if classe:
            for cls in classe:
                user.classe.add(cls)

        user.ville = self.cleaned_data.get('ville')
        user.email = self.cleaned_data.get('email')
        user.numero_telephone = self.cleaned_data.get('numero_telephone')
        user.save()

        return user


class MyCustomLoginForm(LoginForm):

    def __init__(self, *args, **kwargs):
        super(MyCustomLoginForm, self).__init__(*args, **kwargs)

        self.fields['login'].label = 'Adresse e-mail'
        self.fields['password'].label = 'Mot de passe'

    def login(self, *args, **kwargs):
        return super(MyCustomLoginForm, self).login(*args, **kwargs)


class EditAccountForm(forms.ModelForm):

    def clean_avater(self):
        avatar = self.cleaned_data.get("avater")
        if avatar and hasattr(avatar, "content_type"):
            validate_upload(avatar, {".png", ".jpg", ".jpeg", ".webp"}, max_mb=3)
        return avatar

    class Meta:
        model = UserRegistration
        fields = [
            'first_name',
            'last_name',
            'avater',
            'classe',
            'numero_telephone',
            'ville',
        ]
        labels = {
            'avater': 'Photo de profile',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_telephone': forms.TextInput(attrs={'class': 'form-control'}),
            # Same fix here — define in Meta so Select2 picks it up correctly
            'classe': forms.SelectMultiple(attrs={
                'class': 'form-control select2-multiple',
                'multiple': 'multiple',
                'style': 'width: 100%;',
            }),
            'ville': forms.TextInput(attrs={'class': 'form-control'}),
            'avater': forms.FileInput(attrs={'class': 'form-control'}),
        }