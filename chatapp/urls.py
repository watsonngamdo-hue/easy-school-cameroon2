from django.urls import path

from .views import ForumView, ForumViewPrivate

app_name = "chatapp"
urlpatterns = [
    path('forum<slug:niveau_slug>/<slug:matiere_slug>', ForumView.as_view(), name="forum"),
    path('forum-private', ForumViewPrivate.as_view(), name="forum-private"),
]
