from django import template
from django.utils.safestring import mark_safe

from Elearning.sanitize import clean_html

register = template.Library()


@register.filter(name="sanitize")
def sanitize(value):
    """À utiliser à la place de |safe pour tout contenu saisi par un utilisateur."""
    return mark_safe(clean_html(value))
