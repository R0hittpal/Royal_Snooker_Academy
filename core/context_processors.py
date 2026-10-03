from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking, BookingEmailNotification, SiteSettings, Table


def site_settings(request):
    settings = SiteSettings.objects.first()

    return {
        "site_settings": settings,
    }
def owner_admin_dashboard(request):
    """Provide simple, current-day shortcuts for the Django Admin home."""
    if (
        not request.user.is_authenticated
        or not request.user.is_superuser
        or request.path_info.rstrip("/") != "/admin"
    ):
        return {}

    today = timezone.localdate()
    stale_before = timezone.now() - timedelta(minutes=15)
    needs_attention = BookingEmailNotification.objects.filter(
        Q(
            status__in=(
                BookingEmailNotification.DeliveryStatus.PENDING,
                BookingEmailNotification.DeliveryStatus.FAILED,
            )
        )
        | Q(
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            last_attempt_at__lte=stale_before,
        )
        | Q(
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            last_attempt_at__isnull=True,
        )
    ).count()

    return {
        "owner_admin_summary": {
            "today_bookings": Booking.objects.filter(booking_date=today).count(),
            "upcoming_bookings": Booking.objects.filter(
                booking_date__gte=today,
                status="Confirmed",
            ).count(),
            "email_attention": needs_attention,
            "active_tables": Table.objects.filter(is_active=True).count(),
            "inactive_tables": Table.objects.filter(is_active=False).count(),
            "booking_add_url": reverse("admin:bookings_booking_add"),
            "booking_list_url": reverse("admin:bookings_booking_changelist"),
            "today_bookings_url": (
                reverse("admin:bookings_booking_changelist")
                + f"?booking_date__exact={today.isoformat()}"
            ),
            "email_attention_url": (
                reverse("admin:bookings_bookingemailnotification_changelist")
                + "?delivery_attention=needs_attention"
            ),
            "tables_url": reverse("admin:bookings_table_changelist"),
            "table_schedule_url": reverse("admin:bookings_table_schedule"),
            "daily_print_url": (
                reverse("admin:bookings_booking_daily_print")
                + f"?date={today.isoformat()}"
            ),
        }
    }
