from .models import ReseauxSociaux
from django.db import ProgrammingError, OperationalError

def social_links(request):
    """
    Context processor that provides social media links to all templates.
    """
    try:
        links = ReseauxSociaux.objects.first()
    except (ProgrammingError, OperationalError):
        links = None
    return {'social_links': links}
