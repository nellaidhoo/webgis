"""
Email notification utilities for WebGIS platform.
"""
import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


def notify_registration_pending(user):
    """Notify admin that a new registration request is pending."""
    subject = f"New Registration Request: {user.username}"
    message = (
        f"A new user has registered and is awaiting approval.\n\n"
        f"Username: {user.username}\n"
        f"Email: {user.email or 'not provided'}\n"
        f"Name: {user.get_full_name() or 'not provided'}\n\n"
        f"Approve or reject at: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/admin/gis_app/userregistrationrequest/\n"
    )
    try:
        send_mail(
            subject, message,
            settings.DEFAULT_FROM_EMAIL,
            [settings.ADMIN_EMAIL],
            fail_silently=True,
        )
    except Exception as e:
        logger.warning(f"Failed to send registration pending email: {e}")


def notify_registration_approved(user):
    """Notify user that their registration has been approved."""
    subject = "Your WebGIS Account Has Been Approved"
    message = (
        f"Dear {user.get_full_name() or user.username},\n\n"
        f"Your registration request has been approved. You can now log in to the WebGIS platform.\n\n"
        f"Login: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}\n\n"
        f"If you have any questions, please contact your administrator.\n\n"
        f"Best regards,\nWebGIS Team"
    )
    if user.email:
        try:
            send_mail(
                subject, message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send approval email to {user.username}: {e}")


def notify_registration_rejected(user, reason=""):
    """Notify user that their registration has been rejected."""
    subject = "Your WebGIS Account Registration"
    reason_text = f"\n\nReason: {reason}" if reason else ""
    message = (
        f"Dear {user.get_full_name() or user.username},\n\n"
        f"Your registration request could not be approved at this time.{reason_text}\n\n"
        f"If you believe this is an error, please contact your administrator.\n\n"
        f"Best regards,\nWebGIS Team"
    )
    if user.email:
        try:
            send_mail(
                subject, message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send rejection email to {user.username}: {e}")
