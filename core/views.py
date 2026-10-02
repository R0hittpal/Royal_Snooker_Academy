from collections import namedtuple
from datetime import datetime, timedelta
from functools import wraps
import logging
import re
from email.mime.image import MIMEImage
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

logger = logging.getLogger(__name__)


from bookings.models import (
    AcademySettings,
    Booking,
    CoachingContent,
    GalleryImage,
    HomePageSettings,
    MembershipContent,
    Table,
    TournamentContent,
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
    Send a Royal Snooker Academy email with:
    - HTML version
    - Plain-text fallback
    - Optional inline RSA logo
    """

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
                    _subtype="jpeg",
                )

            logo.add_header(
                "Content-ID",
                "<rsa-logo>",
            )

            logo.add_header(
                "Content-Disposition",
                "inline",
                filename="rsa-logo.jpg",
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
        / "Royal_Snooker_Academy_Email_Logo.jpg"
    )


def build_booking_confirmation_html(
    booking,
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
                            background-color:#07100D;
                            border-bottom:1px solid #D4AF37;
                            padding:28px 24px 25px;
                        "
                    >

                        <img
                            src="cid:rsa-logo"
                            width="105"
                            alt="Royal Snooker Academy"
                            style="
                                display:block;
                                width:105px;
                                max-width:105px;
                                height:auto;
                                margin:0 auto 15px;
                                border:0;
                                outline:none;
                                text-decoration:none;
                                border-radius:50%;
                            "
                        >

                        <div
                            style="
                                color:#ffffff;
                                font-size:23px;
                                line-height:30px;
                                font-weight:800;
                                letter-spacing:0.3px;
                            "
                        >
                            Royal Snooker Academy
                        </div>

                        <div
                            style="
                                margin-top:7px;
                                color:#E7CB70;
                                font-size:12px;
                                letter-spacing:1.8px;
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
                            Hi {booking.customer_name},
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
                                        {booking.booking_reference}
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
                                    {booking.table.name}
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
                                    {booking.table.table_type}
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

                    </td>
                </tr>


                <!-- FOOTER -->
                <tr>
                    <td
                        align="center"
                        style="
                            background-color:#07100D;
                            padding:24px 24px;
                        "
                    >

                        <div
                            style="
                                color:#ffffff;
                                font-size:15px;
                                font-weight:800;
                                margin-bottom:6px;
                            "
                        >
                            Royal Snooker Academy
                        </div>

                        <div
                            style="
                                color:#AEBBB6;
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
                            background-color:#07100D;
                            border-bottom:1px solid #D4AF37;
                            padding:28px 24px 25px;
                        "
                    >

                        <img
                            src="cid:rsa-logo"
                            width="105"
                            alt="Royal Snooker Academy"
                            style="
                                display:block;
                                width:105px;
                                max-width:105px;
                                height:auto;
                                margin:0 auto 16px;
                                border:0;
                                outline:none;
                                text-decoration:none;
                                border-radius:50%;
                            "
                        >

                        <div
                            style="
                                color:#ffffff;
                                font-size:22px;
                                line-height:29px;
                                font-weight:800;
                            "
                        >
                            Royal Snooker Academy
                        </div>

                        <div
                            style="
                                margin-top:6px;
                                color:#E7CB70;
                                font-size:11px;
                                letter-spacing:2px;
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
                            Hi {booking.customer_name},<br>
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
                                            color:#07100D;
                                            font-size:18px;
                                            line-height:25px;
                                            font-weight:800;
                                        "
                                    >
                                        {booking.table.name}
                                    </div>

                                    <div
                                        style="
                                            margin-top:4px;
                                            color:#66746F;
                                            font-size:13px;
                                        "
                                    >
                                        {booking.table.table_type}
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
                                            color:#07100D;
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
                            Amount Paid
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
                            href="{booking_url}"
                            style="
                                display:inline-block;
                                background-color:#D4AF37;
                                color:#07100D;
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
                                {booking.booking_reference}
                            </strong>
                        </div>

                    </td>
                </tr>


                <!-- FOOTER -->
                <tr>
                    <td
                        align="center"
                        style="
                            background-color:#07100D;
                            padding:24px;
                        "
                    >

                        <div
                            style="
                                color:#ffffff;
                                font-size:15px;
                                font-weight:800;
                            "
                        >
                            Royal Snooker Academy
                        </div>

                        <div
                            style="
                                margin-top:6px;
                                color:#AEBBB6;
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
            opening_time="10:00",
            closing_time="23:00",
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

        booking_reference = booking.booking_reference

        # ---------------------------------------------------------
        # BOOKING CONFIRMATION EMAIL
        # ---------------------------------------------------------

        booking_email_subject = (
            f"Booking Confirmed - {booking_reference} | "
            f"Royal Snooker Academy"
        )

        booking_plain_message = f"""
Hello {booking.customer_name},

Your snooker session at Royal Snooker Academy has been successfully reserved.

BOOKING DETAILS
------------------------------
Booking Reference : {booking.booking_reference}
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

Royal Snooker Academy
Play. Practice. Perform.
"""

        booking_html_message = build_booking_confirmation_html(
            booking
        )

        logo_path = get_rsa_email_logo_path()

        try:

            send_rsa_html_email(
                subject=booking_email_subject,
                recipient=booking.email,
                plain_message=booking_plain_message,
                html_message=booking_html_message,
                logo_path=logo_path,
            )

        except Exception as email_error:

            logger.exception(
                "Booking confirmation email could not be sent for %s: %s",
                booking_reference,
                email_error,
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

    booking.status = "Cancelled"

    booking.save(
        update_fields=["status"]
    )

    messages.success(
        request,
        f"Booking {booking.booking_reference} has been cancelled successfully.",
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

    booking.status = "Completed"

    booking.save(
        update_fields=["status"]
    )

    # ---------------------------------------------------------
    # POST-SESSION THANK-YOU EMAIL
    # ---------------------------------------------------------

    completion_email_subject = (
        f"Thank You for Visiting Royal Snooker Academy | "
        f"{booking.booking_reference}"
    )

    completion_plain_message = f"""
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
Amount Paid       : ₹{booking.amount:,.2f}

Your session has been successfully completed.

We'd love to welcome you back for another game.

Book another session:
{request.build_absolute_uri("/book/")}

Booking Reference:
{booking.booking_reference}

Royal Snooker Academy
Play. Practice. Perform.

Thank you for being part of the RSA community.
"""

    booking_url = request.build_absolute_uri("/book/")

    completion_html_message = build_completion_email_html(
        booking=booking,
        booking_url=booking_url,
    )

    logo_path = get_rsa_email_logo_path()

    try:

        send_rsa_html_email(
            subject=completion_email_subject,
            recipient=booking.email,
            plain_message=completion_plain_message,
            html_message=completion_html_message,
            logo_path=logo_path,
        )

    except Exception as email_error:

        logger.exception(
            "Completion email could not be sent for %s: %s",
            booking.booking_reference,
            email_error,
        )

    messages.success(
        request,
        f"Booking {booking.booking_reference} has been marked as completed.",
    )

    return redirect("admin_dashboard")


@manager_required
def admin_dashboard(request):

    today = timezone.localdate()
    current_time = timezone.localtime().time()

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