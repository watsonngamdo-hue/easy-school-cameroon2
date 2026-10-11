from django.urls import path
from .views import  (
    PaymentView, about, adminDashboard, contact, courses, index, lecon_detail,
    lecons_course, level, pay, student_dashboard, user_slug,
    liste_anciennes_epreuves, detail_ancienne_epreuve,
    lire_lecon, document_lecon, lire_epreuve, document_epreuve,
    )

app_name = "programme"
urlpatterns = [
    path('', index, name='programme'),
    path('about', about, name="about"),
    path('level', level, name='level'),
    path('contact', contact, name='contact'),
    path('student_dashboard/<slug:slug>', student_dashboard, name='student_dashboard'),
    path('courses/<slug:slug>', courses, name="courses"),
    path('courses/', user_slug, name="courses"),
    path('lecons_course/<slug:niveau_slug>/<slug:matiere_slug>', lecons_course, name="lecons_course"),
    path('lecon_detail/<slug:niveau_slug>/<slug:matiere_slug>/<slug:lesson_slug>', lecon_detail, name="lecon_detail"),
    path('billing', PaymentView.as_view(), name="billing"),
    path('pay', pay, name="pay",),
    path('admin-staff', adminDashboard, name='admin-staff'),
    path('anciennes-epreuves/<slug:slug>', liste_anciennes_epreuves, name='liste_anciennes_epreuves'),
    path('detail-epreuve/<int:pk>', detail_ancienne_epreuve, name='detail_ancienne_epreuve'),
    path('lire/lecon/<int:lesson_id>/<str:champ>', lire_lecon, name='lire_lecon'),
    path('document/lecon/<int:lesson_id>/<str:champ>', document_lecon, name='document_lecon'),
    path('lire/epreuve/<int:pk>', lire_epreuve, name='lire_epreuve'),
    path('document/epreuve/<int:pk>', document_epreuve, name='document_epreuve'),
    ]

