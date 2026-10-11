from django.core.files.storage import FileSystemStorage, storages
from django.core.signals import setting_changed
from django.utils.functional import LazyObject, empty


class StockagePrive(FileSystemStorage):
    """Stockage local sans adresse web : `.url()` ne renvoie jamais de lien public.
    Les fichiers ne sont lisibles qu'à travers les vues qui vérifient les droits."""

    def url(self, name):
        return ""


class _StockagePriveParesseux(LazyObject):
    """Résout le stockage « private » au moment de l'utilisation (et non à l'import),
    pour suivre les changements de réglages (tests, configuration S3)."""

    def _setup(self):
        self._wrapped = storages["private"]


_stockage_prive = _StockagePriveParesseux()


def _reinitialiser(*, setting, **kwargs):
    if setting == "STORAGES":
        _stockage_prive._wrapped = empty


setting_changed.connect(_reinitialiser)


def private_storage():
    """Stockage des fichiers payants ou sensibles : jamais d'URL publique."""
    return _stockage_prive
