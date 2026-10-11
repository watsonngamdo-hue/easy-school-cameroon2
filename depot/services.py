"""Analyse des fichiers et enregistrement d'une épreuve avec crédit du solde.

Une épreuve est refusée comme doublon si l'une de ces conditions est vraie :
  1. le fichier est identique octet par octet à un fichier déjà reçu (SHA-256) ;
  2. (PDF avec texte) le texte, une fois normalisé, est identique à celui d'une
     épreuve déjà reçue — même si le fichier a été renommé ou ré-enregistré ;
  3. l'image (ou la 1re page d'un PDF scanné) est visuellement quasi identique
     à une épreuve déjà reçue — même après recompression ou redimensionnement ;
  4. une épreuve du même établissement, de la même classe, de la même matière,
     du même type d'évaluation et de la même année existe déjà.
"""
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from PIL import Image, ImageOps

from authapp.models import UserRegistration
from programme.models import AncienEpreuve, Ecole

from .models import EpreuveSoumise, MouvementSolde

Image.MAX_IMAGE_PIXELS = 40_000_000  # protection contre les « bombes » d'images

EXTENSIONS = {"pdf": "pdf", "jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}
TEXTE_MINIMUM = 150          # en dessous, le PDF est considéré comme scanné
SIMILARITE_MIN = 0.92        # mesuré : copie recompressée ≥ 0.93, épreuve différente ≤ 0.80
PAGES_MAX = 40
COTE_MIN_IMAGE = 500         # px : refuse les vignettes illisibles


class DepotRefuse(Exception):
    """Envoi refusé, avec un message destiné à l'élève."""

    def __init__(self, message, doublon=False):
        super().__init__(message)
        self.message = message
        self.doublon = doublon


@dataclass
class Analyse:
    contenu: bytes
    type_fichier: str
    nombre_pages: int = 1
    empreinte_fichier: str = ""
    empreinte_texte: str | None = None
    empreinte_visuelle: str | None = None
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normaliser(texte):
    """minuscules, sans accents, sans ponctuation ni espaces multiples."""
    texte = unicodedata.normalize("NFKD", texte or "")
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def normaliser_etablissement(nom):
    nom = normaliser(nom)
    # « lycée bilingue de deido » == « lycee bilingue deido »
    mots_vides = {"de", "du", "des", "d", "la", "le", "les", "l", "et"}
    return " ".join(m for m in nom.split() if m not in mots_vides)


def cle_epreuve(etablissement, niveau_id, matiere_id, type_evaluation, annee):
    if type_evaluation == EpreuveSoumise.Type.DEVOIR:
        return None  # plusieurs devoirs peuvent exister pour une même matière
    return f"{normaliser_etablissement(etablissement)}|{niveau_id}|{matiere_id}|{type_evaluation}|{annee}"


# ---------------------------------------------------------------------------
# Empreintes
# ---------------------------------------------------------------------------
TAILLE_SIGNATURE = 32


def signature_visuelle(image):
    """Vignette 32×32 en niveaux de gris de la zone écrite de la page (hexadécimal).

    La page est d'abord recadrée sur l'encre (les marges blanches sont ignorées),
    ce qui rend la signature insensible au redimensionnement, à la recompression
    et à un léger recadrage."""
    gris = ImageOps.exif_transpose(image).convert("L")
    petit = gris.copy()
    petit.thumbnail((800, 800))
    boite = petit.point(lambda p: 255 if p < 110 else 0).getbbox()
    if boite:
        sx, sy = gris.size[0] / petit.size[0], gris.size[1] / petit.size[1]
        gris = gris.crop((int(boite[0] * sx), int(boite[1] * sy), int(boite[2] * sx), int(boite[3] * sy)))
    vignette = gris.resize((TAILLE_SIGNATURE, TAILLE_SIGNATURE), Image.BOX)
    return bytes(vignette.getdata()).hex()


def similarite(sig_a, sig_b):
    """Corrélation de Pearson entre deux signatures (1 = identiques)."""
    a, b = bytes.fromhex(sig_a), bytes.fromhex(sig_b)
    if len(a) != len(b) or not a:
        return 0.0
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def _analyser_pdf(contenu):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        lecteur = PdfReader(io.BytesIO(contenu))
        if lecteur.is_encrypted:
            raise DepotRefuse("Ce PDF est protégé par un mot de passe. Envoie une version non protégée.")
        pages = len(lecteur.pages)
    except DepotRefuse:
        raise
    except (PdfReadError, Exception):
        raise DepotRefuse("Ce PDF est illisible ou endommagé.")
    if pages == 0:
        raise DepotRefuse("Ce PDF ne contient aucune page.")
    if pages > PAGES_MAX:
        raise DepotRefuse(f"Ce PDF compte {pages} pages : une épreuve en fait {PAGES_MAX} au maximum.")

    texte = []
    for page in lecteur.pages[:PAGES_MAX]:
        try:
            texte.append(page.extract_text() or "")
        except Exception:
            continue
    texte = normaliser(" ".join(texte))
    empreinte_texte = hashlib.sha256(texte.encode()).hexdigest() if len(texte) >= TEXTE_MINIMUM else None

    empreinte_visuelle = None
    if empreinte_texte is None:
        # PDF scanné : on compare le rendu de la première page.
        try:
            import pypdfium2 as pdfium

            doc = pdfium.PdfDocument(contenu)
            image = doc[0].render(scale=1.5).to_pil()
            empreinte_visuelle = signature_visuelle(image)
            doc.close()
        except Exception:
            empreinte_visuelle = None
    return pages, empreinte_texte, empreinte_visuelle


def _analyser_image(contenu):
    try:
        with Image.open(io.BytesIO(contenu)) as img:
            img.verify()
        image = Image.open(io.BytesIO(contenu))
        image.load()
    except Exception:
        raise DepotRefuse("Cette image est illisible ou endommagée.")
    if min(image.size) < COTE_MIN_IMAGE:
        raise DepotRefuse("Image trop petite pour être lisible. Prends la photo de plus près ou en meilleure qualité.")
    return image


def _nettoyer_image(image, type_fichier):
    """Ré-encode l'image sans métadonnées (supprime notamment la position GPS du téléphone)."""
    image = ImageOps.exif_transpose(image)
    sortie = io.BytesIO()
    if type_fichier == "png":
        image.save(sortie, format="PNG", optimize=True)
    else:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(sortie, format="JPEG", quality=88, optimize=True)
    return sortie.getvalue()


def analyser_fichier(upload):
    nom = (upload.name or "").lower()
    ext = nom.rsplit(".", 1)[-1] if "." in nom else ""
    if ext not in EXTENSIONS:
        raise DepotRefuse("Format non accepté. Envoie un PDF ou une photo (JPG, PNG, WEBP).")
    taille_max = settings.DEPOT_TAILLE_MAX_MO * 1024 * 1024
    if upload.size > taille_max:
        raise DepotRefuse(f"Fichier trop lourd : {settings.DEPOT_TAILLE_MAX_MO} Mo au maximum.")

    contenu = upload.read()
    upload.seek(0)
    analyse = Analyse(contenu=contenu, type_fichier=EXTENSIONS[ext])
    analyse.empreinte_fichier = hashlib.sha256(contenu).hexdigest()

    if analyse.type_fichier == "pdf":
        if not contenu.startswith(b"%PDF"):
            raise DepotRefuse("Ce fichier n'est pas un vrai PDF.")
        analyse.nombre_pages, analyse.empreinte_texte, analyse.empreinte_visuelle = _analyser_pdf(contenu)
    else:
        image = _analyser_image(contenu)
        reel = (image.format or "").lower()
        if reel not in ("jpeg", "png", "webp"):
            raise DepotRefuse("Le contenu de l'image ne correspond pas à son extension.")
        analyse.empreinte_visuelle = signature_visuelle(image)
        analyse.type_fichier = "png" if reel == "png" else "jpeg"
        analyse.contenu = _nettoyer_image(image, analyse.type_fichier)
    return analyse


# ---------------------------------------------------------------------------
# Détection des doublons
# ---------------------------------------------------------------------------
MESSAGE_DOUBLON = "Cette épreuve est déjà dans notre base : elle ne peut pas être envoyée une deuxième fois."


def message_doublon(raison):
    return f"Cette épreuve est déjà dans notre base ({raison}) : elle ne peut pas être envoyée une deuxième fois."


def chercher_doublon(analyse, cle):
    existantes = EpreuveSoumise.objects.all()
    if EpreuveSoumise.objects.filter(empreinte_fichier=analyse.empreinte_fichier).exists():
        return message_doublon("fichier identique")
    if analyse.empreinte_texte and existantes.filter(empreinte_texte=analyse.empreinte_texte).exists():
        return message_doublon("même contenu")
    if cle and existantes.filter(cle_epreuve=cle).exists():
        return ("Une épreuve de cet établissement, pour cette classe, cette matière, "
                "cette évaluation et cette année a déjà été envoyée.")
    if analyse.empreinte_visuelle:
        candidates = existantes.exclude(empreinte_visuelle__isnull=True).values_list("empreinte_visuelle", "type_fichier", "nombre_pages")
        for empreinte, type_fichier, pages in candidates.iterator():
            if similarite(empreinte, analyse.empreinte_visuelle) >= SIMILARITE_MIN:
                # Pour deux PDF scannés, on exige aussi le même nombre de pages.
                if analyse.type_fichier == "pdf" and type_fichier == "pdf" and pages != analyse.nombre_pages:
                    continue
                return message_doublon("image identique")
    return None


# ---------------------------------------------------------------------------
# Enregistrement + crédit
# ---------------------------------------------------------------------------
def enregistrer_epreuve(eleve, donnees, upload, adresse_ip=None):
    """Analyse, vérifie l'unicité, enregistre l'épreuve et crédite le solde.

    Tout se passe dans une transaction : si une étape échoue, rien n'est
    enregistré et le solde n'est pas modifié. Les contraintes UNIQUE de la base
    garantissent qu'un double envoi simultané ne peut pas passer.
    """
    debut_jour = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    if EpreuveSoumise.objects.filter(eleve=eleve, date_envoi__gte=debut_jour).count() >= settings.DEPOT_LIMITE_PAR_JOUR:
        raise DepotRefuse(f"Tu as atteint la limite de {settings.DEPOT_LIMITE_PAR_JOUR} envois aujourd'hui. Reviens demain !")

    analyse = analyser_fichier(upload)
    cle = cle_epreuve(
        donnees["etablissement"], donnees["niveau"].pk, donnees["matiere"].pk,
        donnees["type_evaluation"], donnees["annee_scolaire"],
    )
    message = chercher_doublon(analyse, cle)
    if message:
        raise DepotRefuse(message, doublon=True)

    recompense = settings.DEPOT_RECOMPENSE_FCFA
    extension = "pdf" if analyse.type_fichier == "pdf" else ("png" if analyse.type_fichier == "png" else "jpg")
    try:
        with transaction.atomic():
            epreuve = EpreuveSoumise(
                eleve=eleve,
                titre=donnees["titre"],
                niveau=donnees["niveau"],
                matiere=donnees["matiere"],
                etablissement=donnees["etablissement"],
                type_evaluation=donnees["type_evaluation"],
                annee_scolaire=donnees["annee_scolaire"],
                nom_original=(upload.name or "")[:255],
                type_fichier=analyse.type_fichier,
                taille=len(analyse.contenu),
                nombre_pages=analyse.nombre_pages,
                empreinte_fichier=analyse.empreinte_fichier,
                empreinte_texte=analyse.empreinte_texte,
                empreinte_visuelle=analyse.empreinte_visuelle,
                cle_epreuve=cle,
                recompense=recompense,
                adresse_ip=adresse_ip,
            )
            epreuve.fichier.save(f"epreuve.{extension}", ContentFile(analyse.contenu), save=False)
            epreuve.save()

            # Publication immédiate dans la banque « Anciennes épreuves » de la classe.
            if getattr(settings, "DEPOT_PUBLICATION_AUTO", True):
                publier_epreuve(epreuve, analyse.contenu)

            UserRegistration.objects.filter(pk=eleve.pk).update(somme=F("somme") + recompense)
            solde = UserRegistration.objects.values_list("somme", flat=True).get(pk=eleve.pk)
            MouvementSolde.objects.create(
                eleve=eleve, epreuve=epreuve, montant=recompense, solde_apres=solde,
                motif=f"Épreuve envoyée : {epreuve.titre[:150]}",
            )
    except IntegrityError:
        # Un autre envoi identique vient d'être enregistré à la même seconde.
        raise DepotRefuse(MESSAGE_DOUBLON, doublon=True)

    eleve.somme = solde
    return epreuve


# ---------------------------------------------------------------------------
# Publication dans la banque d'épreuves
# ---------------------------------------------------------------------------
def trouver_ou_creer_ecole(nom):
    """Retrouve l'établissement même s'il est écrit autrement
    (« Lycée bilingue de Deïdo » = « LYCEE BILINGUE DEIDO »)."""
    cle = normaliser_etablissement(nom)
    for ecole in Ecole.objects.only("id", "nom").iterator():
        if normaliser_etablissement(ecole.nom) == cle:
            return ecole
    ecole, _ = Ecole.objects.get_or_create(nom=nom[:200])
    return ecole


def en_pdf(contenu, type_fichier):
    """La banque d'épreuves n'accepte que des PDF : une photo est convertie en PDF A4."""
    if type_fichier == "pdf":
        return contenu
    image = Image.open(io.BytesIO(contenu))
    if image.mode != "RGB":
        image = image.convert("RGB")
    sortie = io.BytesIO()
    image.save(sortie, format="PDF", resolution=150)
    return sortie.getvalue()


def publier_epreuve(epreuve, contenu=None):
    """Crée la fiche « Ancienne épreuve » visible par les abonnés de la classe."""
    if epreuve.publication_id or epreuve.statut == EpreuveSoumise.Statut.REJETEE:
        return epreuve.publication
    if contenu is None:
        with epreuve.fichier.open("rb") as f:
            contenu = f.read()
    annee_fin = int(epreuve.annee_scolaire.split("-")[-1]) if epreuve.annee_scolaire[-4:].isdigit() else None
    publication = AncienEpreuve(
        titre=epreuve.titre,
        description=(
            f"{epreuve.matiere.nom} — {epreuve.get_type_evaluation_display()} — année scolaire "
            f"{epreuve.annee_scolaire}. Épreuve partagée par un élève d'EasySchool."
        ),
        niveau=epreuve.niveau,
        matiere=epreuve.matiere,
        ecole=trouver_ou_creer_ecole(epreuve.etablissement),
        annee=annee_fin,
    )
    publication.fichier.save("epreuve.pdf", ContentFile(en_pdf(contenu, epreuve.type_fichier)), save=False)
    publication.save()
    epreuve.publication = publication
    epreuve.save(update_fields=["publication"])
    return publication


def retirer_publication(epreuve):
    """Retire l'épreuve de la banque (la fiche et son fichier)."""
    publication = epreuve.publication
    if publication is None:
        return
    fichier = publication.fichier
    epreuve.publication = None
    epreuve.save(update_fields=["publication"])
    publication.delete()
    if fichier:
        transaction.on_commit(lambda: fichier.storage.delete(fichier.name))


def rejeter_epreuve(epreuve, motif=""):
    """Rejet par un administrateur : l'épreuve est retirée de la banque et la récompense reprise."""
    with transaction.atomic():
        epreuve = EpreuveSoumise.objects.select_for_update().get(pk=epreuve.pk)
        if epreuve.statut == EpreuveSoumise.Statut.REJETEE:
            return epreuve
        epreuve.statut = EpreuveSoumise.Statut.REJETEE
        epreuve.motif_rejet = motif[:300]
        epreuve.date_traitement = timezone.now()
        # Libère la place : une version correcte de la même épreuve pourra être
        # renvoyée. Le fichier et le texte rejetés restent, eux, bloqués.
        epreuve.cle_epreuve = None
        epreuve.empreinte_visuelle = None
        epreuve.save(update_fields=["statut", "motif_rejet", "date_traitement", "cle_epreuve", "empreinte_visuelle"])
        retirer_publication(epreuve)
        if epreuve.recompense:
            UserRegistration.objects.filter(pk=epreuve.eleve_id).update(somme=F("somme") - epreuve.recompense)
            solde = UserRegistration.objects.values_list("somme", flat=True).get(pk=epreuve.eleve_id)
            MouvementSolde.objects.create(
                eleve_id=epreuve.eleve_id, epreuve=epreuve, montant=-epreuve.recompense, solde_apres=solde,
                motif=f"Épreuve rejetée : {motif[:150] or 'non conforme'}",
            )
    return epreuve


def valider_epreuve(epreuve):
    EpreuveSoumise.objects.filter(pk=epreuve.pk, statut=EpreuveSoumise.Statut.RECUE).update(
        statut=EpreuveSoumise.Statut.VALIDEE, date_traitement=timezone.now()
    )
