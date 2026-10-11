from django.contrib import admin, messages
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import AbonnementProf, CoursProf, DemandeRetrait, LeconProf, MouvementProf, PieceIdentite, ProfilProfesseur
from .services import OperationRefusee, marquer_retrait_paye, refuser_retrait


class PieceInline(admin.TabularInline):
    model = PieceIdentite
    extra = 0
    fields = ("type", "voir", "date")
    readonly_fields = ("type", "voir", "date")
    can_delete = True

    @admin.display(description="Document")
    def voir(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">Ouvrir</a>', reverse("profs:piece", args=[obj.pk]))

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProfilProfesseur)
class ProfilProfesseurAdmin(admin.ModelAdmin):
    list_display = ("nom_public", "user", "statut", "prix_mensuel", "date_demande", "nb_pieces")
    list_filter = ("statut",)
    search_fields = ("nom_public", "user__email", "user__last_name", "numero_retrait")
    readonly_fields = ("user", "slug", "date_demande", "date_decision", "date_creation")
    inlines = [PieceInline]
    actions = ["verifier", "refuser", "suspendre"]

    @admin.display(description="Pièces")
    def nb_pieces(self, obj):
        return f"{obj.pieces.count()}/4"

    def _decider(self, request, queryset, statut, motif):
        n = queryset.update(statut=statut, date_decision=timezone.now(), motif_decision=motif)
        self.message_user(request, f"{n} professeur(s) : {ProfilProfesseur.Statut(statut).label}.", messages.SUCCESS)

    @admin.action(description="Vérifier l'identité (le professeur peut publier et vendre)")
    def verifier(self, request, queryset):
        incomplets = [p.nom_public for p in queryset if p.pieces.count() < 4]
        if incomplets:
            self.message_user(request, f"Dossier incomplet : {', '.join(incomplets)}.", messages.ERROR)
            return
        self._decider(request, queryset, ProfilProfesseur.Statut.VERIFIE, "")

    @admin.action(description="Refuser (pièces non conformes)")
    def refuser(self, request, queryset):
        self._decider(request, queryset, ProfilProfesseur.Statut.REFUSE, "Pièces non conformes : merci de renvoyer des photos nettes.")

    @admin.action(description="Suspendre (cours retirés du site)")
    def suspendre(self, request, queryset):
        self._decider(request, queryset, ProfilProfesseur.Statut.SUSPENDU, "Compte suspendu par l'équipe EasySchool.")


class LeconInline(admin.TabularInline):
    model = LeconProf
    extra = 0
    fields = ("ordre", "titre", "type", "apercu_gratuit", "vues")
    readonly_fields = ("vues",)


@admin.register(CoursProf)
class CoursProfAdmin(admin.ModelAdmin):
    list_display = ("titre", "professeur", "niveau", "publie", "bloque_par_admin", "date_creation")
    list_filter = ("publie", "bloque_par_admin", "niveau")
    search_fields = ("titre", "professeur__nom_public")
    list_editable = ("bloque_par_admin",)
    inlines = [LeconInline]


@admin.register(AbonnementProf)
class AbonnementProfAdmin(admin.ModelAdmin):
    list_display = ("eleve", "professeur", "montant", "part_professeur", "part_plateforme", "debut", "fin")
    list_filter = ("professeur",)
    search_fields = ("eleve__email", "professeur__nom_public")
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        t = AbonnementProf.objects.aggregate(p=Sum("part_plateforme"), f=Sum("part_professeur"))
        self.message_user(request, f"Revenus EasySchool : {t['p'] or 0} F — versés aux professeurs : {t['f'] or 0} F.")
        return super().changelist_view(request, extra_context)


@admin.register(DemandeRetrait)
class DemandeRetraitAdmin(admin.ModelAdmin):
    list_display = ("professeur", "montant", "operateur", "numero", "statut", "reference_paiement", "date")
    list_filter = ("statut", "operateur")
    list_editable = ("reference_paiement",)
    readonly_fields = ("professeur", "montant", "operateur", "numero", "statut", "date", "date_traitement")
    actions = ["marquer_payee", "refuser"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Marquer comme payée (saisir d'abord la référence Mobile Money)")
    def marquer_payee(self, request, queryset):
        for retrait in queryset:
            try:
                marquer_retrait_paye(retrait, retrait.reference_paiement)
            except OperationRefusee as e:
                self.message_user(request, f"{retrait} : {e.message}", messages.ERROR)

    @admin.action(description="Refuser (le montant est recrédité au professeur)")
    def refuser(self, request, queryset):
        for retrait in queryset:
            refuser_retrait(retrait, "Numéro Mobile Money invalide ou injoignable.")


@admin.register(MouvementProf)
class MouvementProfAdmin(admin.ModelAdmin):
    list_display = ("professeur", "type", "montant", "disponible_le", "libelle", "date")
    list_filter = ("type",)
    search_fields = ("professeur__nom_public",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
