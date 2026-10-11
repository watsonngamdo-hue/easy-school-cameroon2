from django.urls import path
from authapp import views

app_name='authapp'
urlpatterns = [
    path('editprofile', views.updateProfile, name='editprofile'),
    path('mark-onboarded', views.mark_onboarded, name='mark-onboarded'),
]