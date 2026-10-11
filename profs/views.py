from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from Elearning.protection import reponse_document, reponse_video
from programme.models import Niveaux

from .forms import CoursForm, LeconForm, PiecesForm, ProfilForm, RetraitForm
from .models import AbonnementProf, CoursProf, LeconProf, PieceIdentite, ProfilProfesseur
from .services import OperationRefusee, a_acces, abonnement_actif, abonner, demander_retrait, repartition


def _cours_visibles():
    return CoursProf.objects.filter(publie=True, bloque_par_admin=False, professeur__statut=ProfilProfesseur.Statut.VERIFIE)


def _profil_ou_none(user):
    if not user.is_authenticated:
        return None
    return ProfilProfesseur.objects.filter(user=user).first()


# ---------------------------------------------------------------------------
# Côté élèves (public)
# ---------------------------------------------------------------------------
def catalogue(request):
    niveaux = Niveaux.objects.all()
    niveau_slug = request.GET.get("classe", "")
    q = (request.GET.get("q") or "").strip()[:80]
    profs = (ProfilProfesseur.objects.filter(statut=ProfilProfesseur.Statut.VERIFIE)
             .annotate(nb_cours=Count("cours", filter=Q(cours__publie=True, cours__bloque_par_admin=False), distinct=True))
             .filter(nb_cours__gt=0).prefetch_related("niveaux"))
    cours = _cours_visibles().select_related("professeur", "niveau", "matiere").annotate(nb_lecons=Count("lecons"))
    if niveau_slug:
        profs = profs.filter(niveaux__slug=niveau_slug)
        cours = cours.filter(niveau__slug=niveau_slug)
    if q:
        profs = profs.filter(Q(nom_public__icontains=q) | Q(matieres_texte__icontains=q))
        cours = cours.filter(Q(titre__icontains=q) | Q(description__icontains=q) | Q(professeur__nom_public__icontains=q))
    return render(request, "profs/catalogue.html", {
        "profs": profs.distinct()[:24],
        "page_cours": Paginator(cours.distinct(), 12).get_page(request.GET.get("page")),
        "niveaux": niveaux, "niveau_slug": niveau_slug, "q": q,
        "mon_profil": _profil_ou_none(request.user),
    })


def chaine(request, slug):
    profil = get_object_or_404(ProfilProfesseur.objects.prefetch_related("niveaux"), slug=slug)
    proprietaire = request.user.is_authenticated and profil.user_id == request.user.pk
    if not profil.est_verifie and not (proprietaire or request.user.is_staff):
        raise Http404
    cours = profil.cours.annotate(nb_lecons=Count("lecons"))
    if not (proprietaire or request.user.is_staff):
        cours = cours.filter(publie=True, bloque_par_admin=False)
    return render(request, "profs/chaine.html", {
        "profil": profil, "cours": cours, "abonnement": abonnement_actif(request.user, profil),
        "proprietaire": proprietaire, "abonnes": profil.abonnes_actifs(),
        "vues": LeconProf.objects.filter(cours__professeur=profil).aggregate(t=Sum("vues"))["t"] or 0,
    })


@login_required
@require_http_methods(["GET", "POST"])
def s_abonner(request, slug):
    profil = get_object_or_404(ProfilProfesseur, slug=slug, statut=ProfilProfesseur.Statut.VERIFIE)
    en_cours = abonnement_actif(request.user, profil)
    if request.method == "POST":
        try:
            abonnement = abonner(request.user, profil)
        except OperationRefusee as refus:
            messages.error(request, refus.message)
            return redirect("profs:abonner", slug=slug)
        messages.success(request, f"Abonnement activé jusqu'au {timezone.localtime(abonnement.fin):%d/%m/%Y}. Bon apprentissage !")
        return redirect("profs:chaine", slug=slug)
    part_prof, _ = repartition(profil.prix_mensuel)
    return render(request, "profs/abonner.html", {
        "profil": profil, "en_cours": en_cours, "part_prof": part_prof,
        "solde_suffisant": request.user.somme >= profil.prix_mensuel,
        "manque": max(0, profil.prix_mensuel - request.user.somme),
    })


