from collections import namedtuple
from datetime import datetime, time, timedelta
from functools import wraps
import hashlib
import logging
import re
import secrets

import requests

from email.mime.image import MIMEImage
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

logger = logging.getLogger(__name__)


from bookings.models import (
    AcademySettings,
    Booking,
    BookingCancellation,
    BookingEmailDeliveryAttempt,
    BookingEmailNotification,
    CoachingContent,
    GalleryImage,
    HomePageSettings,
    MembershipContent,
    Table,
    TournamentContent,
)
from bookings.audit import log_booking_status_change
from bookings.forms import (
    BookingCancellationLookupForm,
    CustomerBookingCancellationForm,
)


TimeSlot = namedtuple(
    "TimeSlot",
    ["value", "label"],
)


# =========================================================
# RSA MANAGER AUTHENTICATION
# =========================================================

RSA_MANAGER_GROUP = "RSA Manager"


def is_rsa_manager(user):
    """Return True for RSA managers and the academy owner/superuser."""

    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    return user.groups.filter(name=RSA_MANAGER_GROUP).exists()


def manager_required(view_func):
    """Protect Operations Center views without granting Django Admin access."""

    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect(
                f"{reverse('manager_login')}?next={request.get_full_path()}"
            )

        if not is_rsa_manager(request.user):
            messages.error(
                request,
                "This account is not authorised to access the RSA Operations Center.",
            )
            logout(request)
            return redirect("manager_login")

        return view_func(request, *args, **kwargs)

    return wrapped_view


def manager_login(request):
    """Dedicated RSA Manager login. This is separate from Django Admin."""

    if request.user.is_authenticated and is_rsa_manager(request.user):
        return redirect("admin_dashboard")

    next_url = request.GET.get("next") or request.POST.get("next") or ""

    if next_url and not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = ""

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not username or not password:
            return render(
                request,
                "manager_login.html",
                {
                    "error": "Please enter both username and password.",
                    "next": next_url,
                },
            )

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None and is_rsa_manager(user):
            login(request, user)
            return redirect(next_url or "admin_dashboard")

        return render(
            request,
            "manager_login.html",
            {
                "error": "Invalid manager credentials or this account is not configured for RSA Operations Center access.",
                "next": next_url,
                "username": username,
            },
        )

    return render(
        request,
        "manager_login.html",
        {
            "next": next_url,
        },
    )


def manager_logout(request):
    """Log the manager out of the RSA Operations Center."""

    if request.method != "POST":
        return redirect("admin_dashboard")

    logout(request)
    return redirect("manager_login")


# =========================================================
# EMAIL HELPERS
# =========================================================

def send_rsa_html_email(
    subject,
    recipient,
    plain_message,
    html_message,
    logo_path=None,
):
    """
    Send a Royal Snooker Academy transactional email.

    Delivery is selected with RSA_EMAIL_PROVIDER:
    - "brevo" uses Brevo's HTTPS transactional email API.
    - "smtp" keeps the existing Django SMTP delivery for local use.

    The existing RSA HTML/plain-text email content is preserved.
    """

    provider = getattr(
        settings,
        "RSA_EMAIL_PROVIDER",
        "smtp",
    ).strip().lower()

    if provider == "brevo":

        api_key = getattr(
            settings,
            "RSA_BREVO_API_KEY",
            "",
        ).strip()

        sender_email = getattr(
            settings,
            "RSA_BREVO_SENDER_EMAIL",
            "",
        ).strip()

        sender_name = getattr(
            settings,
            "RSA_BREVO_SENDER_NAME",
            "Royal Snooker Academy",
        ).strip()

        logo_url = getattr(
            settings,
            "RSA_EMAIL_LOGO_URL",
            "",
        ).strip()

        if not api_key:
            raise RuntimeError(
                "RSA_BREVO_API_KEY is not configured."
            )

        if not sender_email:
            raise RuntimeError(
                "RSA_BREVO_SENDER_EMAIL is not configured."
            )

        brevo_html_message = html_message

        if "cid:rsa-logo" in brevo_html_message:

            if not logo_url:
                raise RuntimeError(
                    "RSA_EMAIL_LOGO_URL is required for Brevo "
                    "because the RSA email contains an inline logo."
                )

            brevo_html_message = brevo_html_message.replace(
                'src="cid:rsa-logo"',
                f'src="{logo_url}"',
            )

        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json={
                "sender": {
                    "name": sender_name,
                    "email": sender_email,
                },
                "to": [
                    {
                        "email": recipient,
                    },
                ],
                "subject": subject,
                "htmlContent": brevo_html_message,
                "textContent": plain_message,
            },
            timeout=20,
        )

        response.raise_for_status()
        return

    if provider != "smtp":
        raise RuntimeError(
            "Unsupported RSA_EMAIL_PROVIDER. "
            "Use 'brevo' or 'smtp'."
        )

    email_connection = get_connection(
        fail_silently=False,
        timeout=20,
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=None,
        to=[recipient],
        connection=email_connection,
    )

    email.attach_alternative(
        html_message,
        "text/html",
    )

    if logo_path:

        logo_file = Path(logo_path)

        if logo_file.exists():

            with open(logo_file, "rb") as image_file:

                logo = MIMEImage(
                    image_file.read(),
                    _subtype="png",
                )

            logo.add_header(
                "Content-ID",
                "<rsa-logo>",
            )

            logo.add_header(
                "Content-Disposition",
                "inline",
                filename="rsa-logo.png",
            )

            email.attach(logo)

    email.send(
        fail_silently=False
    )


def get_rsa_email_logo_path():
    return (
        Path(settings.BASE_DIR)
        / "static"
        / "images"
        / "royal_snooker_favicon_under_50kb.png"
    )


def _attempt_booking_email_delivery(notification, retry=False):
    now = timezone.now()
    eligible = Q(status=BookingEmailNotification.DeliveryStatus.PENDING)

    if retry:
        stale_before = now - timedelta(minutes=15)
        eligible |= Q(
            status=BookingEmailNotification.DeliveryStatus.FAILED
        ) | Q(
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            last_attempt_at__lte=stale_before,
        ) | Q(
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            last_attempt_at__isnull=True,
        )

    with transaction.atomic():
        claimed = BookingEmailNotification.objects.filter(
            pk=notification.pk,
        ).filter(
            eligible,
        ).update(
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            attempt_count=F("attempt_count") + 1,
            last_attempt_at=now,
            last_error="",
        )

        if not claimed:
            notification.refresh_from_db(fields=["status"])
            return notification.status == BookingEmailNotification.DeliveryStatus.SENT

        notification.refresh_from_db(fields=["attempt_count"])
        delivery_attempt = BookingEmailDeliveryAttempt.objects.create(
            notification=notification,
            attempt_number=notification.attempt_count,
            status=BookingEmailDeliveryAttempt.AttemptStatus.SENDING,
            started_at=now,
        )

    try:
        send_rsa_html_email(
            subject=notification.subject,
            recipient=notification.recipient_email,
            plain_message=notification.plain_message,
            html_message=notification.html_message,
            logo_path=get_rsa_email_logo_path(),
        )
    except Exception as error:
        completed_at = timezone.now()
        error_summary = (
            f"{type(error).__name__}. Check the application log for details."
        )
        with transaction.atomic():
            BookingEmailNotification.objects.filter(
                pk=notification.pk,
                status=BookingEmailNotification.DeliveryStatus.SENDING,
                last_attempt_at=now,
            ).update(
                status=BookingEmailNotification.DeliveryStatus.FAILED,
                last_error=error_summary,
            )
            BookingEmailDeliveryAttempt.objects.filter(
                pk=delivery_attempt.pk,
                status=BookingEmailDeliveryAttempt.AttemptStatus.SENDING,
            ).update(
                status=BookingEmailDeliveryAttempt.AttemptStatus.FAILED,
                completed_at=completed_at,
                error_summary=error_summary,
            )
        logger.exception(
            "Booking %s email delivery failed for %s",
            notification.notification_type,
            notification.booking.booking_reference,
        )
        return False

    completed_at = timezone.now()
    with transaction.atomic():
        BookingEmailNotification.objects.filter(
            pk=notification.pk,
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            last_attempt_at=now,
        ).update(
            status=BookingEmailNotification.DeliveryStatus.SENT,
            sent_at=completed_at,
            last_error="",
        )
        BookingEmailDeliveryAttempt.objects.filter(
            pk=delivery_attempt.pk,
            status=BookingEmailDeliveryAttempt.AttemptStatus.SENDING,
        ).update(
            status=BookingEmailDeliveryAttempt.AttemptStatus.SENT,
            completed_at=completed_at,
            error_summary="",
        )
    return True


