from django.urls import path

from . import views

app_name = "profs"
urlpatterns = [
    path("", views.catalogue, name="catalogue"),
    path("devenir-professeur/", views.devenir_professeur, name="devenir"),
    path("studio/", views.studio, name="studio"),
    path("studio/retrait/", views.studio_retrait, name="studio_retrait"),
    path("studio/cours/nouveau/", views.studio_cours, name="studio_nouveau_cours"),
    path("studio/cours/<int:pk>/", views.studio_cours, name="studio_cours"),
    path("studio/lecon/<int:pk>/supprimer/", views.studio_supprimer_lecon, name="studio_supprimer_lecon"),
    path("mes-abonnements/", views.mes_abonnements, name="mes_abonnements"),
    path("cours/<slug:slug>/", views.cours_detail, name="cours"),
    path("lecon/<int:pk>/", views.lecon_detail, name="lecon"),
    path("lecon/<int:pk>/media/", views.lecon_media, name="lecon_media"),
    path("piece/<int:pk>/", views.piece_identite, name="piece"),
    path("<slug:slug>/abonner/", views.s_abonner, name="abonner"),
    path("<slug:slug>/", views.chaine, name="chaine"),
]
