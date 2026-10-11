import datetime
import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_http_methods

from authapp.models import UserRegistration
from chatapp.models import ForumPrivate

from .forms import ComForm, PaymentForm
from .models import (
    AncienEpreuve, Contact, Lesson, Matiere, Newsletter, Niveaux, Payment,
    PaymentIssue, PaymentSettings,
)

logger = logging.getLogger(__name__)

MONTANT_MINIMUM_ABONNEMENT = 1000
MONTANT_MAXIMUM_ABONNEMENT = 1_000_000


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
def client_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def too_many_requests(request, scope, limit, period_seconds):
    """Limiteur simple basé sur le cache : True si la limite est dépassée."""
    key = f"rl:{scope}:{client_ip(request)}"
    added = cache.add(key, 1, period_seconds)
    if added:
        return False
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, period_seconds)
        return False
    return count > limit


def active_subscription(user, niveau):
    """Retourne l'abonnement en cours de l'utilisateur pour ce niveau, ou None."""
    payment = Payment.objects.filter(user=user, niveau=niveau).order_by("-date_expired").first()
    if payment and payment.date_expired >= datetime.date.today():
        return payment
    return None


def is_valid_email(email):
    try:
        validate_email(email)
        return True
    except ValidationError:
        return False


# ---------------------------------------------------------------------------
# Pages d'erreur
# ---------------------------------------------------------------------------
def handels_error404(request, exception):
    return render(request, "programme/404.html", status=404)


def handels_error403(request, exception=None):
    return render(request, "programme/403.html", status=403)


def handels_error500(request):
    return render(request, "programme/500.html", status=500)


# ---------------------------------------------------------------------------
# Pages publiques
# ---------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def index(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        if too_many_requests(request, "newsletter", 5, 3600):
            messages.error(request, "Trop de tentatives. Réessayez plus tard.")
        elif is_valid_email(email):
            Newsletter.objects.get_or_create(email=email)
            messages.success(request, "Merci ! Vous êtes inscrit(e) à la newsletter.")
        else:
            messages.error(request, "Adresse e-mail invalide.")
        return redirect("programme:programme")
    stats = {
        "niveaux": Niveaux.objects.count(),
        "matieres": Matiere.objects.count(),
        "lecons": Lesson.objects.count(),
        "epreuves": AncienEpreuve.objects.count(),
    }
    return render(request, "programme/index.html", {"stats": stats})


def about(request):
    return render(request, "programme/about.html")


@require_http_methods(["GET", "POST"])
def contact(request):
    done = False
    nom = ""
    errors = []
    if request.method == "POST":
        nom = (request.POST.get("nom") or "").strip()[:150]
        email = (request.POST.get("email") or "").strip()[:254]
        sujet = (request.POST.get("sujet") or "").strip()[:300]
        message = (request.POST.get("message") or "").strip()[:5000]
        if too_many_requests(request, "contact", 5, 3600):
            errors.append("Trop de messages envoyés. Réessayez dans une heure.")
        elif not (nom and email and sujet and message):
            errors.append("Tous les champs sont obligatoires.")
        elif not is_valid_email(email):
            errors.append("Adresse e-mail invalide.")
        else:
            contact_obj = Contact.objects.create(nom=nom, email=email, sujet=sujet, message=message)
            try:
                from .tasks import send_admin_contact_email
                send_admin_contact_email.delay(contact_obj.id)
            except Exception:
                logger.exception("Envoi de la notification de contact impossible")
            done = True
    return render(request, "programme/contact.html", {"nom": nom, "done": done, "errors": errors})


def level(request):
    levels = Niveaux.objects.all()
    return render(request, "programme/level.html", {"levels": levels})


# ---------------------------------------------------------------------------
# Espace élève
# ---------------------------------------------------------------------------
@login_required
def student_dashboard(request, slug):
    niveau = get_object_or_404(Niveaux, slug=slug)
    if not request.user.classe.filter(pk=niveau.pk).exists():
        return render(request, "programme/403.html", status=403)

    numbers = ForumPrivate.objects.filter(
        to_message=request.user, created_at__date=timezone.localdate(), deleted=False
    ).count()
    subscription = Payment.objects.filter(user=request.user, niveau=niveau).order_by("-date_expired").first()
    from django.db.models import Count
    from profs.models import CoursProf, ProfilProfesseur
    cours_profs = (CoursProf.objects.filter(niveau=niveau, publie=True, bloque_par_admin=False,
                                            professeur__statut=ProfilProfesseur.Statut.VERIFIE)
                   .select_related("professeur", "matiere").annotate(nb_lecons=Count("lecons")).order_by("-date_creation"))
    context = {
        "cours_profs": cours_profs[:4],
        "nb_cours_profs": cours_profs.count(),
        "niveau_obj": niveau,
        "lecons": Lesson.objects.filter(niveau=niveau).order_by("-date_ajout")[:3],
        "class": niveau.libelle,
        "slug": niveau.slug,
        "exp": subscription.date_expired if subscription else "Aujourd'hui",
        "number": numbers,
    }
    return render(request, "dash/index.html", context)