def _send_tracked_booking_email(
    booking,
    notification_type,
    subject,
    plain_message,
    html_message,
):
    notification, _ = BookingEmailNotification.objects.get_or_create(
        booking=booking,
        notification_type=notification_type,
        defaults={
            "status": BookingEmailNotification.DeliveryStatus.PENDING,
            "recipient_email": booking.email,
            "subject": subject,
            "plain_message": plain_message,
            "html_message": html_message,
        },
    )
    return _attempt_booking_email_delivery(notification)


def retry_booking_email_notification(notification):
    """Retry a failed or stalled delivery using its saved message snapshot."""

    return _attempt_booking_email_delivery(notification, retry=True)


def build_booking_confirmation_html(
    booking,
    cancellation_request_url=None,
):
    """
    Build the polished HTML booking confirmation email.
    """

    duration_label = (
        f"{booking.duration_hours} hour"
        if booking.duration_hours == 1
        else f"{booking.duration_hours} hours"
    )

    amount = f"₹{booking.amount:,.2f}"
    customer_name = escape(booking.customer_name)
    booking_reference = escape(booking.booking_reference)
    table_name = escape(booking.table.name)
    table_type = escape(booking.table.table_type)
    cancellation_note = ""
    if cancellation_request_url:
        cancellation_note = (
            '<p style="margin:18px 0 0;padding:12px 14px;'
            'background:#EAF5F0;border-radius:8px;color:#36514A;'
            'font-size:12px;line-height:19px;">'
            'Need to cancel? <a href="'
            f'{escape(cancellation_request_url)}'
            '" style="color:#07513F;font-weight:700;">'
            'Request cancellation online</a> at least 2 hours before '
            'your session.</p>'
        )

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>Booking Confirmed - Royal Snooker Academy</title>
</head>

<body
    style="
        margin:0;
        padding:0;
        background-color:#F7F5EF;
        font-family:Arial,Helvetica,sans-serif;
        color:#1f2937;
    "
>

<table
    role="presentation"
    width="100%"
    cellspacing="0"
    cellpadding="0"
    border="0"
    style="background-color:#F7F5EF;"
>
    <tr>
        <td
            align="center"
            style="padding:32px 16px;"
        >

            <table
                role="presentation"
                width="100%"
                cellspacing="0"
                cellpadding="0"
                border="0"
                style="
                    max-width:620px;
                    background-color:#ffffff;
                    border:1px solid #D7E2DD;
                    border-top:4px solid #D4AF37;
                    border-radius:16px;
                    overflow:hidden;
                    box-shadow:0 4px 18px rgba(15,23,42,0.08);
                "
            >

                <!-- HEADER -->
                <tr>
                    <td
                        align="center"
                        style="
                            background-color:#07513F;
                            border-bottom:1px solid #D4AF37;
                            padding:18px 24px 16px;
                        "
                    >

                        <img
                            src="cid:rsa-logo"
                            width="84"
                            alt="Royal Snooker Academy"
                            style="
                                display:block;
                                width:84px;
                                max-width:84px;
                                height:auto;
                                margin:0 auto 8px;
                                border:0;
                                outline:none;
                                text-decoration:none;
                            "
                        >

                        <div
                            style="
                                color:#ffffff;
                                font-size:20px;
                                line-height:26px;
                                font-weight:800;
                                letter-spacing:0.3px;
                            "
                        >
                            Royal Snooker Academy
                        </div>

                        <div
                            style="
                                margin-top:4px;
                                color:#E7CB70;
                                font-size:10px;
                                letter-spacing:1.5px;
                                text-transform:uppercase;
                            "
                        >
                            Play. Practice. Perform.
                        </div>

                    </td>
                </tr>


                <!-- STATUS -->
                <tr>
                    <td
                        align="center"
                        style="padding:30px 24px 10px;"
                    >

                        <div
                            style="
                                display:inline-block;
                                background-color:#EAF5F0;
                                border:1px solid #B9DCCF;
                                color:#07513F;
                                padding:8px 16px;
                                border-radius:999px;
                                font-size:12px;
                                font-weight:800;
                                letter-spacing:0.8px;
                            "
                        >
                            ✓ &nbsp; BOOKING CONFIRMED
                        </div>

                    </td>
                </tr>


                <!-- INTRO -->
                <tr>
                    <td
                        style="
                            padding:18px 40px 8px;
                        "
                    >

                        <p
                            style="
                                margin:0 0 16px;
                                font-size:17px;
                                line-height:26px;
                                font-weight:700;
                                color:#18322B;
                            "
                        >
                            Hi {customer_name},
                        </p>

                        <p
                            style="
                                margin:0;
                                font-size:15px;
                                line-height:25px;
                                color:#66746F;
                            "
                        >
                            Your snooker session at
                            <strong style="color:#18322B;">
                                Royal Snooker Academy
                            </strong>
                            has been successfully reserved.
                        </p>

                    </td>
                </tr>


                <!-- BOOKING REFERENCE -->
                <tr>
                    <td
                        style="
                            padding:22px 40px 10px;
                        "
                    >

                        <table
                            role="presentation"
                            width="100%"
                            cellspacing="0"
                            cellpadding="0"
                            border="0"
                            style="
                                background-color:#F4F7F5;
                                border:1px solid #D7E2DD;
                                border-radius:12px;
                            "
                        >
                            <tr>
                                <td
                                    style="
                                        padding:17px 20px;
                                    "
                                >

                                    <div
                                        style="
                                            color:#66746F;
                                            font-size:11px;
                                            font-weight:800;
                                            letter-spacing:1.2px;
                                            text-transform:uppercase;
                                            margin-bottom:7px;
                                        "
                                    >
                                        Booking Reference
                                    </div>

                                    <div
                                        style="
                                            color:#07100D;
                                            font-size:20px;
                                            line-height:26px;
                                            font-weight:800;
                                            letter-spacing:0.5px;
                                        "
                                    >
                                    {booking_reference}
                                    </div>

                                </td>
                            </tr>
                        </table>

                    </td>
                </tr>


                <!-- SESSION DETAILS -->
                <tr>
                    <td
                        style="
                            padding:24px 40px 8px;
                        "
                    >

                        <div
                            style="
                                color:#18322B;
                                font-size:14px;
                                font-weight:800;
                                letter-spacing:0.8px;
                                text-transform:uppercase;
                                margin-bottom:14px;
                            "
                        >
                            Session Details
                        </div>


                        <table
                            role="presentation"
                            width="100%"
                            cellspacing="0"
                            cellpadding="0"
                            border="0"
                            style="
                                border:1px solid #e5e7eb;
                                border-radius:12px;
                                overflow:hidden;
                            "
                        >

                            <tr>
                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#66746F;
                                        font-size:13px;
                                        border-bottom:1px solid #E8EFEB;
                                        width:42%;
                                    "
                                >
                                    Table
                                </td>

                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#18322B;
                                        font-size:13px;
                                        font-weight:700;
                                        text-align:right;
                                        border-bottom:1px solid #E8EFEB;
                                    "
                                >
                                    {table_name}
                                </td>
                            </tr>


                            <tr>
                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#66746F;
                                        font-size:13px;
                                        border-bottom:1px solid #E8EFEB;
                                    "
                                >
                                    Table Type
                                </td>

                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#18322B;
                                        font-size:13px;
                                        font-weight:700;
                                        text-align:right;
                                        border-bottom:1px solid #E8EFEB;
                                    "
                                >
                                    {table_type}
                                </td>
                            </tr>


                            <tr>
                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#66746F;
                                        font-size:13px;
                                        border-bottom:1px solid #E8EFEB;
                                    "
                                >
                                    Date
                                </td>

                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#18322B;
                                        font-size:13px;
                                        font-weight:700;
                                        text-align:right;
                                        border-bottom:1px solid #E8EFEB;
                                    "
                                >
                                    {booking.booking_date.strftime("%d %B %Y")}
                                </td>
                            </tr>


                            <tr>
                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#66746F;
                                        font-size:13px;
                                        border-bottom:1px solid #E8EFEB;
                                    "
                                >
                                    Start Time
                                </td>

                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#18322B;
                                        font-size:13px;
                                        font-weight:700;
                                        text-align:right;
                                        border-bottom:1px solid #E8EFEB;
                                    "
                                >
                                    {booking.start_time.strftime("%I:%M %p")}
                                </td>
                            </tr>


                            <tr>
                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#66746F;
                                        font-size:13px;
                                    "
                                >
                                    Duration
                                </td>

                                <td
                                    style="
                                        padding:13px 16px;
                                        color:#18322B;
                                        font-size:13px;
                                        font-weight:700;
                                        text-align:right;
                                    "
                                >
                                    {duration_label}
                                </td>
                            </tr>

                        </table>

                    </td>
                </tr>


                <!-- AMOUNT -->
                <tr>
                    <td
                        style="
                            padding:22px 40px 10px;
                        "
                    >

                        <table
                            role="presentation"
                            width="100%"
                            cellspacing="0"
                            cellpadding="0"
                            border="0"
                            style="
                                background-color:#FFF8E1;
                                border:1px solid #E7CB70;
                                border-radius:12px;
                            "
                        >
                            <tr>

                                <td
                                    align="center"
                                    style="
                                        padding:20px;
                                    "
                                >

                                    <div
                                        style="
                                            color:#8A6814;
                                            font-size:11px;
                                            font-weight:800;
                                            letter-spacing:1.2px;
                                            text-transform:uppercase;
                                            margin-bottom:7px;
                                        "
                                    >
                                        Total Amount
                                    </div>

                                    <div
                                        style="
                                            color:#18322B;
                                            font-size:27px;
                                            line-height:34px;
                                            font-weight:800;
                                        "
                                    >
                                        {amount}
                                    </div>

                                </td>

                            </tr>
                        </table>

                    </td>
                </tr>


                <!-- MESSAGE -->
                <tr>
                    <td
                        style="
                            padding:22px 40px 28px;
                        "
                    >

                        <p
                            style="
                                margin:0 0 14px;
                                font-size:14px;
                                line-height:24px;
                                color:#36514A;
                            "
                        >
                            Your table has been reserved successfully.
                        </p>

                        <p
                            style="
                                margin:0 0 14px;
                                font-size:14px;
                                line-height:24px;
                                color:#36514A;
                            "
                        >
                            Please arrive a few minutes before your
                            scheduled session.
                        </p>

                        <p
                            style="
                                margin:0;
                                font-size:15px;
                                line-height:25px;
                                color:#18322B;
                                font-weight:700;
                            "
                        >
                            We look forward to seeing you at the academy! 🎱
                        </p>

                        {cancellation_note}

                    </td>
                </tr>


                <!-- FOOTER -->
                <tr>
                    <td
                        align="center"
                        style="
                            background-color:#EAF5F0;
                            border-top:1px solid #D7E2DD;
                            padding:16px 24px;
                        "
                    >

                        <div
                            style="
                                color:#07513F;
                                font-size:14px;
                                font-weight:800;
                                margin-bottom:6px;
                            "
                        >
                            Royal Snooker Academy
                        </div>

                        <div
                            style="
                                color:#36514A;
                                font-size:12px;
                                line-height:19px;
                            "
                        >
                            Play. Practice. Perform.
                        </div>

                        <div
                            style="
                                margin-top:12px;
                                color:#66746F;
                                font-size:11px;
                                line-height:18px;
                            "
                        >
                            Thank you for choosing Royal Snooker Academy.
                        </div>

                    </td>
                </tr>

            </table>

        </td>
    </tr>
