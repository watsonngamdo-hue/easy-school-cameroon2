"""Protection des contenus payants (cours, épreuves, cours des professeurs).

Aucune protection ne peut empêcher à 100 % une capture d'écran ou une photo de
l'écran. Le but est de rendre le partage difficile, traçable et dissuasif :

1. les fichiers ne sont plus accessibles par une adresse publique : chaque
   ouverture repasse par Django, qui vérifie l'abonnement à ce moment-là ;
2. chaque PDF est marqué au nom de l'élève (filigrane + pied de page) : une copie
   qui circule désigne immédiatement le compte qui l'a fait fuiter ;
3. les documents s'ouvrent dans un lecteur intégré, sans bouton de téléchargement ;
4. chaque ouverture est journalisée et le nombre d'ouvertures par heure est limité ;
5. un compte ne peut être connecté que sur un nombre limité d'appareils.
"""
import io
import logging
import mimetypes
import os
import re

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, HttpResponse, HttpResponseRedirect, StreamingHttpResponse
from django.utils import timezone

logger = logging.getLogger(__name__)

LIMITE_OUVERTURES_PAR_HEURE = getattr(settings, "PROTECTION_LIMITE_PAR_HEURE", 120)


def ip_client(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR") or None)


def identite(user):
    nom = f"{user.first_name} {user.last_name}".strip() or "Élève"
    tel = str(getattr(user, "numero_telephone", "") or "")
    return nom, user.email, tel


def trop_d_ouvertures(user):
    cle = f"protection:{user.pk}"
    if cache.add(cle, 1, 3600):
        return False
    try:
        return cache.incr(cle) > LIMITE_OUVERTURES_PAR_HEURE
    except ValueError:
        cache.set(cle, 1, 3600)
        return False


def journaliser(request, type_document, objet_id, titre):
    from programme.models import AccesDocument

    try:
        AccesDocument.objects.create(
            utilisateur=request.user, type_document=type_document, objet_id=objet_id, titre=str(titre)[:300],
            adresse_ip=ip_client(request), appareil=request.META.get("HTTP_USER_AGENT", "")[:300],
        )
    except Exception:  # le journal ne doit jamais bloquer la lecture
        logger.exception("Journalisation d'accès impossible")


# ---------------------------------------------------------------------------
# Filigrane PDF
# ---------------------------------------------------------------------------
def _calque(largeur, hauteur, nom, email, tel, date):
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=(largeur, hauteur))
    # Filigrane diagonal répété
    c.saveState()
    c.setFillColor(Color(0.04, 0.36, 0.28, alpha=0.11))
    taille = max(14, min(largeur, hauteur) / 22)
    c.setFont("Helvetica-Bold", taille)
    c.translate(largeur / 2, hauteur / 2)
    c.rotate(35)
    for dy in (-hauteur * 0.45, -hauteur * 0.15, hauteur * 0.15, hauteur * 0.45):
        c.drawCentredString(0, dy, f"{nom} · {email}")
    c.restoreState()
    # Pied de page lisible
    c.setFillColor(Color(0.04, 0.29, 0.23, alpha=0.85))
    c.setFont("Helvetica", 7)
    texte = (f"Document personnel de {nom} ({email}{' · ' + tel if tel else ''}) — ouvert le {date} sur EasySchool. "
             "Diffusion interdite : toute copie est traçable.")
    c.drawCentredString(largeur / 2, 12, texte[:180])
    c.save()
    return tampon.getvalue()


def filigraner_pdf(contenu, user):
    from pypdf import PdfReader, PdfWriter

    nom, email, tel = identite(user)
    date = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    lecteur = PdfReader(io.BytesIO(contenu))
    ecrivain = PdfWriter()
    calques = {}
    for page in lecteur.pages:
        largeur, hauteur = float(page.mediabox.width), float(page.mediabox.height)
        cle = (round(largeur), round(hauteur))
        if cle not in calques:
            calques[cle] = PdfReader(io.BytesIO(_calque(largeur, hauteur, nom, email, tel, date))).pages[0]
        page.merge_page(calques[cle])
        ecrivain.add_page(page)
    ecrivain.add_metadata({"/Producer": "EasySchool", "/EasySchoolLicence": f"compte-{user.pk}"})
    sortie = io.BytesIO()
    ecrivain.write(sortie)
    return sortie.getvalue()