def cours_detail(request, slug):
    cours = get_object_or_404(CoursProf.objects.select_related("professeur", "niveau", "matiere"), slug=slug)
    if not cours.visible and not (request.user.is_staff or (request.user.is_authenticated and cours.professeur.user_id == request.user.pk)):
        raise Http404
    return render(request, "profs/cours.html", {
        "cours": cours, "lecons": cours.lecons.all(), "acces": a_acces(request.user, cours),
        "abonnement": abonnement_actif(request.user, cours.professeur),
    })


def _lecon_autorisee(request, pk):
    lecon = get_object_or_404(LeconProf.objects.select_related("cours__professeur", "cours__niveau"), pk=pk)
    cours = lecon.cours
    proprietaire = request.user.is_authenticated and cours.professeur.user_id == request.user.pk
    if not cours.visible and not (request.user.is_staff or proprietaire):
        raise Http404
    autorise = lecon.apercu_gratuit or a_acces(request.user, cours)
    return lecon, autorise


def lecon_detail(request, pk):
    lecon, autorise = _lecon_autorisee(request, pk)
    # Même l'aperçu gratuit demande un compte : le document est marqué au nom de l'élève.
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")
    if not autorise:
        messages.info(request, "Abonne-toi à ce professeur pour suivre cette leçon.")
        return redirect("profs:abonner", slug=lecon.cours.professeur.slug)
    LeconProf.objects.filter(pk=lecon.pk).update(vues=F("vues") + 1)
    return render(request, "profs/lecon.html", {
        "lecon": lecon, "cours": lecon.cours, "lecons": lecon.cours.lecons.all(),
    })


def lecon_media(request, pk):
    lecon, autorise = _lecon_autorisee(request, pk)
    if not autorise or not request.user.is_authenticated:
        raise Http404
    if lecon.type == LeconProf.Type.VIDEO and lecon.video:
        return reponse_video(request, lecon.video, "prof-video", lecon.pk, lecon.titre)
    if lecon.type == LeconProf.Type.PDF and lecon.pdf:
        return reponse_document(request, lecon.pdf, "prof-pdf", lecon.pk, lecon.titre)
    raise Http404


@login_required
def mes_abonnements(request):
    abonnements = AbonnementProf.objects.filter(eleve=request.user).select_related("professeur").order_by("-fin")
    derniers = {}  # le plus récent par professeur
    for a in abonnements:
        derniers.setdefault(a.professeur_id, a)
    return render(request, "profs/mes_abonnements.html", {"abonnements": list(derniers.values()), "maintenant": timezone.now()})


# ---------------------------------------------------------------------------
# Côté professeurs
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET", "POST"])
def devenir_professeur(request):
    profil = _profil_ou_none(request.user)
    if profil and profil.statut in (ProfilProfesseur.Statut.VERIFIE, ProfilProfesseur.Statut.SUSPENDU):
        return redirect("profs:studio")
    deja = list(profil.pieces.values_list("type", flat=True)) if profil else []
    form = ProfilForm(instance=profil)
    pieces = PiecesForm(deja_fournies=deja)
    if request.method == "POST":
        form = ProfilForm(request.POST, request.FILES, instance=profil)
        pieces = PiecesForm(request.POST, request.FILES, deja_fournies=deja)
        if form.is_valid() and pieces.is_valid():
            with transaction.atomic():
                profil = form.save(commit=False)
                profil.user = request.user
                profil.statut = ProfilProfesseur.Statut.EN_ATTENTE
                profil.date_demande = timezone.now()
                profil.motif_decision = ""
                profil.save()
                form.save_m2m()
                for type_, fichier in pieces.cleaned_data.items():
                    if fichier:
                        ancienne = PieceIdentite.objects.filter(profil=profil, type=type_).first()
                        if ancienne:
                            ancienne.fichier.delete(save=False)
                            ancienne.delete()
                        PieceIdentite.objects.create(profil=profil, type=type_, fichier=fichier)
            messages.success(request, "Dossier envoyé ! Notre équipe vérifie ton identité sous 48 h. "
                                      "Tu peux déjà préparer tes cours dans ton studio.")
            return redirect("profs:studio")
    return render(request, "profs/devenir.html", {"form": form, "pieces": pieces, "profil": profil, "deja": deja,
                                                  "commission": getattr(settings, "PROF_COMMISSION_PLATEFORME", 30),
                                                  "part_prof_pct": 100 - getattr(settings, "PROF_COMMISSION_PLATEFORME", 30)})


def _profil_requis(request):
    profil = _profil_ou_none(request.user)
    if profil is None:
        messages.info(request, "Commence par créer ton profil de professeur.")
    return profil