</table>

</body>
</html>
"""


def build_completion_email_html(
    booking,
    booking_url,
):
    """
    Build the distinct, warmer HTML post-session email.
    """

    duration_label = (
        f"{booking.duration_hours} hour"
        if booking.duration_hours == 1
        else f"{booking.duration_hours} hours"
    )

    amount = f"₹{booking.amount:,.2f}"
    customer_name = escape(booking.customer_name)
    booking_reference = escape(booking.booking_reference)
    table_name = escape(booking.table.name)
    table_type = escape(booking.table.table_type)
    safe_booking_url = escape(booking_url)

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>Thank You - Royal Snooker Academy</title>
</head>

<body
    style="
        margin:0;
        padding:0;
        background-color:#F7F5EF;
        font-family:Arial,Helvetica,sans-serif;
        color:#1f2937;
    "
>

<table
    role="presentation"
    width="100%"
    cellspacing="0"
    cellpadding="0"
    border="0"
    style="background-color:#F7F5EF;"
>
    <tr>
        <td
            align="center"
            style="padding:28px 14px;"
        >

            <table
                role="presentation"
                width="100%"
                cellspacing="0"
                cellpadding="0"
                border="0"
                style="
                    max-width:620px;
                    background-color:#ffffff;
                    border:1px solid #D7E2DD;
                    border-top:4px solid #D4AF37;
                    border-radius:18px;
                    overflow:hidden;
                    box-shadow:0 5px 20px rgba(15,23,42,0.08);
                "
            >

                <!-- BRAND HEADER -->
                <tr>
                    <td
                        align="center"
                        style="
                            background-color:#07513F;
                            border-bottom:1px solid #D4AF37;
                            padding:18px 24px 16px;
                        "
                    >

                        <img
                            src="cid:rsa-logo"
                            width="84"
                            alt="Royal Snooker Academy"
                            style="
                                display:block;
                                width:84px;
                                max-width:84px;
                                height:auto;
                                margin:0 auto 8px;
                                border:0;
                                outline:none;
                                text-decoration:none;
                            "
                        >

                        <div
                            style="
                                color:#ffffff;
                                font-size:20px;
                                line-height:26px;
                                font-weight:800;
                            "
                        >
                            Royal Snooker Academy
                        </div>

                        <div
                            style="
                                margin-top:4px;
                                color:#E7CB70;
                                font-size:10px;
                                letter-spacing:1.5px;
                                text-transform:uppercase;
                            "
                        >
                            Play. Practice. Perform.
                        </div>

                    </td>
                </tr>


                <!-- WARM INTRO -->
                <tr>
                    <td
                        align="center"
                        style="
                            padding:34px 40px 12px;
                        "
                    >

                        <div
                            style="
                                display:inline-block;
                                background-color:#EAF5F0;
                                border:1px solid #B9DCCF;
                                color:#07513F;
                                padding:7px 15px;
                                border-radius:999px;
                                font-size:11px;
                                font-weight:800;
                                letter-spacing:0.9px;
                                text-transform:uppercase;
                            "
                        >
                            ✓ &nbsp; SESSION COMPLETED
                        </div>

                        <div
                            style="
                                margin-top:25px;
                                color:#18322B;
                                font-size:27px;
                                line-height:35px;
                                font-weight:800;
                            "
                        >
                            Thanks for playing with us!
                        </div>

                        <p
                            style="
                                margin:14px 0 0;
                                color:#66746F;
                                font-size:15px;
                                line-height:25px;
                            "
                        >
                            Hi {customer_name},<br>
                            we hope you enjoyed your session at
                            <strong style="color:#18322B;">
                                Royal Snooker Academy
                            </strong>.
                        </p>

                    </td>
                </tr>


                <!-- SESSION SUMMARY -->
                <tr>
                    <td
                        style="
                            padding:25px 40px 10px;
                        "
                    >

                        <div
                            style="
                                color:#18322B;
                                font-size:13px;
                                font-weight:800;
                                letter-spacing:1px;
                                text-transform:uppercase;
                                margin-bottom:12px;
                            "
                        >
                            Your Session
                        </div>


                        <table
                            role="presentation"
                            width="100%"
                            cellspacing="0"
                            cellpadding="0"
                            border="0"
                            style="
                                background-color:#F4F7F5;
                                border:1px solid #D7E2DD;
                                border-radius:14px;
                            "
                        >

                            <tr>

                                <td
                                    style="
                                        padding:18px;
                                    "
                                >

                                    <div
                                        style="
                                        color:#043A2D;
                                            font-size:18px;
                                            line-height:25px;
                                            font-weight:800;
                                        "
                                    >
                                        {table_name}
                                    </div>

                                    <div
                                        style="
                                            margin-top:4px;
                                            color:#66746F;
                                            font-size:13px;
                                        "
                                    >
                                        {table_type}
                                    </div>

                                </td>


                                <td
                                    align="right"
                                    style="
                                        padding:18px;
                                    "
                                >

                                    <div
                                        style="
                                        color:#043A2D;
                                            font-size:16px;
                                            font-weight:800;
                                        "
                                    >
                                        {booking.start_time.strftime("%I:%M %p")}
                                    </div>

                                    <div
                                        style="
                                            margin-top:5px;
                                            color:#66746F;
                                            font-size:12px;
                                        "
                                    >
                                        {booking.booking_date.strftime("%d %B %Y")}
                                    </div>

                                </td>

                            </tr>


                            <tr>
                                <td
                                    colspan="2"
                                    style="
                                        padding:0 18px 17px;
                                    "
                                >

                                    <div
                                        style="
                                            height:1px;
                                            background-color:#D7E2DD;
                                        "
                                    ></div>

                                    <table
                                        role="presentation"
                                        width="100%"
                                        cellspacing="0"
                                        cellpadding="0"
                                        border="0"
                                        style="
                                            margin-top:14px;
                                        "
                                    >

                                        <tr>

                                            <td
                                                style="
                                                    color:#66746F;
                                                    font-size:12px;
                                                "
                                            >
                                                Duration
                                            </td>

                                            <td
                                                align="right"
                                                style="
                                                    color:#18322B;
                                                    font-size:12px;
                                                    font-weight:700;
                                                "
                                            >
                                                {duration_label}
                                            </td>

                                        </tr>

                                    </table>

                                </td>
                            </tr>

                        </table>

                    </td>
                </tr>


                <!-- AMOUNT -->
                <tr>
                    <td
                        align="center"
                        style="
                            padding:18px 40px 8px;
                        "
                    >

                        <div
                            style="
                                color:#66746F;
                                font-size:10px;
                                font-weight:800;
                                letter-spacing:1.5px;
                                text-transform:uppercase;
                            "
                        >
                            Session Amount
                        </div>

                        <div
                            style="
                                margin-top:5px;
                                color:#18322B;
                                font-size:26px;
                                line-height:34px;
                                font-weight:800;
                            "
                        >
                            {amount}
                        </div>

                    </td>
                </tr>


                <!-- COMPLETION MESSAGE -->
                <tr>
                    <td
                        style="
                            padding:22px 40px 8px;
                        "
                    >

                        <table
                            role="presentation"
                            width="100%"
                            cellspacing="0"
                            cellpadding="0"
                            border="0"
                            style="
                                background-color:#FFF8E1;
                                border-left:4px solid #D4AF37;
                            "
                        >

                            <tr>

                                <td
                                    style="
                                        padding:15px 16px;
                                        color:#36514A;
                                        font-size:14px;
                                        line-height:23px;
                                    "
                                >
                                    Your session has been successfully
                                    completed. Thank you for spending
                                    your time with us.
                                </td>

                            </tr>

                        </table>

                    </td>
                </tr>


                <!-- RETURN MESSAGE -->
                <tr>
                    <td
                        align="center"
                        style="
                            padding:22px 40px 8px;
                        "
                    >

                        <p
                            style="
                                margin:0;
                                color:#36514A;
                                font-size:14px;
                                line-height:24px;
                            "
                        >
                            We'd love to welcome you back for another game.
                        </p>

                        <p
                            style="
                                margin:8px 0 0;
                                color:#18322B;
                                font-size:16px;
                                line-height:25px;
                                font-weight:800;
                            "
                        >
                            See you again soon! 🎱
                        </p>

                    </td>
                </tr>


                <!-- BOOK AGAIN BUTTON -->
                <tr>
                    <td
                        align="center"
                        style="
                            padding:22px 40px 30px;
                        "
                    >

                        <a
                            href="{safe_booking_url}"
                            style="
                                display:inline-block;
                                background-color:#D4AF37;
                            color:#043A2D;
                                text-decoration:none;
                                font-size:14px;
                                font-weight:800;
                                padding:13px 25px;
                                border-radius:9px;
                            "
                        >
                            Book Another Session
                        </a>

                    </td>
                </tr>


                <!-- REFERENCE -->
                <tr>
                    <td
                        align="center"
                        style="
                            padding:0 40px 25px;
                        "
                    >

                        <div
                            style="
                                color:#AEBBB6;
                                font-size:11px;
                                line-height:18px;
                            "
                        >
                            Booking Reference:
                            <strong style="color:#66746F;">
                                {booking_reference}
                            </strong>
                        </div>

                    </td>
                </tr>


                <!-- FOOTER -->
                <tr>
                    <td
                        align="center"
                        style="
                            background-color:#EAF5F0;
                            border-top:1px solid #D7E2DD;
                            padding:16px 24px;
                        "
                    >

                        <div
                            style="
                                color:#07513F;
                                font-size:14px;
                                font-weight:800;
                            "
                        >
                            Royal Snooker Academy
                        </div>

                        <div
                            style="
                                margin-top:6px;
                                color:#36514A;
                                font-size:12px;
                            "
                        >
                            Play. Practice. Perform.
                        </div>

                        <div
                            style="
                                margin-top:12px;
                                color:#66746F;
                                font-size:11px;
                                line-height:18px;
                            "
                        >
                            Thank you for being part of the RSA community.
                        </div>

                    </td>
                </tr>

            </table>

        </td>
    </tr>
</table>

</body>
</html>
"""


