from django.urls import path

from . import views

app_name = "depot"
urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("merci/", views.merci, name="merci"),
    path("matieres/<int:niveau_id>/", views.matieres, name="matieres"),
    path("fichier/<int:pk>/", views.fichier, name="fichier"),
]