@login_required
def user_slug(request):
    first = request.user.classe.first()
    if first is None:
        messages.info(request, "Choisissez d'abord une classe pour accéder aux cours.")
        return redirect("programme:level")
    return redirect("programme:courses", slug=first.slug)


@login_required
def courses(request, slug):
    niveau = get_object_or_404(Niveaux, slug=slug)
    context = {"courses": niveau.matieres.all(), "slug": slug}
    return render(request, "dash/browse-courses.html", context)


def _require_subscription(request, niveau, quoi="ce contenu"):
    if active_subscription(request.user, niveau):
        return None
    if Payment.objects.filter(user=request.user, niveau=niveau).exists():
        messages.error(request, "Votre abonnement pour ce niveau a expiré. Veuillez renouveler votre souscription.")
    else:
        messages.error(request, f"Accès refusé. Veuillez souscrire à ce niveau pour accéder à {quoi}.")
    return redirect("programme:billing")


@login_required
def lecons_course(request, niveau_slug, matiere_slug):
    niveau = get_object_or_404(Niveaux, slug=niveau_slug)
    matiere = get_object_or_404(Matiere, slug=matiere_slug, niveau=niveau)
    refus = _require_subscription(request, niveau, "aux cours")
    if refus:
        return refus
    lessons = Lesson.objects.filter(niveau=niveau, matiere=matiere)
    context = {"lessons": lessons, "total": lessons.count(), "refuse": False, "slug": niveau.slug}
    return render(request, "dash/my-courses.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def lecon_detail(request, niveau_slug, matiere_slug, lesson_slug):
    niveau = get_object_or_404(Niveaux, slug=niveau_slug)
    matiere = get_object_or_404(Matiere, slug=matiere_slug, niveau=niveau)
    # La leçon doit appartenir au niveau ET à la matière demandés : avant ce
    # contrôle, un abonné d'un niveau pouvait lire les leçons de tous les niveaux.
    lesson = get_object_or_404(Lesson, slug=lesson_slug, niveau=niveau, matiere=matiere)
    refus = _require_subscription(request, niveau, "cette leçon")
    if refus:
        return refus

    request.session["lesson"] = lesson.pk
    form = ComForm()
    if request.method == "POST":
        form = ComForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.auteur = request.user
            comment.nom_lesson = lesson
            comment.save()
            return HttpResponseRedirect(request.path_info)
    context = {
        "lesson": lesson,
        "lessons": Lesson.objects.filter(niveau=niveau, matiere=matiere),
        "form": form,
        "refuse": False,
        "slug": niveau.slug,
    }
    return render(request, "dash/take-course.html", context)


class PaymentView(LoginRequiredMixin, View):
    """Souscription à un niveau, payée avec le solde du compte."""

    template_name = "dash/billing.html"

    def _context(self, request, form):
        qs = Payment.objects.select_related("niveau", "user").filter(user=request.user)
        return {"form": form, "qs": qs}

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(request, PaymentForm()))

    def post(self, request, *args, **kwargs):
        form = PaymentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Formulaire invalide : vérifiez le niveau et le montant.")
            return render(request, self.template_name, self._context(request, form))

        niveau = form.cleaned_data["niveau"]
        montant = int(form.cleaned_data["montant"])
        if montant < MONTANT_MINIMUM_ABONNEMENT:
            messages.error(request, f"Le minimum de transaction est de {MONTANT_MINIMUM_ABONNEMENT} FCFA.")
            return redirect("programme:billing")
        if montant > MONTANT_MAXIMUM_ABONNEMENT:
            messages.error(request, "Montant trop élevé.")
            return redirect("programme:billing")

        with transaction.atomic():
            # Verrou sur la ligne : deux paiements simultanés ne peuvent pas
            # dépenser deux fois le même solde.
            user = UserRegistration.objects.select_for_update().get(pk=request.user.pk)
            if user.somme < montant:
                messages.error(request, "Solde insuffisant, veuillez recharger votre compte.")
                return redirect("programme:billing")
            user.somme -= montant
            user.save(update_fields=["somme"])
            user.classe.add(niveau)

            today = datetime.date.today()
            current = active_subscription(user, niveau)
            start = current.date_expired if current else today
            Payment.objects.create(
                user=user,
                niveau=niveau,
                montant=montant,
                date_pay=today,
                date_expired=start + datetime.timedelta(days=montant * 30 // 1000),
            )
        messages.success(request, "Paiement réussi !")
        return redirect("programme:billing")


@login_required
@require_http_methods(["GET", "POST"])
def pay(request, *args, **kwargs):
    """Déclaration d'un dépôt Mobile Money (vérifié ensuite par un administrateur)."""
    if request.method == "POST":
        numero = (request.POST.get("numero") or "").strip()[:100]
        description = (request.POST.get("description") or "").strip()[:2000]
        reference = (request.POST.get("reference") or "").strip()[:100]
        date = (request.POST.get("date") or "").strip()[:100]
        try:
            montant = int(request.POST.get("montant") or 0)
        except (TypeError, ValueError):
            montant = -1

        if too_many_requests(request, f"pay:{request.user.pk}", 10, 3600):
            messages.error(request, "Trop de déclarations envoyées. Réessayez plus tard.")
        elif not (numero and reference) or montant < 0 or montant > 10_000_000:
            messages.error(request, "Requête invalide. Veuillez revoir le formulaire.")
        else:
            issue = PaymentIssue.objects.create(
                numero=numero, description=description, reference=reference,
                user=request.user, date=date, montant=montant,
            )
            try:
                from .tasks import send_admin_deposit_email
                send_admin_deposit_email.delay(issue.id)
            except Exception:
                logger.exception("Envoi de la notification de dépôt impossible")
            messages.success(request, "Requête envoyée avec succès. Vous recevrez une réponse dans un délai d’une heure.")

    pay_settings = PaymentSettings.objects.first() or PaymentSettings.objects.create()
    return render(request, "dash/pay.html", {"pay_settings": pay_settings})


def _int_or_none(value, minimum=0, maximum=10_000_000):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None


@staff_member_required()
@require_http_methods(["GET", "POST"])
def adminDashboard(request, *args, **kwargs):
    from aiapp.models import AISettings, Pack

    if request.method == "POST" and "update_ai_settings" in request.POST:
        ai_settings_obj, _ = AISettings.objects.get_or_create(id=1)
        daily = _int_or_none(request.POST.get("default_daily_credits"))
        if daily is not None:
            ai_settings_obj.default_daily_credits = daily
        # Les clés ne sont modifiées que si une nouvelle valeur est saisie ;
        # elles ne sont plus jamais réaffichées ni écrites dans le fichier .env.
        for field in ("openai_api_key", "gemini_api_key"):
            value = (request.POST.get(field) or "").strip()
            if value:
                setattr(ai_settings_obj, field, value[:255])
        ai_settings_obj.save()
        if daily is not None:
            UserRegistration.objects.all().update(last_daily_reset=None)
        messages.success(request, "Paramètres IA mis à jour.")
        return redirect("programme:admin-staff")

    if request.method == "POST" and "create_pack" in request.POST:
        name = (request.POST.get("pack_name") or "").strip()[:100]
        price = _int_or_none(request.POST.get("pack_price"), minimum=1)
        credit = _int_or_none(request.POST.get("pack_credit"), minimum=1)
        icon = (request.POST.get("pack_icon") or "bolt").strip()[:50]
        if name and price and credit:
            Pack.objects.create(name=name, price=price, credit=credit, icon=icon)
            messages.success(request, f"Pack « {name} » créé avec succès !")
        else:
            messages.error(request, "Veuillez remplir correctement tous les champs du pack.")
        return redirect("programme:admin-staff")

    if request.method == "POST" and "delete_pack" in request.POST:
        pack_id = _int_or_none(request.POST.get("pack_id"), minimum=1)
        if pack_id:
            Pack.objects.filter(id=pack_id).delete()
            messages.success(request, "Pack supprimé avec succès !")
        return redirect("programme:admin-staff")

    niveau = Niveaux.objects.all()
    ai_settings, _ = AISettings.objects.get_or_create(id=1)
    context = {
        "niveau": niveau,
        "transaction": Payment.objects.all().order_by("-date_pay")[:5],
        "etudiant": UserRegistration.objects.count(),
        "niveaux": niveau.count(),
        "matieres": Matiere.objects.count(),
        "lecons": Lesson.objects.count(),
        "new_students": UserRegistration.objects.order_by("-date_joined")[:5],
        "paymentissue": PaymentIssue.objects.select_related("user").order_by("-date_added")[:50],
        "ai_settings": ai_settings,
        "packs": Pack.objects.all().order_by("price"),
    }
    return render(request, "programme/instructors/instructor-dashboard.html", context)


@login_required
def liste_anciennes_epreuves(request, slug):
    niveau = get_object_or_404(Niveaux, slug=slug)
    refus = _require_subscription(request, niveau, "aux épreuves")
    if refus:
        return refus

    query = (request.GET.get("q") or "").strip()[:100]
    epreuves = AncienEpreuve.objects.select_related("ecole", "matiere").filter(niveau=niveau).order_by("-date_ajout")
    if query:
        epreuves = epreuves.filter(
            Q(titre__icontains=query) | Q(description__icontains=query) | Q(ecole__nom__icontains=query)
            | Q(matiere__nom__icontains=query)
        ).distinct()

    page_obj = Paginator(epreuves, 20).get_page(request.GET.get("page"))
    context = {"niveau": niveau, "page_obj": page_obj, "slug": slug, "query": query}
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "dash/_epreuves_table_partial.html", context)
    return render(request, "dash/liste_anciennes_epreuves.html", context)