def send_booking_confirmation_notification(
    booking,
    cancellation_request_url=None,
):
    """Send the standard booking confirmation email and report delivery."""

    if not cancellation_request_url:
        public_hostname = getattr(
            settings,
            "RENDER_EXTERNAL_HOSTNAME",
            "",
        ).strip()
        if public_hostname:
            cancellation_request_url = (
                f"https://{public_hostname}"
                f"{reverse('booking_cancellation_request')}"
            )

    booking_reference = booking.booking_reference
    subject = (
        f"Booking Confirmed - {booking_reference} | "
        "Royal Snooker Academy"
    )
    plain_message = f"""
Hello {booking.customer_name},

Your snooker session at Royal Snooker Academy has been successfully reserved.

BOOKING DETAILS
------------------------------
Booking Reference : {booking_reference}
Customer Name     : {booking.customer_name}
Table             : {booking.table.name}
Table Type        : {booking.table.table_type}
Date              : {booking.booking_date.strftime("%d %B %Y")}
Start Time        : {booking.start_time.strftime("%I:%M %p")}
Duration          : {booking.duration_hours} hour{"s" if booking.duration_hours != 1 else ""}
Total Amount      : ₹{booking.amount:,.2f}

Your table has been reserved successfully.

Please arrive a few minutes before your scheduled session.

We look forward to seeing you at the academy!

{"To request cancellation, visit " + cancellation_request_url + ". You must request it at least 2 hours before your session." if cancellation_request_url else "For booking changes, please visit the academy website."}

Royal Snooker Academy
Play. Practice. Perform.
"""

    return _send_tracked_booking_email(
        booking=booking,
        notification_type=BookingEmailNotification.NotificationType.CONFIRMATION,
        subject=subject,
        plain_message=plain_message,
        html_message=build_booking_confirmation_html(
            booking,
            cancellation_request_url=cancellation_request_url,
        ),
    )


def send_booking_cancellation_notification(booking):
    """Send the customer a branded notice after a booking is cancelled."""

    booking_reference = booking.booking_reference
    subject = (
        f"Booking Cancelled - {booking_reference} | "
        "Royal Snooker Academy"
    )
    duration_label = (
        f"{booking.duration_hours} hour"
        if booking.duration_hours == 1
        else f"{booking.duration_hours} hours"
    )
    plain_message = f"""
Hello {booking.customer_name},

This email confirms that your Royal Snooker Academy booking has been cancelled.

BOOKING DETAILS
------------------------------
Booking Reference : {booking_reference}
Table             : {booking.table.name}
Table Type        : {booking.table.table_type}
Date              : {booking.booking_date.strftime("%d %B %Y")}
Start Time        : {booking.start_time.strftime("%I:%M %p")}
Duration          : {duration_label}

If you expected to attend this session or have questions about the cancellation, please contact the academy using the details on our website.

If you would like to visit another time, you are welcome to make a new booking.

Royal Snooker Academy
Play. Practice. Perform.
"""
    customer_name = escape(booking.customer_name)
    table_name = escape(booking.table.name)
    table_type = escape(booking.table.table_type)
    booking_reference = escape(booking_reference)
    booking_date = escape(booking.booking_date.strftime("%d %B %Y"))
    start_time = escape(booking.start_time.strftime("%I:%M %p"))
    duration_label = escape(duration_label)
    html_message = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Booking Cancelled - Royal Snooker Academy</title></head>