def _entetes_prives(reponse):
    reponse["Cache-Control"] = "private, no-store, max-age=0"
    reponse["X-Robots-Tag"] = "noindex, nofollow"
    reponse["X-Content-Type-Options"] = "nosniff"
    return reponse


def reponse_document(request, fichier, type_document, objet_id, titre):
    """Renvoie un document payant après vérification (à faire par l'appelant)."""
    if trop_d_ouvertures(request.user):
        return HttpResponse("Trop de documents ouverts en peu de temps. Réessaie dans une heure.", status=429)
    journaliser(request, type_document, objet_id, titre)
    nom_fichier = os.path.basename(fichier.name)
    extension = nom_fichier.rsplit(".", 1)[-1].lower() if "." in nom_fichier else ""
    try:
        with fichier.open("rb") as f:
            contenu = f.read()
    except (FileNotFoundError, OSError):
        logger.warning("Fichier introuvable : %s", fichier.name)
        return HttpResponse("Ce document est introuvable. Signale-le à l'équipe EasySchool.", status=404)
    propre = re.sub(r"[^A-Za-z0-9_-]+", "-", str(titre))[:60].strip("-") or "document"
    if extension == "pdf":
        try:
            contenu = filigraner_pdf(contenu, request.user)
        except Exception:
            logger.exception("Filigrane impossible pour %s", fichier.name)
            return HttpResponse("Ce document est momentanément indisponible.", status=503)
        reponse = HttpResponse(contenu, content_type="application/pdf")
        reponse["Content-Disposition"] = f'inline; filename="{propre}.pdf"'
        reponse["Content-Security-Policy"] = "sandbox; default-src 'none'"
    else:
        type_mime = mimetypes.guess_type(nom_fichier)[0] or "application/octet-stream"
        reponse = HttpResponse(contenu, content_type=type_mime)
        reponse["Content-Disposition"] = f'attachment; filename="{propre}.{extension}"'
    return _entetes_prives(reponse)


# ---------------------------------------------------------------------------
# Vidéo (lecture avec avance rapide, sans adresse publique)
# ---------------------------------------------------------------------------
_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def reponse_video(request, fichier, type_document, objet_id, titre):
    if trop_d_ouvertures(request.user):
        return HttpResponse("Trop de vidéos ouvertes en peu de temps.", status=429)
    if request.headers.get("Range", "bytes=0-").startswith("bytes=0-"):
        journaliser(request, type_document, objet_id, titre)  # une fois par lecture, pas à chaque morceau
    stockage = fichier.storage
    type_mime = mimetypes.guess_type(fichier.name)[0] or "video/mp4"

    # Stockage S3 : lien signé valable 5 minutes.
    if not hasattr(stockage, "path"):
        return _entetes_prives(HttpResponseRedirect(stockage.url(fichier.name)))

    chemin = stockage.path(fichier.name)
    if not os.path.exists(chemin):
        return HttpResponse("Cette vidéo est introuvable.", status=404)
    taille = os.path.getsize(chemin)
    plage = _RANGE.match(request.headers.get("Range", ""))
    if plage:
        debut = int(plage.group(1) or 0)
        fin = int(plage.group(2)) if plage.group(2) else min(debut + 2 * 1024 * 1024, taille) - 1
        fin = min(fin, taille - 1)
        if debut > fin:
            reponse = HttpResponse(status=416)
            reponse["Content-Range"] = f"bytes */{taille}"
            return reponse
        longueur = fin - debut + 1

        def morceaux():
            with open(chemin, "rb") as f:
                f.seek(debut)
                reste = longueur
                while reste > 0:
                    bloc = f.read(min(65536, reste))
                    if not bloc:
                        break
                    reste -= len(bloc)
                    yield bloc

        reponse = StreamingHttpResponse(morceaux(), status=206, content_type=type_mime)
        reponse["Content-Range"] = f"bytes {debut}-{fin}/{taille}"
        reponse["Content-Length"] = str(longueur)
    else:
        reponse = FileResponse(open(chemin, "rb"), content_type=type_mime)
        reponse["Content-Length"] = str(taille)
    reponse["Accept-Ranges"] = "bytes"
    reponse["Content-Disposition"] = "inline"
    return _entetes_prives(reponse)
