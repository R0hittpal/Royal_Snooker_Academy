from django.contrib.admin.models import CHANGE, LogEntry


def log_booking_status_change(user, booking, old_status, new_status):
    """Record a staff booking status transition in Django's admin history."""

    if not getattr(user, "is_authenticated", False) or not user.pk:
        return None

    return LogEntry.objects.log_actions(
        user_id=user.pk,
        queryset=[booking],
        action_flag=CHANGE,
        change_message=(
            f"Booking status changed from {old_status} to {new_status}."
        ),
        single_object=True,
    )
