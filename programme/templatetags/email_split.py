
from django import template


register = template.Library()

@register.filter
def email_split(email):
    return email.split('@')[0]