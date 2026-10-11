"""Classes et matières du secondaire général camerounais (sous-système francophone).

`completer_programme` ajoute ce qui manque sans jamais modifier ni supprimer
l'existant. Elle reçoit les classes de modèles en paramètre pour pouvoir être
appelée depuis une migration (modèles historiques) comme depuis le code.
"""
import re
import unicodedata

from django.utils.text import slugify

# (nom enregistré, ordre, variantes reconnues)
CLASSES = [
    ("SIXIEME", 1, {"sixieme", "6e", "6eme", "6 eme"}),
    ("CINQUIEME", 2, {"cinquieme", "5e", "5eme", "5 eme"}),
    ("QUATRIEME", 3, {"quatrieme", "4e", "4eme", "4 eme"}),
    ("TROISIEME", 4, {"troisieme", "3e", "3eme", "3 eme"}),
    ("SECONDE", 5, {"seconde", "2nde", "2de", "2nd"}),
    ("PREMIERE", 6, {"premiere", "1ere", "1re"}),
    ("TERMINALE", 7, {"terminale", "tle", "tale"}),
]

PREMIER_CYCLE = [
    "Mathématiques", "Français", "Anglais", "Histoire-Géographie", "Éducation à la citoyenneté",
    "Sciences de la Vie et de la Terre", "Physique-Chimie-Technologie", "Informatique",
]
LANGUES = ["Espagnol", "Allemand"]  # deuxième langue vivante, à partir de la 4e
SECOND_CYCLE = [
    "Mathématiques", "Français", "Anglais", "Histoire-Géographie", "Physique-Chimie",
    "Sciences de la Vie et de la Terre", "Informatique", "Espagnol", "Allemand",
]

MATIERES = {
    "SIXIEME": PREMIER_CYCLE,
    "CINQUIEME": PREMIER_CYCLE,
    "QUATRIEME": PREMIER_CYCLE + LANGUES,
    "TROISIEME": PREMIER_CYCLE + LANGUES,
    "SECONDE": SECOND_CYCLE,
    "PREMIERE": SECOND_CYCLE + ["Philosophie"],
    "TERMINALE": SECOND_CYCLE + ["Philosophie"],
}


def _norm(texte):
    texte = unicodedata.normalize("NFKD", texte or "")
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    texte = re.sub(r"\(.*?\)", " ", texte)          # retire « (TERMINALE) »
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def _cle_matiere(nom):
    """Clé de rapprochement : « Mathematique » = « Mathématiques (TERMINALE) »,
    « Physique-Chimie » = « Physique-Chimie-Technologie »."""
    n = _norm(nom)
    if n.startswith("math"):
        return "maths"
    if n.startswith("physique") or n.startswith("sciences physiques") or n == "pct":
        return "physique"
    if n.startswith("sciences de la vie") or n == "svt":
        return "svt"
    if n.startswith("histoire") or n.startswith("geographie"):
        return "hg"
    if n.startswith("education a la citoyennete") or n == "ecm":
        return "ecm"
    if n.startswith("informatique") or n == "tic":
        return "info"
    return n.rstrip("s")


def ordre_classe(nom):
    n = _norm(nom)
    for _, ordre, variantes in CLASSES:
        if n in variantes:
            return ordre
    return 99


def completer_programme(Niveaux, Matiere):
    """Crée les classes de la 6e à la Terminale et leurs matières de base manquantes.
    Retourne (classes créées, matières créées)."""
    classes_creees = matieres_creees = 0
    existantes = list(Niveaux.objects.all())
    par_ordre = {}
    for niveau in existantes:
        ordre = ordre_classe(niveau.niveau)
        if niveau.ordre != ordre:
            niveau.ordre = ordre
            niveau.save(update_fields=["ordre"])
        par_ordre.setdefault(ordre, niveau)

    for nom, ordre, _ in CLASSES:
        if ordre in par_ordre:
            continue
        par_ordre[ordre] = Niveaux.objects.create(
            niveau=nom, slug=slugify(nom), ordre=ordre,
            description=f"Cours, exercices et épreuves de {nom.lower().replace('ieme', 'ième').replace('premiere', 'première')}.",
        )
        classes_creees += 1

    for nom_classe, ordre, _ in CLASSES:
        niveau = par_ordre[ordre]
        presentes = {_cle_matiere(m.nom) for m in Matiere.objects.filter(niveau=niveau)}
        for matiere in MATIERES[nom_classe]:
            if _cle_matiere(matiere) in presentes:
                continue
            nom_complet = f"{matiere} ({niveau.niveau})"
            if Matiere.objects.filter(nom=nom_complet).exists():
                continue
            Matiere.objects.create(
                matiere_id=slugify(f"{niveau.niveau}-{matiere}")[:40],
                nom=nom_complet,
                slug=slugify(f"{nom_complet}/{niveau.niveau}"),
                niveau=niveau,
                description=f"<p>{matiere} — programme officiel de {niveau.niveau.lower()}.</p>",
            )
            presentes.add(_cle_matiere(matiere))
            matieres_creees += 1
    return classes_creees, matieres_creees


LIBELLES = {1: ("Sixième", "6e"), 2: ("Cinquième", "5e"), 3: ("Quatrième", "4e"), 4: ("Troisième", "3e"),
            5: ("Seconde", "2nde"), 6: ("Première", "1re"), 7: ("Terminale", "Tle")}
REPERES = {1: "Premier cycle", 2: "Premier cycle", 3: "Premier cycle", 4: "Premier cycle · examen : BEPC",
           5: "Second cycle", 6: "Second cycle · examen : Probatoire", 7: "Second cycle · examen : Baccalauréat"}