@login_required
def detail_ancienne_epreuve(request, pk):
    epreuve = get_object_or_404(AncienEpreuve.objects.select_related("niveau", "ecole"), pk=pk)
    if not active_subscription(request.user, epreuve.niveau):
        messages.error(request, "Votre abonnement ne vous permet pas d'accéder à cette épreuve.")
        return redirect("programme:billing")
    context = {
        "epreuve": epreuve,
        "autres_epreuves": AncienEpreuve.objects.filter(niveau=epreuve.niveau).exclude(pk=pk).order_by("-date_ajout")[:4],
        "slug": epreuve.niveau.slug,
    }
    return render(request, "dash/detail_ancienne_epreuve.html", context)


# ---------------------------------------------------------------------------
# Documents protégés : lecteur intégré + fichier filigrané
# ---------------------------------------------------------------------------
CHAMPS_LECON = {"pdf": "Leçon", "exercice": "Exercices", "fpe": "Fiche de présentation"}


def _lecon_et_fichier(request, lesson_id, champ):
    if champ not in CHAMPS_LECON:
        raise Http404
    lesson = get_object_or_404(Lesson.objects.select_related("niveau", "matiere"), pk=lesson_id)
    fichier = getattr(lesson, champ)
    if not fichier:
        raise Http404
    autorise = request.user.is_staff or active_subscription(request.user, lesson.niveau)
    return lesson, fichier, autorise