<body style="margin:0;padding:20px 12px;background:#F7F5EF;font-family:Arial,Helvetica,sans-serif;color:#18322B;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:620px;margin:0 auto;background:#ffffff;border:1px solid #D7E2DD;border-top:4px solid #D4AF37;border-radius:14px;overflow:hidden;">
    <tr><td style="padding:18px 20px 16px;background:#07513F;text-align:center;border-bottom:1px solid #D4AF37;">
      <img src="cid:rsa-logo" width="84" alt="Royal Snooker Academy" style="display:block;width:84px;max-width:84px;height:auto;margin:0 auto 8px;border:0;">
      <div style="color:#ffffff;font-size:20px;line-height:26px;font-weight:800;">Royal Snooker Academy</div>
      <div style="margin-top:4px;color:#E7CB70;font-size:10px;letter-spacing:1.5px;">PLAY. PRACTICE. PERFORM.</div>
    </td></tr>
    <tr><td style="padding:26px 28px 10px;">
      <div style="display:inline-block;padding:6px 12px;background:#EAF5F0;border:1px solid #B9DCCF;border-radius:999px;color:#07513F;font-size:10px;font-weight:800;letter-spacing:.7px;">BOOKING CANCELLED</div>
      <h1 style="margin:16px 0 12px;color:#043A2D;font-size:22px;line-height:29px;">Your booking has been cancelled</h1>
      <p style="margin:0 0 10px;color:#36514A;font-size:14px;line-height:22px;">Hello {customer_name},</p>
      <p style="margin:0;color:#36514A;font-size:14px;line-height:22px;">This email confirms that the following Royal Snooker Academy booking has been cancelled.</p>
    </td></tr>
    <tr><td style="padding:14px 28px 22px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #D7E2DD;border-radius:10px;overflow:hidden;">
        <tr><td style="padding:11px 14px;background:#EAF5F0;color:#07513F;font-size:11px;font-weight:800;letter-spacing:.7px;text-transform:uppercase;">Booking reference</td><td align="right" style="padding:11px 14px;background:#EAF5F0;color:#043A2D;font-size:12px;font-weight:800;">{booking_reference}</td></tr>
        <tr><td style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#66746F;font-size:13px;">Table</td><td align="right" style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#18322B;font-size:13px;font-weight:700;">{table_name}</td></tr>
        <tr><td style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#66746F;font-size:13px;">Table type</td><td align="right" style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#18322B;font-size:13px;font-weight:700;">{table_type}</td></tr>
        <tr><td style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#66746F;font-size:13px;">Date</td><td align="right" style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#18322B;font-size:13px;font-weight:700;">{booking_date}</td></tr>
        <tr><td style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#66746F;font-size:13px;">Start time</td><td align="right" style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#18322B;font-size:13px;font-weight:700;">{start_time}</td></tr>
        <tr><td style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#66746F;font-size:13px;">Duration</td><td align="right" style="padding:10px 14px;border-top:1px solid #E8EFEB;color:#18322B;font-size:13px;font-weight:700;">{duration_label}</td></tr>
      </table>
    </td></tr>
    <tr><td style="padding:0 28px 24px;color:#36514A;font-size:13px;line-height:21px;">
      <p style="margin:0 0 10px;">If you expected to attend this session or have questions about the cancellation, please contact the academy using the details on our website.</p>
      <p style="margin:0;">If you would like to visit another time, you are welcome to make a new booking.</p>
    </td></tr>
    <tr><td align="center" style="padding:15px 20px;background:#EAF5F0;border-top:1px solid #D7E2DD;">
      <div style="color:#07513F;font-size:13px;font-weight:800;">Royal Snooker Academy</div>
      <div style="margin-top:4px;color:#36514A;font-size:10px;">Play. Practice. Perform.</div>
    </td></tr>
  </table>
</body>
</html>"""

    return _send_tracked_booking_email(
        booking=booking,
        notification_type=BookingEmailNotification.NotificationType.CANCELLATION,
        subject=subject,
        plain_message=plain_message,
        html_message=html_message,
    )


def send_booking_completion_notification(booking, booking_url):
    """Send the standard post-session email and track its delivery state."""

    subject = (
        "Thank You for Visiting Royal Snooker Academy | "
        f"{booking.booking_reference}"
    )
    plain_message = f"""
Hello {booking.customer_name},

Thanks for playing with us!

We hope you enjoyed your session at Royal Snooker Academy.

YOUR SESSION
------------------------------
Table             : {booking.table.name}
Table Type        : {booking.table.table_type}
Date              : {booking.booking_date.strftime("%d %B %Y")}
Start Time        : {booking.start_time.strftime("%I:%M %p")}
Duration          : {booking.duration_hours} hour{"s" if booking.duration_hours != 1 else ""}
Session Amount    : ₹{booking.amount:,.2f}

Your session has been successfully completed.

We'd love to welcome you back for another game.

Book another session:
{booking_url}

Booking Reference:
{booking.booking_reference}

Royal Snooker Academy
Play. Practice. Perform.

