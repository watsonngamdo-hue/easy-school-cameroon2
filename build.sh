#!/usr/bin/env bash
# Script de construction utilisé par Render (et utilisable sur tout serveur).
set -o errexit
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py configurer_site
# Démonstration : uniquement si DEMO_ADMIN_EMAIL / DEMO_ADMIN_PASSWORD sont définis.
# (doit passer avant completer_programme : le contenu de démonstration est chargé dans une base vide)
if [ -n "$DEMO_ADMIN_EMAIL" ]; then python manage.py init_demo; fi
python manage.py completer_programme
python manage.py proteger_fichiers
if [ -n "$DEMO_ADMIN_EMAIL" ]; then python manage.py demo_professeur; fi