@login_required
def studio(request):
    profil = _profil_requis(request)
    if profil is None:
        return redirect("profs:devenir")
    retrait_form = RetraitForm()
    return render(request, "profs/studio.html", {
        "profil": profil,
        "cours": profil.cours.annotate(nb_lecons=Count("lecons"), nb_vues=Sum("lecons__vues")),
        "abonnes": profil.abonnes_actifs(),
        "disponible": profil.solde_disponible(), "en_attente": profil.solde_en_attente(), "gains": profil.gains_totaux(),
        "mouvements": profil.mouvements.all()[:15], "retraits": profil.retraits.all()[:10],
        "retrait_form": retrait_form, "minimum": getattr(settings, "PROF_RETRAIT_MINIMUM", 5000),
        "delai": getattr(settings, "PROF_DELAI_DISPONIBILITE_JOURS", 7),
        "commission": getattr(settings, "PROF_COMMISSION_PLATEFORME", 30),
        "part_prof_pct": 100 - getattr(settings, "PROF_COMMISSION_PLATEFORME", 30),
        "maintenant": timezone.now(),
    })


@login_required
@require_POST
def studio_retrait(request):
    profil = _profil_requis(request)
    if profil is None:
        return redirect("profs:devenir")
    form = RetraitForm(request.POST)
    if form.is_valid():
        try:
            demander_retrait(profil, form.cleaned_data["montant"])
            messages.success(request, "Demande de retrait envoyée. Le paiement est fait sous 72 h sur ton numéro Mobile Money.")
        except OperationRefusee as refus:
            messages.error(request, refus.message)
    else:
        messages.error(request, "Montant invalide.")
    return redirect("profs:studio")


@login_required
@require_http_methods(["GET", "POST"])
def studio_cours(request, pk=None):
    profil = _profil_requis(request)
    if profil is None:
        return redirect("profs:devenir")
    cours = get_object_or_404(CoursProf, pk=pk, professeur=profil) if pk else None
    form = CoursForm(instance=cours, profil=profil)
    lecon_form = LeconForm(initial={"ordre": (cours.lecons.count() + 1) if cours else 1})
    if request.method == "POST" and "enregistrer_cours" in request.POST:
        form = CoursForm(request.POST, request.FILES, instance=cours, profil=profil)
        if form.is_valid():
            cours = form.save(commit=False)
            cours.professeur = profil
            cours.save()
            if cours.publie and not profil.est_verifie:
                messages.info(request, "Cours enregistré. Il sera visible dès que ton identité sera vérifiée.")
            else:
                messages.success(request, "Cours enregistré.")
            return redirect("profs:studio_cours", pk=cours.pk)
    elif request.method == "POST" and "ajouter_lecon" in request.POST and cours:
        lecon_form = LeconForm(request.POST, request.FILES)
        if lecon_form.is_valid():
            lecon = lecon_form.save(commit=False)
            lecon.cours = cours
            lecon.save()
            messages.success(request, f"Leçon « {lecon.titre} » ajoutée.")
            return redirect("profs:studio_cours", pk=cours.pk)
    return render(request, "profs/studio_cours.html", {
        "profil": profil, "cours": cours, "form": form, "lecon_form": lecon_form,
        "lecons": cours.lecons.all() if cours else [],
        "video_max": getattr(settings, "PROF_VIDEO_TAILLE_MAX_MO", 300),
    })


@login_required
@require_POST
def studio_supprimer_lecon(request, pk):
    lecon = get_object_or_404(LeconProf, pk=pk, cours__professeur__user=request.user)
    cours_pk = lecon.cours_id
    for fichier in (lecon.video, lecon.pdf):
        if fichier:
            fichier.delete(save=False)
    lecon.delete()
    messages.success(request, "Leçon supprimée.")
    return redirect("profs:studio_cours", pk=cours_pk)


# ---------------------------------------------------------------------------
# Administration : consultation des pièces d'identité
# ---------------------------------------------------------------------------
@staff_member_required
def piece_identite(request, pk):
    piece = get_object_or_404(PieceIdentite, pk=pk)
    try:
        handle = piece.fichier.open("rb")
    except FileNotFoundError:
        raise Http404
    reponse = FileResponse(handle, as_attachment=False)
    reponse["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'"
    reponse["Cache-Control"] = "private, no-store"
    return reponse