Thank you for being part of the RSA community.
"""
    return _send_tracked_booking_email(
        booking=booking,
        notification_type=BookingEmailNotification.NotificationType.COMPLETION,
        subject=subject,
        plain_message=plain_message,
        html_message=build_completion_email_html(
            booking=booking,
            booking_url=booking_url,
        ),
    )


def home(request):

    home_settings = HomePageSettings.objects.filter(
        is_active=True
    ).first()

    active_tables = Table.objects.filter(
        is_active=True
    ).order_by("id")

    active_table_count = active_tables.count()

    active_coaching_count = CoachingContent.objects.filter(
        is_active=True
    ).count()

    active_tournament_count = TournamentContent.objects.filter(
        is_active=True
    ).count()

    return render(
        request,
        "home.html",
        {
            "home_settings": home_settings,
            "tables": active_tables,
            "active_table_count": active_table_count,
            "active_coaching_count": active_coaching_count,
            "active_tournament_count": active_tournament_count,
        },
    )


def tables(request):

    active_tables = Table.objects.filter(
        is_active=True
    ).order_by("id")

    return render(
        request,
        "tables.html",
        {
            "tables": active_tables,
        },
    )


def get_time_slots():

    slots = []

    for hour in range(10, 23):

        value = f"{hour:02d}:00"

        display_hour = hour % 12 or 12

        suffix = "AM" if hour < 12 else "PM"

        label = f"{display_hour}:00 {suffix}"

        slots.append(
            TimeSlot(
                value=value,
                label=label,
            )
        )

    return slots


def get_table_availability(
    booking_date,
    start_time,
    duration_hours,
):

    tables = Table.objects.filter(
        is_active=True
    ).order_by("id")

    start_datetime = datetime.combine(
        booking_date,
        start_time,
    )

    end_datetime = (
        start_datetime
        + timedelta(hours=duration_hours)
    )

    results = []

    for table in tables:

        bookings = Booking.objects.filter(
            table=table,
            booking_date=booking_date,
            status="Confirmed",
        )

        is_available = True

        for existing_booking in bookings:

            existing_start = datetime.combine(
                booking_date,
                existing_booking.start_time,
            )

            existing_end = (
                existing_start
                + timedelta(
                    hours=existing_booking.duration_hours
                )
            )

            if (
                start_datetime < existing_end
                and end_datetime > existing_start
            ):
                is_available = False
                break

        results.append(
            {
                "id": table.id,
                "name": table.name,
                "table_type": table.table_type,
                "hourly_rate": float(table.hourly_rate),
                "available": is_available,
            }
        )

    return results


def availability(request):

    booking_date = request.GET.get("date")
    start_time = request.GET.get("start_time")
    duration = request.GET.get("duration")

    if not booking_date or not start_time or not duration:

        return JsonResponse(
            {
                "error": "Missing booking information."
            },
            status=400,
        )

    try:

        booking_date = datetime.strptime(
            booking_date,
            "%Y-%m-%d",
        ).date()

        start_time = datetime.strptime(
            start_time,
            "%H:%M",
        ).time()

        duration = int(duration)

        if duration not in (1, 2, 3, 4):
            raise ValueError

    except (ValueError, TypeError):

        return JsonResponse(
            {
                "error": "Invalid booking information."
            },
            status=400,
        )

    tables = get_table_availability(
        booking_date,
        start_time,
        duration,
    )

    return JsonResponse(
        {
            "tables": tables,
        }
    )


def booking(request):

    academy_settings = AcademySettings.objects.first()

    if academy_settings is None:

        academy_settings = AcademySettings.objects.create(
            opening_time=time(10, 0),
            closing_time=time(23, 0),
        )

    active_tables = Table.objects.filter(
        is_active=True
    ).order_by("id")

    time_slots = get_time_slots()

    context = {
        "tables": active_tables,
        "time_slots": time_slots,
        "academy_settings": academy_settings,
    }

    if request.method == "POST":

        table_id = request.POST.get("table")

        customer_name = request.POST.get(
            "customer_name",
            "",
        ).strip()

        phone = request.POST.get(
            "phone",
            "",
        ).strip()

        email = request.POST.get(
            "email",
            "",
        ).strip()

        booking_date = request.POST.get("booking_date")
        start_time = request.POST.get("start_time")
        duration = request.POST.get("duration")

        errors = []

        if not table_id:
            errors.append("Please select a table.")

        if not customer_name:
            errors.append("Please enter your full name.")
        elif not re.fullmatch(
            r"[A-Za-z]+(?: [A-Za-z]+)*",
            customer_name,
        ):
            errors.append(
                "Please enter a valid name using alphabets and spaces only."
            )

        if not phone:
            errors.append("Please enter your phone number.")
        else:
            if not re.fullmatch(
                r"[6-9]\d{9}",
                phone,
            ):
                errors.append(
                    "Please enter exactly 10 digits. The first digit must be 6, 7, 8 or 9."
                )

        if not email:
            errors.append(
                "Please enter your email address."
            )
        else:
            try:
                validate_email(email)
            except ValidationError:
                errors.append(
                    "Please enter a valid email address."
                )

        if not booking_date:
            errors.append(
                "Please select a booking date."
            )

        if not start_time:
            errors.append(
                "Please select a start time."
            )

        if not duration:
            errors.append(
                "Please select duration."
            )

        if errors:

            context["errors"] = errors

            return render(
                request,
                "booking.html",
                context,
            )

        try:

            table = Table.objects.get(
                id=table_id,
                is_active=True,
            )

            booking_date = datetime.strptime(
                booking_date,
                "%Y-%m-%d",
            ).date()

            start_time = datetime.strptime(
                start_time,
                "%H:%M",
            ).time()

            duration_hours = int(duration)

            if duration_hours not in (1, 2, 3, 4):
                raise ValueError

        except (
            Table.DoesNotExist,
            ValueError,
            TypeError,
        ):

            context["errors"] = [
                "Invalid booking information."
            ]

            return render(
                request,
                "booking.html",
                context,
            )

        today = timezone.localdate()

        if booking_date < today:

            context["errors"] = [
                "You cannot book a past date."
            ]

            return render(
                request,
                "booking.html",
                context,
            )

        start_datetime = datetime.combine(
            booking_date,
            start_time,
        )

        end_datetime = (
            start_datetime
            + timedelta(hours=duration_hours)
        )

        opening_datetime = datetime.combine(
            booking_date,
            academy_settings.opening_time,
        )

        closing_datetime = datetime.combine(
            booking_date,
            academy_settings.closing_time,
        )

        if (
            start_datetime < opening_datetime
            or end_datetime > closing_datetime
        ):

            context["errors"] = [
                "Selected time is outside academy operating hours."
            ]

            return render(
                request,
                "booking.html",
                context,
            )

        # Allow a 15-minute grace period after the slot start time.
        if booking_date == today:

            current_datetime = timezone.localtime()

            grace_deadline = (
                timezone.make_aware(
                    start_datetime,
                    timezone.get_current_timezone(),
                )
                + timedelta(minutes=15)
            )

            if current_datetime > grace_deadline:

                context["errors"] = [
                    "This time slot is no longer available for booking."
                ]

                return render(
                    request,
                    "booking.html",
                    context,
                )

        try:

            with transaction.atomic():

                # Lock the selected table while performing the final
                # availability check and creating the booking.
                #
                # This prevents two simultaneous booking requests
                # from both passing the availability check for the
                # same table when using a database that supports
                # row-level locking such as PostgreSQL.
                table = (
                    Table.objects
                    .select_for_update()
                    .get(
                        id=table.id,
                        is_active=True,
                    )
                )

                existing_bookings = Booking.objects.filter(
                    table=table,
                    booking_date=booking_date,
                    status="Confirmed",
                )

                for existing_booking in existing_bookings:

                    existing_start = datetime.combine(
                        booking_date,
                        existing_booking.start_time,
                    )

                    existing_end = (
                        existing_start
                        + timedelta(
                            hours=existing_booking.duration_hours
                        )
                    )

                    if (
                        start_datetime < existing_end
                        and end_datetime > existing_start
                    ):

                        context["errors"] = [
                            "This table is already booked for the selected time."
                        ]

                        return render(
                            request,
                            "booking.html",
                            context,
                        )

                amount = (
                    table.hourly_rate
                    * duration_hours
                )

                booking = Booking.objects.create(
                    table=table,
                    customer_name=customer_name,
                    phone=phone,
                    email=email,
                    booking_date=booking_date,
                    start_time=start_time,
                    duration_hours=duration_hours,
                    amount=amount,
                    status="Confirmed",
                )

        except Table.DoesNotExist:

            context["errors"] = [
                "The selected table is no longer available."
            ]

            return render(
                request,
                "booking.html",
                context,
            )

        send_booking_confirmation_notification(
            booking,
            cancellation_request_url=request.build_absolute_uri(
                reverse("booking_cancellation_request")
            ),
        )

        request.session["booking_success"] = {
            "booking_id": booking.id,
        }

        return redirect("booking")

    success_data = request.session.pop("booking_success", None)

    if success_data:
        try:
            successful_booking = (
                Booking.objects
                .select_related("table")
                .get(id=success_data["booking_id"])
            )

            return render(
                request,
                "booking.html",
                {
                    **context,
                    "success": True,
                    "booking_reference": successful_booking.booking_reference,
                    "booking_amount": successful_booking.amount,
                    "booked_table": successful_booking.table,
                    "booked_customer_name": successful_booking.customer_name,
                    "booked_date": successful_booking.booking_date,
                    "booked_start_time": successful_booking.start_time,
                    "booked_duration": successful_booking.duration_hours,
                },
            )

        except Booking.DoesNotExist:
            pass

    return render(
        request,
        "booking.html",
        context,
    )


def _find_customer_booking_for_cancellation(booking_reference, email):
    match = re.fullmatch(
        r"RSA-(\d{8})-(\d{4,})",
        booking_reference.strip().upper(),
    )
    if not match:
        return None

    try:
        booking_date = datetime.strptime(match.group(1), "%Y%m%d").date()
        booking_id = int(match.group(2))
    except (TypeError, ValueError):
        return None

    booking = (
        Booking.objects
        .select_related("table")
        .filter(pk=booking_id, booking_date=booking_date)
        .first()
    )
    if not booking or booking.email.casefold() != email.strip().casefold():
        return None
    return booking


def _booking_cancellation_deadline(booking):
    session_start = datetime.combine(
        booking.booking_date,
        booking.start_time,
    )
    session_start = timezone.make_aware(
        session_start,
        timezone.get_current_timezone(),
    )
    return session_start - timedelta(hours=2)


def _booking_cancellation_is_allowed(booking, now=None):
    now = now or timezone.now()
    return (
        booking.status == "Confirmed"
        and now <= _booking_cancellation_deadline(booking)
    )


def _send_booking_cancellation_link(booking, confirmation_url):
    customer_name = escape(booking.customer_name)
    booking_reference = escape(booking.booking_reference)
    table_name = escape(booking.table.name)
    safe_url = escape(confirmation_url)
    expiry_minutes = 30
    plain_message = f"""Hello {booking.customer_name},

We received a request to cancel your Royal Snooker Academy booking.

Booking reference: {booking.booking_reference}
Table: {booking.table.name}
Date: {booking.booking_date.strftime("%d %B %Y")}
Start time: {booking.start_time.strftime("%I:%M %p")}

To continue, open this secure link within {expiry_minutes} minutes:
{confirmation_url}

Your booking will not be cancelled unless you open the link and confirm. If you did not make this request, you can ignore this email.

