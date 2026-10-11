from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

@shared_task
def notify_admin_quota_exhausted(model_name, provider):
    """
    Sends an email to administrators when an AI API quota is exhausted.
    Uses a cache-based throttle to prevent spamming.
    """
    cache_key = f"quota_notification_sent_{provider}_{model_name}"
    if cache.get(cache_key):
        logger.info(f"Notification for {provider} {model_name} already sent recently. Skipping.")
        return "Notification already sent recently"

    User = get_user_model()
    from django.db.models import Q
    admin_emails = list(User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).values_list('email', flat=True))
    admin_emails = list(set(admin_emails)) # Ensure unique emails
    
    if not admin_emails:
        logger.warning("No administrator emails found for quota notification.")
        return "No admin emails found"

    subject = f"IMPORTANT : Quota API Épuisé - {provider.upper()} ({model_name})"
    from_email = settings.DEFAULT_FROM_EMAIL
    
    context = {
        'model_name': model_name,
        'provider': provider.upper(),
        'base_url': settings.BASE_URL,
    }

    html_content = render_to_string('emails/ai_quota_exhausted.html', context)
    text_content = strip_tags(html_content)

    try:
        msg = EmailMultiAlternatives(subject, text_content, from_email, admin_emails)
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        
        # Set cache to throttle notifications for 1 hour
        cache.set(cache_key, True, 3600)
        
        logger.info(f"Quota notification sent to {len(admin_emails)} admins for {provider} {model_name}")
        return f"Email sent to {len(admin_emails)} admins"
    except Exception as e:
        logger.error(f"Failed to send quota notification email: {str(e)}")
        return f"Error sending email: {str(e)}"
