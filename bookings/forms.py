from datetime import datetime, time, timedelta

from django import forms
from django.utils import timezone

from .models import AcademySettings, Booking, BookingCancellation


class BookingAdminForm(forms.ModelForm):
    """Apply booking schedule and pricing rules in Django Admin."""

    class Meta:
        model = Booking
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        table = cleaned_data.get("table")
        booking_date = cleaned_data.get("booking_date")
        start_time = cleaned_data.get("start_time")
        duration_hours = cleaned_data.get("duration_hours")
        amount = cleaned_data.get("amount")

        schedule_fields = {
            "table",
            "booking_date",
            "start_time",
            "duration_hours",
        }
        schedule_changed = (
            not self.instance.pk
            or bool(schedule_fields.intersection(self.changed_data))
        )
        amount_changed = not self.instance.pk or "amount" in self.changed_data

        if not schedule_changed and not amount_changed:
            return cleaned_data

        if (
            table is None
            or booking_date is None
            or start_time is None
            or duration_hours is None
            or amount is None
        ):
            return cleaned_data

        if schedule_changed and not table.is_active:
            self.add_error(
                "table",
                "Select an active table for a new or rescheduled booking.",
            )

        if schedule_changed:
            if booking_date < timezone.localdate():
                self.add_error("booking_date", "You cannot book a past date.")

            if start_time.minute or start_time.second or start_time.microsecond:
                self.add_error("start_time", "Choose an available whole-hour start time.")
            elif start_time.hour not in range(10, 23):
                self.add_error("start_time", "Choose an available whole-hour start time.")

            academy_settings = AcademySettings.objects.first()
            opening_time = academy_settings.opening_time if academy_settings else time(10, 0)
            closing_time = academy_settings.closing_time if academy_settings else time(23, 0)

            start_datetime = datetime.combine(booking_date, start_time)
            end_datetime = start_datetime + timedelta(hours=duration_hours)
            opening_datetime = datetime.combine(booking_date, opening_time)
            closing_datetime = datetime.combine(booking_date, closing_time)

            if start_datetime < opening_datetime or end_datetime > closing_datetime:
                self.add_error(
                    "start_time",
                    "Selected time is outside academy operating hours.",
                )

            today = timezone.localdate()
            if booking_date == today:
                grace_deadline = timezone.make_aware(
                    start_datetime,
                    timezone.get_current_timezone(),
                ) + timedelta(minutes=15)
                if timezone.localtime() > grace_deadline:
                    self.add_error(
                        "start_time",
                        "This time slot is no longer available for booking.",
                    )

        status = (
            self.instance.status
            if self.instance.pk
            else Booking._meta.get_field("status").get_default()
        )
        if schedule_changed and status == "Confirmed":
            existing_bookings = Booking.objects.filter(
                table=table,
                booking_date=booking_date,
                status="Confirmed",
            ).exclude(pk=self.instance.pk)

            for existing_booking in existing_bookings:
                existing_start = datetime.combine(
                    booking_date,
                    existing_booking.start_time,
                )
                existing_end = existing_start + timedelta(
                    hours=existing_booking.duration_hours
                )

                if start_datetime < existing_end and end_datetime > existing_start:
                    self.add_error(
                        "start_time",
                        "This table is already booked for the selected time.",
                    )
                    break

        expected_amount = table.hourly_rate * duration_hours
        if (schedule_changed or amount_changed) and amount != expected_amount:
            self.add_error(
                "amount",
                "Amount must equal the table's hourly rate multiplied by the duration.",
            )

        return cleaned_data


class BookingCancellationLookupForm(forms.Form):
    booking_reference = forms.CharField(
        label="Booking reference",
        max_length=32,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "rsa-input",
                "autocomplete": "off",
                "placeholder": "For example, RSA-20261003-0001",
            }
        ),
    )
    email = forms.EmailField(
        label="Email used for the booking",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "rsa-input",
                "autocomplete": "email",
            }
        ),
    )


class CustomerBookingCancellationForm(forms.ModelForm):
    reason = forms.ChoiceField(
        choices=[("", "Choose a reason"), *BookingCancellation.Reason.choices],
        required=True,
        widget=forms.Select(attrs={"class": "rsa-input"}),
    )

    class Meta:
        model = BookingCancellation
        fields = ("reason", "reason_details")
        labels = {
            "reason": "Why are you cancelling?",
            "reason_details": "Please tell us a little more",
        }
        widgets = {
            "reason": forms.Select(attrs={"class": "rsa-input"}),
            "reason_details": forms.Textarea(
                attrs={
                    "class": "rsa-input",
                    "rows": 3,
                    "maxlength": 500,
                    "placeholder": "Share a short note (up to 500 characters).",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        reason = cleaned_data.get("reason")
        details = (cleaned_data.get("reason_details") or "").strip()

        if reason == BookingCancellation.Reason.OTHER and not details:
            self.add_error(
                "reason_details",
                "Please add a short note for the other reason.",
            )
        elif reason != BookingCancellation.Reason.OTHER:
            cleaned_data["reason_details"] = ""

        return cleaned_data