Royal Snooker Academy
Play. Practice. Perform.
"""
    html_message = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Confirm booking cancellation request</title></head>
<body style="margin:0;padding:20px 12px;background:#F7F5EF;font-family:Arial,Helvetica,sans-serif;color:#18322B;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #D7E2DD;border-top:4px solid #D4AF37;border-radius:14px;overflow:hidden;">
    <tr><td style="padding:18px 20px 16px;background:#07513F;text-align:center;border-bottom:1px solid #D4AF37;">
      <img src="cid:rsa-logo" width="84" alt="Royal Snooker Academy" style="display:block;width:84px;max-width:84px;height:auto;margin:0 auto 8px;border:0;">
      <div style="color:#ffffff;font-size:20px;line-height:26px;font-weight:800;">Royal Snooker Academy</div>
      <div style="margin-top:4px;color:#E7CB70;font-size:10px;letter-spacing:1.5px;">PLAY. PRACTICE. PERFORM.</div>
    </td></tr>
    <tr><td style="padding:26px 28px 28px;">
      <h1 style="margin:0 0 12px;color:#043A2D;font-size:21px;line-height:28px;">Confirm your cancellation request</h1>
      <p style="margin:0 0 12px;color:#36514A;font-size:14px;line-height:22px;">Hello {customer_name}, we received a request to cancel this booking:</p>
      <p style="margin:0 0 20px;padding:12px;background:#EAF5F0;border-radius:8px;color:#07513F;font-size:13px;line-height:21px;"><strong>{booking_reference}</strong><br>{table_name} · {booking.booking_date.strftime("%d %B %Y")} · {booking.start_time.strftime("%I:%M %p")}</p>
      <p style="margin:0 0 20px;color:#36514A;font-size:13px;line-height:21px;">Your booking will remain confirmed unless you open the secure link below and complete the cancellation. The link expires in {expiry_minutes} minutes.</p>
      <p style="margin:0 0 20px;text-align:center;"><a href="{safe_url}" style="display:inline-block;padding:12px 20px;background:#D4AF37;border-radius:8px;color:#07100D;font-size:13px;font-weight:800;text-decoration:none;">Review cancellation</a></p>
      <p style="margin:0;color:#66746F;font-size:12px;line-height:19px;">If you did not make this request, you can ignore this email. No change will be made to your booking.</p>
    </td></tr>
    <tr><td align="center" style="padding:14px 20px;background:#EAF5F0;border-top:1px solid #D7E2DD;color:#36514A;font-size:11px;">Royal Snooker Academy · Play. Practice. Perform.</td></tr>
  </table>
</body>
</html>"""
    send_rsa_html_email(
        subject=f"Confirm cancellation request - {booking.booking_reference}",
        recipient=booking.email,
        plain_message=plain_message,
        html_message=html_message,
        logo_path=get_rsa_email_logo_path(),
    )


def booking_cancellation_request(request):
    form = BookingCancellationLookupForm(request.POST or None)
    request_submitted = request.method == "POST"

    if request_submitted and form.is_valid():
        booking = _find_customer_booking_for_cancellation(
            form.cleaned_data["booking_reference"],
            form.cleaned_data["email"],
        )

        if booking and _booking_cancellation_is_allowed(booking):
            now = timezone.now()
            token = secrets.token_urlsafe(32)
            token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            should_send = False

            with transaction.atomic():
                locked_booking = (
                    Booking.objects
                    .select_for_update()
                    .select_related("table")
                    .get(pk=booking.pk)
                )
                if _booking_cancellation_is_allowed(locked_booking, now):
                    cancellation, created = BookingCancellation.objects.get_or_create(
                        booking=locked_booking,
                        defaults={
                            "token_digest": token_digest,
                            "requested_at": now,
                            "expires_at": now + timedelta(minutes=30),
                        },
                    )
                    can_resend = (
                        created
                        or now - cancellation.requested_at >= timedelta(minutes=2)
                        or cancellation.expires_at <= now
                    )
                    if not created and can_resend:
                        cancellation.token_digest = token_digest
                        cancellation.requested_at = now
                        cancellation.expires_at = now + timedelta(minutes=30)
                        cancellation.used_at = None
                        cancellation.reason = ""
                        cancellation.reason_details = ""
                        cancellation.save(
                            update_fields=[
                                "token_digest",
                                "requested_at",
                                "expires_at",
                                "used_at",
                                "reason",
                                "reason_details",
                            ]
                        )
                    should_send = created or can_resend

            if should_send:
                confirmation_url = request.build_absolute_uri(
                    reverse(
                        "booking_cancellation_confirm",
                        kwargs={"token": token},
                    )
                )
                try:
                    _send_booking_cancellation_link(booking, confirmation_url)
                except Exception:
                    logger.exception(
                        "Customer cancellation link could not be sent for %s",
                        booking.booking_reference,
                    )

    return render(
        request,
        "booking_cancellation_request.html",
        {
            "form": form,
            "request_submitted": request_submitted and form.is_valid(),
        },
    )


def booking_cancellation_confirm(request, token):
    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cancellation = (
        BookingCancellation.objects
        .select_related("booking", "booking__table")
        .filter(token_digest=token_digest)
        .first()
    )

    if cancellation is None:
        return render(
            request,
            "booking_cancellation_result.html",
            {"result": "invalid"},
        )

    booking = cancellation.booking
    now = timezone.now()
    if cancellation.used_at:
        return render(
            request,
            "booking_cancellation_result.html",
            {"result": "already_used"},
        )
    if cancellation.expires_at <= now:
        return render(
            request,
            "booking_cancellation_result.html",
            {"result": "expired"},
        )
    if not _booking_cancellation_is_allowed(booking, now):
        result = (
            "cutoff"
            if booking.status == "Confirmed"
            else "unavailable"
        )
        return render(
            request,
            "booking_cancellation_result.html",
            {"result": result},
        )

    form = CustomerBookingCancellationForm(request.POST or None, instance=cancellation)
    if request.method == "POST" and form.is_valid():
        cancellation_completed = False
        result = "unavailable"
        with transaction.atomic():
            locked_booking = (
                Booking.objects
                .select_for_update()
                .select_related("table")
                .get(pk=booking.pk)
            )
            locked_cancellation = (
                BookingCancellation.objects
                .select_for_update()
                .filter(pk=cancellation.pk, token_digest=token_digest)
                .first()
            )
            now = timezone.now()
            if locked_cancellation is None:
                result = "invalid"
            elif locked_cancellation.used_at:
                result = "already_used"
            elif locked_cancellation.expires_at <= now:
                result = "expired"
            elif not _booking_cancellation_is_allowed(locked_booking, now):
                result = (
                    "cutoff"
                    if locked_booking.status == "Confirmed"
                    else "unavailable"
                )
            else:
                locked_cancellation.reason = form.cleaned_data["reason"]
                locked_cancellation.reason_details = form.cleaned_data[
                    "reason_details"
                ]
                locked_cancellation.used_at = now
                locked_cancellation.save(
                    update_fields=["reason", "reason_details", "used_at"]
                )
                locked_booking.status = "Cancelled"
                locked_booking.save(update_fields=["status"])
                booking = locked_booking
                cancellation_completed = True
                result = "cancelled"

        if cancellation_completed:
            email_sent = send_booking_cancellation_notification(booking)
            return render(
                request,
                "booking_cancellation_result.html",
                {
                    "result": result,
                    "email_sent": email_sent,
                    "booking": booking,
                },
            )
        return render(
            request,
            "booking_cancellation_result.html",
            {"result": result},
        )

    return render(
        request,
        "booking_cancellation_confirm.html",
        {
            "booking": booking,
            "cancellation": cancellation,
            "form": form,
        },
    )


@manager_required
def cancel_booking(request, booking_id):

    if request.method != "POST":
        return JsonResponse(
            {
                "error": "Cancellation must be submitted using POST."
            },
            status=405,
        )

    try:
        booking = Booking.objects.select_related("table").get(id=booking_id)
    except Booking.DoesNotExist:
        messages.error(
            request,
            "The selected booking could not be found.",
        )
        return redirect("admin_dashboard")

    if booking.status != "Confirmed":
        messages.warning(
            request,
            f"Booking {booking.booking_reference} is already "
            f"{booking.status.lower()} and was not changed.",
        )
        return redirect("admin_dashboard")

    with transaction.atomic():
        changed = Booking.objects.filter(
            pk=booking.pk,
            status="Confirmed",
        ).update(
            status="Cancelled",
        )

        if changed:
            booking.status = "Cancelled"
            log_booking_status_change(
                request.user,
                booking,
                old_status="Confirmed",
                new_status="Cancelled",
            )

    if not changed:
        messages.warning(
            request,
            f"Booking {booking.booking_reference} was already updated and was not cancelled again.",
        )
        return redirect("admin_dashboard")

    messages.success(
        request,
        f"Booking {booking.booking_reference} has been cancelled successfully.",
    )

    if not send_booking_cancellation_notification(booking):
        messages.warning(
            request,
            "The booking was cancelled, but its customer email could not be sent. "
            "See the application log for details.",
        )

    return redirect("admin_dashboard")


