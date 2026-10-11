# EasySchool Cameroun

Plateforme d'apprentissage en ligne pour le secondaire camerounais : cours, exercices, quiz, forums,
assistant IA, anciennes épreuves, et **dépôt d'épreuves par les élèves** (25 FCFA par épreuve nouvelle).

- Rapport d'audit et correctifs : [SECURITE.md](SECURITE.md)
- Python 3.12+, Django 5.2 LTS

## Lancer en local (5 minutes)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
echo "DEBUG=True" > .env
echo "ACCOUNT_EMAIL_VERIFICATION=optional" >> .env
python manage.py migrate
DEMO_ADMIN_EMAIL=admin@demo.cm DEMO_ADMIN_PASSWORD=ChangeMoi-2026 \
DEMO_ELEVE_EMAIL=eleve@demo.cm DEMO_ELEVE_PASSWORD=ChangeMoi-2026 python manage.py init_demo
python manage.py runserver
```

Sans Redis, les tâches Celery s'exécutent directement ; sans clé Brevo, les e-mails s'affichent dans le terminal.

## Mise en ligne

### Option A — Render (gratuit, pour une démo)

1. Pousse ce dossier sur un dépôt GitHub **privé**.
2. Sur [render.com](https://render.com) : **New > Blueprint**, choisis le dépôt. `render.yaml` crée la base
   PostgreSQL et le site ; `build.sh` installe, migre, configure le domaine, complète les classes,
   protège les fichiers et charge la démonstration.
3. Renseigne quand Render les demande : `DEMO_ADMIN_EMAIL`, `DEMO_ADMIN_PASSWORD`, `DEMO_ELEVE_EMAIL`,
   `DEMO_ELEVE_PASSWORD` (laisse-les vides en production réelle), puis plus tard `BREVO_API_KEY`, `GEMINI_API_KEY`…
4. Le site répond sur `https://easyschool-xxxx.onrender.com`. L'administration Django est à l'adresse
   `/<ADMIN_URL>/` (valeur générée au hasard, visible dans Render > Environment).

