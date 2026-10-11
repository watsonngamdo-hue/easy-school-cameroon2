from django.contrib import admin
from .models import Contact, Niveaux, Matiere, Lesson, Commentaire, Reponse, Payment, PaymentIssue, Newsletter, Ecole, AncienEpreuve

# Register your models here.


class AdminNiveau(admin.ModelAdmin):
    list_display = ('niveau', 'slug', 'description')
    search_fields = ('niveau',) 
    


class AdminMatiere(admin.ModelAdmin):
    list_display = ('matiere_id', 'nom', 'niveau')
    search_fields = ('nom', ) 
    list_editable = ('nom',)

class AdminLesson(admin.ModelAdmin):
    list_display = ('lesson_id', 'nom', 'matiere', 'niveau')
    search_fields = ('nom',) 
    list_editable = ('nom',)

class AdminCommentaire(admin.ModelAdmin):
    list_display = ('nom_comm', 'nom_lesson', 'date_added')
    search_fields = ('nom_lesson',) 
    
class AdminPayment(admin.ModelAdmin):
    list_display = ('user', 'niveau', 'montant', 'date_pay', 'date_expired')
    search_fields = ('user',) 
  
class AdminPaymentIssue(admin.ModelAdmin):
    list_display = ('user', 'numero', 'reference', 'date_added', 'date')
    search_fields = ('numero', 'user__first_name', 'user__last_name', 'reference')
    list_filter = ('date_added', 'user')

class AdminNewsletter(admin.ModelAdmin):
    list_display = ('email', 'creer_le')
    search_fields = ('creer_le')    

@admin.register(Contact)
class AdminContact(admin.ModelAdmin):
    list_display = ('nom', 'email', 'sujet', 'message', 'date')
    search_fields = ('date', )

admin.site.register(Niveaux, AdminNiveau)
admin.site.register(Matiere, AdminMatiere)
admin.site.register(Lesson, AdminLesson)
admin.site.register(Commentaire, AdminCommentaire)
admin.site.register(Reponse)
admin.site.register(Payment, AdminPayment)
admin.site.register(PaymentIssue, AdminPaymentIssue)
admin.site.register(Newsletter)

@admin.register(Ecole)
class AdminEcole(admin.ModelAdmin):
    list_display = ('nom', 'adresse')
    search_fields = ('nom',)

@admin.register(AncienEpreuve)
class AdminAncienEpreuve(admin.ModelAdmin):
    list_display = ('titre', 'ecole', 'niveau', 'matiere', 'annee', 'date_ajout')
    list_filter = ('niveau', 'matiere', 'annee', 'ecole')
    search_fields = ('titre', 'description')

from .models import ReseauxSociaux, PaymentSettings

@admin.register(ReseauxSociaux)
class ReseauxSociauxAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

@admin.register(PaymentSettings)
class PaymentSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

from .models import AccesDocument


@admin.register(AccesDocument)
class AccesDocumentAdmin(admin.ModelAdmin):
    list_display = ("date", "utilisateur", "type_document", "titre", "adresse_ip")
    list_filter = ("type_document", "date")
    search_fields = ("utilisateur__email", "utilisateur__last_name", "titre", "adresse_ip")
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