@manager_required
def complete_booking(request, booking_id):

    if request.method != "POST":
        return JsonResponse(
            {
                "error": "Completion must be submitted using POST."
            },
            status=405,
        )

    try:
        booking = Booking.objects.get(id=booking_id)
    except Booking.DoesNotExist:
        messages.error(
            request,
            "The selected booking could not be found.",
        )
        return redirect("admin_dashboard")

    if booking.status != "Confirmed":
        messages.warning(
            request,
            f"Booking {booking.booking_reference} is already "
            f"{booking.status.lower()} and was not changed.",
        )
        return redirect("admin_dashboard")

    # A session can only be completed after its scheduled end time.
    # This prevents staff from accidentally closing an active or future session.
    today = timezone.localdate()
    current_datetime = timezone.localtime()
    session_end = (
        datetime.combine(
            booking.booking_date,
            booking.start_time,
        )
        + timedelta(hours=booking.duration_hours)
    )

    current_local_naive = current_datetime.replace(tzinfo=None)

    if session_end > current_local_naive:
        messages.warning(
            request,
            f"Booking {booking.booking_reference} cannot be completed yet. "
            "The scheduled session has not ended.",
        )
        return redirect("admin_dashboard")

    with transaction.atomic():
        changed = Booking.objects.filter(
            pk=booking.pk,
            status="Confirmed",
        ).update(status="Completed")

        if changed:
            booking.status = "Completed"
            log_booking_status_change(
                request.user,
                booking,
                old_status="Confirmed",
                new_status="Completed",
            )

    if not changed:
        messages.warning(
            request,
            f"Booking {booking.booking_reference} was already updated and was not completed again.",
        )
        return redirect("admin_dashboard")

    email_sent = send_booking_completion_notification(
        booking=booking,
        booking_url=request.build_absolute_uri("/book/"),
    )

    messages.success(
        request,
        f"Booking {booking.booking_reference} has been marked as completed.",
    )

    if not email_sent:
        messages.warning(
            request,
            "The booking was completed, but its customer email could not be sent. "
            "See the application log for details.",
        )

    return redirect("admin_dashboard")


@manager_required
def admin_dashboard(request):

    today = timezone.localdate()
    current_time = timezone.localtime().time()
    dashboard_updated_at = timezone.localtime()

    today_bookings = (
        Booking.objects
        .select_related("table")
        .filter(booking_date=today)
        .order_by("start_time")
    )

    confirmed_today = today_bookings.filter(
        status="Confirmed"
    )

    today_revenue = (
        confirmed_today.aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )

    upcoming_bookings = (
        Booking.objects
        .select_related("table")
        .filter(
            status="Confirmed",
            booking_date__gte=today,
        )
        .order_by(
            "booking_date",
            "start_time",
        )
    )

    all_bookings = (
        Booking.objects
        .select_related("table")
        .order_by(
            "-booking_date",
            "-start_time",
            "-id",
        )
    )

    active_tables = Table.objects.filter(
        is_active=True
    ).order_by("id")

    completed_today = today_bookings.filter(
        status="Completed"
    )

    cancelled_today = today_bookings.filter(
        status="Cancelled"
    )

    completed_today_revenue = (
        completed_today.aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )

    trend_start_date = today - timedelta(days=6)
    daily_booking_counts = {
        item["booking_date"]: item["total"]
        for item in Booking.objects.filter(
            booking_date__range=(trend_start_date, today),
            status__in=["Confirmed", "Completed"],
        ).values("booking_date").annotate(total=Count("id"))
    }
    highest_daily_booking_count = max(
        daily_booking_counts.values(),
        default=0,
    )
    booking_trend = []

    for day_offset in range(7):
        trend_date = trend_start_date + timedelta(days=day_offset)
        booking_count = daily_booking_counts.get(trend_date, 0)
        booking_trend.append(
            {
                "date": trend_date,
                "weekday": trend_date.strftime("%a"),
                "count": booking_count,
                "bar_height": (
                    round(booking_count / highest_daily_booking_count * 100)
                    if highest_daily_booking_count
                    else 0
                ),
            }
        )

    table_statuses = []

    for table in active_tables:

        table_bookings = (
            Booking.objects
            .filter(
                table=table,
                status="Confirmed",
                booking_date__gte=today,
            )
            .order_by(
                "booking_date",
                "start_time",
            )
        )

        current_booking = None
        next_booking = None

        for table_booking in table_bookings:

            if table_booking.booking_date == today:

                booking_start = table_booking.start_time

                booking_end_datetime = (
                    datetime.combine(
                        today,
                        table_booking.start_time,
                    )
                    + timedelta(
                        hours=table_booking.duration_hours
                    )
                )

                booking_end = booking_end_datetime.time()

                if (
                    booking_start <= current_time
                    < booking_end
                ):

                    current_booking = table_booking
                    break

                if (
                    booking_start > current_time
                    and next_booking is None
                ):

                    next_booking = table_booking

            elif (
                table_booking.booking_date > today
                and next_booking is None
            ):

                next_booking = table_booking

        if current_booking:

            status = "Occupied"
            booking = current_booking

        elif next_booking:

            status = "Booked Later"
            booking = next_booking

        else:

            status = "Available"
            booking = None

        table_statuses.append(
            {
                "table": table,
                "status": status,
                "booking": booking,
                "customer_name": (
                    booking.customer_name
                    if booking
                    else None
                ),
                "start_time": (
                    booking.start_time
                    if booking
                    else None
                ),
                "end_time": (
                    (
                        datetime.combine(
                            booking.booking_date,
                            booking.start_time,
                        )
                        + timedelta(
                            hours=booking.duration_hours,
                        )
                    ).time()
                    if booking
                    else None
                ),
            }
        )

    occupied_table_count = sum(
        1
        for item in table_statuses
        if item["status"] == "Occupied"
    )

    booked_later_table_count = sum(
        1
        for item in table_statuses
        if item["status"] == "Booked Later"
    )

    available_table_count = sum(
        1
        for item in table_statuses
        if item["status"] == "Available"
    )

    # Mark confirmed bookings so the dashboard can show completion
    # only when the scheduled session has actually ended.
    current_local_naive = timezone.localtime().replace(tzinfo=None)

    for dashboard_booking in all_bookings:
        dashboard_booking.can_complete = False

        if dashboard_booking.status == "Confirmed":
            dashboard_booking_end = (
                datetime.combine(
                    dashboard_booking.booking_date,
                    dashboard_booking.start_time,
                )
                + timedelta(
                    hours=dashboard_booking.duration_hours,
                )
            )

            dashboard_booking.can_complete = (
                dashboard_booking_end <= current_local_naive
            )

    return render(
        request,
        "admin_dashboard.html",
        {
            "today": today,
            "current_time": current_time,
            "dashboard_updated_at": dashboard_updated_at,
            "booking_trend": booking_trend,
            "has_booking_trend": bool(highest_daily_booking_count),
            "today_bookings": today_bookings,
            "today_booking_count": confirmed_today.count(),
            "today_status_counts": {
                "Confirmed": today_bookings.filter(
                    status="Confirmed"
                ).count(),
                "Cancelled": today_bookings.filter(
                    status="Cancelled"
                ).count(),
                "Completed": today_bookings.filter(
                    status="Completed"
                ).count(),
                "Pending": today_bookings.filter(
                    status="Pending"
                ).count(),
                "Total": today_bookings.count(),
            },
            "today_revenue": today_revenue,
            "completed_today_revenue": completed_today_revenue,
            "completed_today_count": completed_today.count(),
            "cancelled_today_count": cancelled_today.count(),
            "upcoming_bookings": upcoming_bookings,
            "upcoming_booking_count": upcoming_bookings.count(),
            "all_bookings": all_bookings,
            "active_tables": active_tables,
            "occupied_table_count": occupied_table_count,
            "booked_later_table_count": booked_later_table_count,
            "available_table_count": available_table_count,
            "table_statuses": table_statuses,
            "academy_settings": AcademySettings.objects.first(),
        },
    )


def coaching(request):

    coaching_content = CoachingContent.objects.filter(
        is_active=True
    ).order_by(
        "display_order",
        "id",
    )

    return render(
        request,
        "coaching.html",
        {
            "coaching_content": coaching_content,
        },
    )


def membership(request):

    membership_content = MembershipContent.objects.filter(
        is_active=True
    ).order_by(
        "display_order",
        "id",
    )

    return render(
        request,
        "membership.html",
        {
            "membership_content": membership_content,
        },
    )


def tournaments(request):

    tournament_content = TournamentContent.objects.filter(
        is_active=True
    ).order_by(
        "display_order",
        "tournament_date",
        "id",
    )

    return render(
        request,
        "tournaments.html",
        {
            "tournament_content": tournament_content,
        },
    )


def gallery(request):

    gallery_images = GalleryImage.objects.filter(
        is_active=True
    ).order_by(
        "display_order",
        "id",
    )

    return render(
        request,
        "gallery.html",
        {
            "gallery_images": gallery_images,
        },
    )


def contact(request):

    return render(
        request,
        "contact.html",
    )