@login_required
def lire_lecon(request, lesson_id, champ):
    lesson, fichier, autorise = _lecon_et_fichier(request, lesson_id, champ)
    if not autorise:
        return _require_subscription(request, lesson.niveau, "cette leçon")
    if not fichier.name.lower().endswith(".pdf"):
        return redirect("programme:document_lecon", lesson_id=lesson.pk, champ=champ)
    return render(request, "dash/lecteur.html", {
        "titre": f"{CHAMPS_LECON[champ]} — {lesson.nom}",
        "url_document": reverse("programme:document_lecon", args=[lesson.pk, champ]),
        "retour": request.META.get("HTTP_REFERER") or reverse("programme:level"),
        "slug": lesson.niveau.slug,
    })


@login_required
def document_lecon(request, lesson_id, champ):
    from Elearning.protection import reponse_document

    lesson, fichier, autorise = _lecon_et_fichier(request, lesson_id, champ)
    if not autorise:
        raise Http404
    return reponse_document(request, fichier, f"lecon-{champ}", lesson.pk, lesson.nom)


@login_required
def lire_epreuve(request, pk):
    epreuve = get_object_or_404(AncienEpreuve.objects.select_related("niveau"), pk=pk)
    if not (request.user.is_staff or active_subscription(request.user, epreuve.niveau)):
        return _require_subscription(request, epreuve.niveau, "cette épreuve")
    return render(request, "dash/lecteur.html", {
        "titre": epreuve.titre,
        "url_document": reverse("programme:document_epreuve", args=[epreuve.pk]),
        "retour": reverse("programme:detail_ancienne_epreuve", args=[epreuve.pk]),
        "slug": epreuve.niveau.slug,
    })


@login_required
def document_epreuve(request, pk):
    from Elearning.protection import reponse_document

    epreuve = get_object_or_404(AncienEpreuve.objects.select_related("niveau"), pk=pk)
    if not (request.user.is_staff or active_subscription(request.user, epreuve.niveau)):
        raise Http404
    return reponse_document(request, epreuve.fichier, "epreuve", epreuve.pk, epreuve.titre)
