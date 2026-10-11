from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import PaymentIssue, Contact

@shared_task
def send_admin_deposit_email(issue_id):
    User = get_user_model()
    try:
        issue = PaymentIssue.objects.get(id=issue_id)
    except PaymentIssue.DoesNotExist:
        return f"Issue {issue_id} not found"

    admin_emails = list(User.objects.filter(is_staff=True).values_list('email', flat=True))
    if not admin_emails:
        return "No admin emails found"

    subject = f"Nouveau Dépôt - {issue.user.first_name} {issue.user.last_name}"
    from_email = settings.DEFAULT_FROM_EMAIL
    
    # Use reverse to get the admin URL dynamically to point to the user registration
    from django.urls import reverse
    admin_path = reverse('admin:authapp_userregistration_change', args=[issue.user.id])
    admin_url = f"{settings.BASE_URL}{admin_path}"
    
    context = {
        'user_name': f"{issue.user.first_name} {issue.user.last_name}",
        'numero': issue.numero,
        'reference': issue.reference,
        'date_transaction': issue.date,
        'description': issue.description,
        'amount': f"{issue.montant:,} FCFA".replace(',', ' '),
        'admin_url': admin_url,
    }

    html_content = render_to_string('emails/admin_deposit_notification.html', context)
    text_content = strip_tags(html_content)

    msg = EmailMultiAlternatives(subject, text_content, from_email, admin_emails)
    msg.attach_alternative(html_content, "text/html")
    msg.send()

    return f"Email sent to {len(admin_emails)} admins for issue {issue_id}"

@shared_task
def send_admin_contact_email(contact_id):
    User = get_user_model()
    try:
        contact_obj = Contact.objects.get(id=contact_id)
    except Contact.DoesNotExist:
        return f"Contact message {contact_id} not found"

    admin_emails = list(User.objects.filter(is_staff=True).values_list('email', flat=True))
    if not admin_emails:
        return "No admin emails found"

    subject = f"Nouveau message de contact - {contact_obj.nom}: {contact_obj.sujet}"
    from_email = settings.DEFAULT_FROM_EMAIL
    
    context = {
        'nom': contact_obj.nom,
        'email': contact_obj.email,
        'sujet': contact_obj.sujet,
        'message': contact_obj.message,
    }

    html_content = render_to_string('emails/admin_contact_notification.html', context)
    text_content = strip_tags(html_content)

    msg = EmailMultiAlternatives(subject, text_content, from_email, admin_emails)
    msg.attach_alternative(html_content, "text/html")
    msg.send()

    return f"Contact notification email sent to {len(admin_emails)} admins"
