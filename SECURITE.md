# Audit de sécurité — EasySchool Cameroun

Audit réalisé le 11 octobre 2026 sur l'archive `easyschoolcameroun-main`.
Toutes les failles listées ci-dessous sont corrigées dans cette version, et 56 tests automatiques
(`python manage.py test`) vérifient les correctifs principaux et le module de dépôt.

## À faire immédiatement de ton côté

Certaines fuites ne se corrigent pas seulement dans le code : les secrets sont déjà publics.

1. **Révoquer la clé CloudFront** `KPEC6QXOXJI4B` (console AWS > CloudFront > Public keys) et en créer une nouvelle.
   Sa clé privée RSA était écrite en clair dans `settings.py`.
2. **Révoquer la clé Gemini** `AIzaSyD9…ffg` (Google AI Studio) : elle était la valeur par défaut dans `settings.py`.
3. **Changer `SECRET_KEY`** en production (cela déconnecte tout le monde, c'est voulu).
4. **Changer les mots de passe** des comptes présents dans l'ancien `db.sqlite3` (11 comptes, dont les administrateurs).
5. **Purger l'historique Git** : supprimer un fichier ne l'efface pas des anciens commits.
   `git filter-repo --path db.sqlite3 --path Elearning/settings.py --path sent_emails --invert-paths` (puis ré-ajouter le nouveau `settings.py`), ou rendre le dépôt privé et en recréer un propre.

## Failles trouvées et corrigées

| # | Gravité | Faille | Correctif |
|---|---|---|---|
| 1 | Critique | Clé privée RSA CloudFront écrite en dur dans `settings.py` | Lue depuis l'environnement (`AWS_CLOUDFRONT_KEY`) |
| 2 | Critique | Clé API Gemini en valeur par défaut dans `settings.py` | Aucune valeur par défaut |
| 3 | Critique | Achat de crédits IA : un montant **négatif** ajoutait de l'argent au solde (`amount=-100000` → +1 000 000 FCFA) | Seuls les packs définis par l'admin sont achetables, transaction verrouillée |
| 4 | Critique | `db.sqlite3` versionné : 11 comptes (e-mails, téléphones, empreintes de mots de passe), 34 sessions, 46 messages privés ; dossier `sent_emails/` avec des e-mails d'élèves | Fichiers supprimés, ajoutés au `.gitignore` |
| 5 | Élevée | XSS stocké : commentaires de leçon affichés avec `|safe` (texte brut), forums (HTML libre envoyé en POST), réponses de l'IA (`marked` sans nettoyage) → vol de session, y compris d'un administrateur | Nettoyage serveur avec `nh3` (filtre `|sanitize`), échappement des commentaires, `DOMPurify` côté IA |
| 6 | Élevée | Contrôle d'accès des leçons : un abonnement à un niveau donnait accès aux leçons de **tous** les niveaux (le slug de la leçon n'était pas vérifié) | La leçon doit appartenir au niveau et à la matière de l'URL |
| 7 | Élevée | `ALLOWED_HOSTS = ['*']` : empoisonnement de l'en-tête Host (liens de réinitialisation de mot de passe pointant vers un site pirate) | Liste explicite, configurable |
| 8 | Élevée | Protection CSRF désactivée (`csrf_exempt`) sur l'assistant IA et la création de PDF : un site tiers pouvait dépenser les crédits d'un élève connecté | `csrf_exempt` retiré (le front envoyait déjà le jeton) |
| 9 | Élevée | Envois de fichiers non contrôlés (assistant IA : n'importe quel type et taille ; un `.html` déposé s'exécutait sur le domaine) | Liste blanche + taille max + vérification de la signature binaire ; médias servis en « bac à sable » (CSP `sandbox`) |
| 10 | Élevée | Clés API IA réaffichées en clair dans le tableau de bord staff et écrites dans `.env` par l'application web | Clés masquées, jamais réécrites dans `.env` |
| 11 | Élevée | `docker-compose` : gunicorn exposé directement sur Internet (port 8000), et le service `web` ne recevait pas le `.env` | Port lié à `127.0.0.1`, `env_file` ajouté |
| 12 | Moyenne | Conditions de course sur le solde (paiement d'abonnement, achat de crédits, débit IA) : deux requêtes simultanées dépensaient le même argent | `select_for_update` dans des transactions |
| 13 | Moyenne | Bonus de bienvenue (1 000 F + 500 crédits) cumulable en confirmant plusieurs adresses e-mail | Champ `bonus_bienvenue_recu`, versé une seule fois |
| 14 | Moyenne | Quiz : score falsifiable (questions d'autres quiz acceptées, score > 100 %) | Seules les questions du quiz comptent, score borné |
| 15 | Moyenne | Messagerie privée : « répondre à » un message d'une autre conversation affichait son texte | Réponse limitée aux conversations de l'utilisateur, 20 destinataires max |
| 16 | Moyenne | Déconnexion par lien GET et confirmation d'e-mail par GET (déclenchables par une image piégée ou un antivirus) | POST obligatoire |
| 17 | Moyenne | Page `/pay` accessible sans connexion (erreur 500) et nombreuses erreurs 500 sur des URL invalides (`.get()` sans 404) | `login_required`, `get_object_or_404` partout |
| 18 | Moyenne | Pas de limitation de débit : contact, newsletter, déclarations de dépôt | Limiteur par IP/utilisateur, limites allauth (`ACCOUNT_RATE_LIMITS`) |
| 19 | Moyenne | Modèle d'IA inconnu facturé 10 crédits quel que soit son coût réel | Seuls les modèles actifs configurés sont acceptés |
| 20 | Moyenne | Erreurs internes renvoyées à l'utilisateur (`str(e)`), `DEBUG_PROPAGATE_EXCEPTIONS`, messages des élèves journalisés en DEBUG dans `debug.log` | Messages génériques, journalisation console niveau INFO |
| 21 | Moyenne | En-têtes de sécurité absents ou incomplets | HSTS, CSP (`frame-ancestors`, `form-action`, `object-src`), `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, COOP |
| 22 | Moyenne | Dépendances obsolètes avec failles connues (Django 4.2 en fin de support depuis avril 2026, gunicorn 20.1, Pillow 9.1, requests 2.28, urllib3 1.26.9, cryptography 37…) | Django 5.2 LTS et dépendances à jour, versions figées |
| 23 | Faible | Le site restait bloqué sur un écran de chargement si le CDN jQuery ne répondait pas ; Google Analytics « UA » (arrêté) | Site public sans jQuery ni CDN (polices et icônes hébergées localement) |

## Point restant à surveiller

- **CKEditor 4** (via `django-ckeditor`) n'est plus maintenu. Ses failles XSS sont neutralisées par le
  nettoyage côté serveur, mais il faudra migrer vers `django-ckeditor-5` à terme.
- La liste des destinataires de la messagerie privée montre les noms de tous les élèves : c'est un choix
  fonctionnel, à restreindre aux élèves d'une même classe si tu le souhaites.

## Ajouts après l'audit

- **Contenus payants** : déplacés hors des médias publics, servis uniquement après vérification de l'abonnement,
  filigranés au nom de l'élève, journalisés, avec une limite de 2 appareils connectés par compte.
- **Pièces d'identité des professeurs** : données personnelles sensibles, stockées en privé et visibles du staff
  seulement. Pense à les supprimer une fois la vérification faite si tu n'as pas d'obligation de les conserver
  (loi camerounaise de 2024 sur la protection des données personnelles).
- **Envois des professeurs** : vidéos et PDF contrôlés (extension, taille, signature binaire) ; les textes des
  professeurs sont affichés échappés (aucun HTML).