Limites de l'offre gratuite : mise en veille après 15 min sans visite, base gratuite supprimée après 30 jours,
fichiers envoyés (épreuves, vidéos, pièces d'identité) effacés à chaque redéploiement. Pour garder les fichiers,
renseigne `AWS_STORAGE_BUCKET_NAME` + clés (S3, Cloudflare R2, Wasabi…).

### Option B — ton serveur (production)

1. `cp .env.example .env` et remplis au minimum `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
   `ADMIN_URL`, `POSTGRES_*`, `EMAIL_HOST_USER`, `BREVO_API_KEY`, et le stockage S3.
2. `docker compose up -d --build` (migrations, configuration du site, classes et protection des fichiers
   sont lancées automatiquement au démarrage).
3. Installe `nginx/easyschool.conf` (HTTPS Let's Encrypt, envois de vidéos jusqu'à 350 Mo, médias en bac à sable).
4. Crée ton compte administrateur : `docker compose exec web python manage.py createsuperuser`.

### Après chaque mise à jour du code

`python manage.py migrate && python manage.py completer_programme && python manage.py proteger_fichiers`
(déjà fait par `build.sh` et `docker-compose.yml`).

## Module « Dépôt d'épreuves » (`depot/`)

- Adresse : `/depot/` (liens dans le menu du site, la page d'accueil et l'espace élève).
- Formats : PDF, JPG, PNG, WEBP — 10 Mo max, 40 pages max, 20 envois par élève et par jour.
- **Une épreuve ne peut être envoyée qu'une fois.** L'envoi est refusé si :
  1. le fichier est identique à un fichier déjà reçu (empreinte SHA-256) ;
  2. le texte du PDF, normalisé, est identique (fichier renommé ou ré-enregistré) ;
  3. l'image ou la page scannée est visuellement identique (recompressée, redimensionnée) ;
  4. une épreuve du même établissement, de la même classe, matière, évaluation et année existe déjà.
  Les contraintes `UNIQUE` de la base empêchent aussi deux envois simultanés.
- Si l'épreuve est acceptée, tout se fait dans une seule transaction :
  - l'original est enregistré en base et stocké hors des médias publics (`private_media/` ou dossier S3 privé) ;
  - **une copie PDF est publiée automatiquement** dans la banque « Anciennes épreuves » de la classe
    (avec la matière, l'établissement et l'année), visible tout de suite par les abonnés ; une photo est convertie en PDF ;
  - **+25 FCFA** sont ajoutés au solde (`somme`) et une ligne est écrite dans le journal `MouvementSolde`.
- Administration : *Épreuves soumises* > actions **Publier**, **Valider** ou **Rejeter**
  (le rejet retire l'épreuve de la banque et reprend les 25 F).
- Réglages : `DEPOT_RECOMPENSE_FCFA`, `DEPOT_TAILLE_MAX_MO`, `DEPOT_LIMITE_PAR_JOUR`,
  `DEPOT_PUBLICATION_AUTO` (`False` pour que chaque épreuve attende ta publication manuelle).

## Classes (6e à Terminale)

Les 7 classes du secondaire général (Sixième, Cinquième, Quatrième, Troisième, Seconde, Première,
Terminale) sont créées automatiquement avec leurs matières de base, sans toucher à l'existant :
migration `programme/0026` sur une base existante, `python manage.py completer_programme` à tout moment.
La liste est dans `programme/programme_officiel.py`.

## Assistant IA : réponses réutilisées

Toutes les questions et réponses sont enregistrées (`AIMessage`, avec le modèle utilisé). Quand une question
posée **en début de conversation et sans fichier** a déjà reçu une réponse avec le même modèle, la réponse
enregistrée (`ReponseEnCache`) est renvoyée **sans appel à l'API** ; l'élève est débité normalement.
La comparaison ignore majuscules, accents et espaces (« Qu'est-ce qu'une fonction affine ? » =
« qu'est-ce qu'une FONCTION affine? »). Les questions posées en cours de conversation ne sont pas
réutilisées, car leur réponse dépend de ce qui précède. Une réponse en erreur n'est jamais mise en
cache et l'élève est remboursé. Dans l'admin, *Réponses en cache* indique le nombre d'appels évités et
permet de désactiver une réponse à refaire.

## Protection des cours et des épreuves contre le partage

Impossible d'empêcher totalement une photo d'écran ; le site rend donc le partage difficile, traçable et risqué :

- **Plus aucune adresse publique** : PDF des leçons, exercices, anciennes épreuves, cours des professeurs et
  vidéos sont dans le stockage privé (`private_media/` ou dossier S3 privé). Chaque ouverture repasse par Django,
  qui vérifie l'abonnement à ce moment-là. Après la mise à jour : `python manage.py proteger_fichiers`
  (fait automatiquement par `build.sh`) déplace les anciens fichiers et coupe les anciens liens.
- **Filigrane nominatif** : chaque page de PDF porte le nom, l'e-mail et le téléphone de l'élève, et le fichier
  contient l'identifiant du compte. Une copie qui circule désigne le compte responsable.
- **Lecteur intégré** (pdf.js) sans bouton de téléchargement ; vidéos lues en continu, nom de l'élève qui se déplace sur l'image.
- **Journal des ouvertures** (*Accès aux documents* dans l'admin) et limite de 120 ouvertures par heure.
- **2 appareils connectés maximum par compte** : se connecter sur un 3e appareil déconnecte le plus ancien,
  ce qui décourage le prêt d'identifiants (`MAX_APPAREILS_PAR_COMPTE`).

## Espace professeurs (`/profs/`)

- **Inscription** : un utilisateur connecté remplit son profil (chaîne, classes, prix mensuel de 500 à 20 000 F,
  numéro Mobile Money) et envoie 4 pièces : CNI recto/verso, selfie avec la CNI, diplôme ou attestation.
  Les pièces sont stockées en privé ; seul le staff les ouvre depuis l'admin (*Professeurs*).
- **Vérification** : dans l'admin, actions **Vérifier**, **Refuser**, **Suspendre**. Tant que l'identité n'est pas
  vérifiée, les cours restent invisibles.
- **Studio** : le professeur crée ses cours et ajoute des leçons vidéo (MP4/WEBM, 300 Mo max) ou PDF ; il peut marquer
  une leçon en « aperçu gratuit ».
- **Abonnement** : l'élève paie le prix mensuel avec son solde EasySchool (30 jours, prolongeable, sans renouvellement
  automatique). **70 %** vont au professeur, **30 %** à EasySchool (`PROF_COMMISSION_PLATEFORME`).
- **Retraits** : les gains deviennent retirables après 7 jours (`PROF_DELAI_DISPONIBILITE_JOURS`) ; le professeur demande
  un retrait (5 000 F minimum) vers son numéro ; dans l'admin, *Demandes de retrait* : saisir la référence Mobile Money
  puis **Marquer comme payée**, ou **Refuser** (le montant est recrédité). Les soldes sont calculés à partir d'un journal
  (`MouvementProf`), jamais modifiés à la main.
- **Modération** : un cours signalé se retire avec la case *Bloqué par l'admin*.
- Pour les vidéos, un stockage S3 (ou compatible) est indispensable en production : le disque de Render gratuit
  est effacé à chaque redéploiement, et nginx doit accepter les gros envois (`nginx/easyschool.conf` le prévoit).

## Tests

```bash
python manage.py test
```
