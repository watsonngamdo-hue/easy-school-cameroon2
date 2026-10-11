from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from programme.models import Matiere
from programme.views import client_ip, too_many_requests

from .forms import DepotForm
from .models import EpreuveSoumise, MouvementSolde
from .services import DepotRefuse, enregistrer_epreuve


@require_http_methods(["GET", "POST"])
def accueil(request):
    form = DepotForm()
    resultat = None  # "ok" | "doublon" | "refus"

    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={request.path}")
        form = DepotForm(request.POST, request.FILES)
        if too_many_requests(request, f"depot:{request.user.pk}", 30, 3600):
            messages.error(request, "Trop d'envois en peu de temps. Patiente un peu avant de réessayer.")
            resultat = "refus"
        elif form.is_valid():
            try:
                epreuve = enregistrer_epreuve(
                    request.user, form.cleaned_data, form.cleaned_data["fichier"], adresse_ip=client_ip(request) or None
                )
            except DepotRefuse as refus:
                resultat = "doublon" if refus.doublon else "refus"
                messages.error(request, refus.message)
            else:
                request.session["depot_dernier"] = epreuve.pk
                return redirect("depot:merci")
        else:
            resultat = "refus"

    context = {"form": form, "resultat": resultat, "taille_max": settings.DEPOT_TAILLE_MAX_MO}
    if request.user.is_authenticated:
        context.update(_espace_eleve(request.user))
    context["total_epreuves"] = EpreuveSoumise.objects.exclude(statut=EpreuveSoumise.Statut.REJETEE).count()
    return render(request, "depot/accueil.html", context)


def _espace_eleve(user):
    mes_epreuves = EpreuveSoumise.objects.filter(eleve=user).select_related("niveau", "matiere")
    stats = mes_epreuves.aggregate(
        envoyees=Count("id"),
        rejetees=Count("id", filter=Q(statut=EpreuveSoumise.Statut.REJETEE)),
    )
    gains = MouvementSolde.objects.filter(eleve=user).aggregate(total=Sum("montant"))["total"] or 0
    return {"mes_epreuves": mes_epreuves[:20], "stats": stats, "gains": gains}


@login_required
def merci(request):
    pk = request.session.pop("depot_dernier", None)
    if not pk:
        return redirect("depot:accueil")
    epreuve = get_object_or_404(EpreuveSoumise, pk=pk, eleve=request.user)
    request.user.refresh_from_db(fields=["somme"])
    return render(request, "depot/merci.html", {"epreuve": epreuve})


@require_GET
def matieres(request, niveau_id):
    data = list(Matiere.objects.filter(niveau_id=niveau_id).order_by("nom").values("id", "nom"))
    return JsonResponse({"matieres": data})


@login_required
def fichier(request, pk):
    epreuve = get_object_or_404(EpreuveSoumise, pk=pk)
    if not (request.user.is_staff or epreuve.eleve_id == request.user.pk):
        raise Http404
    try:
        handle = epreuve.fichier.open("rb")
    except FileNotFoundError:
        raise Http404
    nom = f"epreuve-{epreuve.pk}.{'pdf' if epreuve.type_fichier == 'pdf' else ('png' if epreuve.type_fichier == 'png' else 'jpg')}"
    response = FileResponse(handle, as_attachment=False, filename=nom)
    response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'"
    response["Cache-Control"] = "private, no-store"
    return response
