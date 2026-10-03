import csv
import re
from datetime import datetime, time, timedelta

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.db import models
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.dateparse import parse_date
from django.utils.html import format_html, format_html_join
from django.utils.text import Truncator
from django.utils import timezone

from .audit import log_booking_status_change
from .forms import BookingAdminForm
from .models import (
    AcademySettings,
    Booking,
    BookingCancellation,
    BookingEmailDeliveryAttempt,
    BookingEmailNotification,
    CoachingContent,
    GalleryImage,
    HomePageSettings,
    MembershipContent,
    SiteSettings,
    Table,
    TournamentContent,
)

BOOKING_EMAIL_STALE_AFTER = timedelta(minutes=15)


class AcademySettingsAdminForm(forms.ModelForm):
    class Meta:
        model = AcademySettings
        fields = "__all__"
        help_texts = {
            "opening_time": (
                "First time customers can start a booking "
                "(for example, 10:00)."
            ),
            "closing_time": (
                "Latest time a booking session can finish "
                "(for example, 23:00)."
            ),
        }


def _safe_csv_cell(value):
    value = "" if value is None else str(value)
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


class SingleRecordAdminMixin:
    """Protect singleton site settings from duplicates and deletion."""

    def has_add_permission(self, request):
        return (
            super().has_add_permission(request)
            and not self.model.objects.exists()
        )

    def has_delete_permission(self, request, obj=None):
        return False


def content_preview(title_name, title_value, text_name, text_value, label):
    """Render an admin-only, safe-text preview linked to form fields."""
    return format_html(
        '<div class="rsa-admin-preview" data-rsa-preview '
        'data-title-field="{}" data-text-field="{}">'
        '<small>{}</small><h3 data-preview-title>{}</h3>'
        '<p data-preview-text>{}</p></div>',
        title_name,
        text_name,
        label,
        title_value,
        text_value,
    )


class WebsiteContentPreviewMixin:
    readonly_fields = ("content_preview",)

    class Media:
        js = ("js/admin_content_preview.js",)

    @admin.display(description="Website preview")
    def content_preview(self, obj):
        return content_preview(
            "title",
            obj.title if obj else "Content title",
            "description",
            obj.description if obj else "The description shown to website visitors.",
            "Website preview",
        )


class BookingEmailNotificationInline(admin.TabularInline):
    model = BookingEmailNotification
    fields = (
        "notification_type",
        "recipient_email",
        "status",
        "attempt_count",
        "last_attempt_at",
        "sent_at",
        "last_error",
        "delivery_links",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Delivery links")
    def delivery_links(self, obj):
        detail_url = reverse(
            "admin:bookings_bookingemailnotification_change",
            args=[obj.pk],
        )
        booking_deliveries_url = (
            reverse("admin:bookings_bookingemailnotification_changelist")
            + f"?booking__id__exact={obj.booking_id}"
        )
        return format_html(
            '<a href="{}">Details</a> · '
            '<a href="{}">Review or retry this booking’s emails</a>',
            detail_url,
            booking_deliveries_url,
        )


class BookingCancellationInline(admin.StackedInline):
    model = BookingCancellation
    fields = (
        "requested_at",
        "expires_at",
        "used_at",
        "reason",
        "reason_details",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False


class BookingEmailDeliveryAttemptInline(admin.TabularInline):
    model = BookingEmailDeliveryAttempt
    fields = (
        "attempt_number",
        "status",
        "started_at",
        "completed_at",
        "error_summary",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AcademySettings)
class AcademySettingsAdmin(SingleRecordAdminMixin, admin.ModelAdmin):
    form = AcademySettingsAdminForm

    class Media:
        js = ("js/admin_opening_hours_preview.js",)

    fieldsets = (
        (
            "When customers can book",
            {
                "description": (
                    "These hours apply to booking availability every day. "
                    "Use the 24-hour clock when entering times."
                ),
                "fields": ("opening_time", "closing_time", "hours_preview"),
            },
        ),
    )

    list_display = (
        "opening_time",
        "closing_time",
    )

    readonly_fields = ("hours_preview",)

    @admin.display(description="Customer view preview")
    def hours_preview(self, obj):
        opening = obj.opening_time if obj else None
        closing = obj.closing_time if obj else None
        opening_label = opening.strftime("%I:%M %p").lstrip("0") if opening else "10:00 AM"
        closing_label = closing.strftime("%I:%M %p").lstrip("0") if closing else "11:00 PM"
        return format_html(
            '<div class="rsa-admin-preview rsa-hours-preview" data-rsa-hours-preview '
            'data-open-field="opening_time" data-close-field="closing_time">'
            '<small>Opening hours shown to customers</small>'
            '<h3 data-hours-range>{} to {}</h3>'
            '<p>Available every day</p></div>',
            opening_label,
            closing_label,
        )


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingleRecordAdminMixin, admin.ModelAdmin):

    class Media:
        js = ("js/admin_content_preview.js",)

    list_display = (
        "academy_name",
        "phone",
        "email",
        "whatsapp_number",
    )

    fieldsets = (
        (
            "Academy Information",
            {
                "fields": (
                    "academy_name",
                    "tagline",
                    "description",
                    "site_preview",
                ),
            },
        ),
        (
            "Contact Information",
            {
                "fields": (
                    "phone",
                    "email",
                    "whatsapp_number",
                    "address",
                    "contact_intro",
                    "contact_preview",
                ),
            },
        ),
    )

    readonly_fields = ("site_preview", "contact_preview")

    @admin.display(description="Website preview")
    def site_preview(self, obj):
        return content_preview(
            "academy_name",
            obj.academy_name if obj else "Academy name",
            "tagline",
            obj.tagline if obj else "Tagline shown on your website",
            "Academy details",
        )

    @admin.display(description="Contact page preview")
    def contact_preview(self, obj):
        return content_preview(
            "academy_name",
            obj.academy_name if obj else "Contact Royal Snooker Academy",
            "contact_intro",
            obj.contact_intro if obj else "Your contact introduction appears here.",
            "Contact introduction",
        )


@admin.register(HomePageSettings)
class HomePageSettingsAdmin(SingleRecordAdminMixin, admin.ModelAdmin):

    class Media:
        js = ("js/admin_content_preview.js",)

    fieldsets = (
        (
            "Hero Section",
            {
                "fields": (
                    "hero_title",
                    "hero_description",
                    "hero_preview",
                ),
            },
        ),
        (
            "Introduction Section",
            {
                "fields": (
                    "introduction_title",
                    "introduction_text",
                ),
            },
        ),
        (
            "Featured Section",
            {
                "fields": (
                    "featured_title",
                    "featured_text",
                ),
            },
        ),
        (
            "Homepage Statistics",
            {
                "fields": (
                    "tables_stat",
                    "coaching_stat",
                    "tournaments_stat",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                ),
            },
        ),
    )

    readonly_fields = ("hero_preview",)

    @admin.display(description="Homepage preview")
    def hero_preview(self, obj):
        return content_preview(
            "hero_title",
            obj.hero_title if obj else "Homepage heading",
            "hero_description",
            obj.hero_description if obj else "The short introduction shown to visitors.",
            "Homepage hero",
        )


@admin.register(CoachingContent)
class CoachingContentAdmin(WebsiteContentPreviewMixin, admin.ModelAdmin):

    fieldsets = (
        (
            "Coaching shown on the website",
            {
                "description": (
                    "Use a short title and explain who the lessons suit. "
                    "Keep prices current and switch off offers that are no longer available."
                ),
                "fields": (
                    "title",
                    "description",
                    "price",
                    "display_order",
                    "is_active",
                    "content_preview",
                ),
            },
        ),
    )

    list_display = (
        "title",
        "price",
        "display_order",
        "is_active",
    )

    list_editable = (
        "price",
        "display_order",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "title",
        "description",
    )

    ordering = (
        "display_order",
        "id",
    )


@admin.register(MembershipContent)
class MembershipContentAdmin(WebsiteContentPreviewMixin, admin.ModelAdmin):

    fieldsets = (
        (
            "Membership shown on the website",
            {
                "description": (
                    "Describe what members receive in everyday language. "
                    "Check the price and duration before making this offer active."
                ),
                "fields": (
                    "title",
                    "description",
                    "price",
                    "duration",
                    "display_order",
                    "is_active",
                    "content_preview",
                ),
            },
        ),
    )

    list_display = (
        "title",
        "price",
        "duration",
        "display_order",
        "is_active",
    )

    list_editable = (
        "price",
        "duration",
        "display_order",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "title",
        "description",
        "duration",
    )

    ordering = (
        "display_order",
        "id",
    )


@admin.register(TournamentContent)
class TournamentContentAdmin(WebsiteContentPreviewMixin, admin.ModelAdmin):

    fieldsets = (
        (
            "Tournament shown on the website",
            {
                "description": (
                    "Enter the event date, entry fee, and prize details carefully. "
                    "Turn off past events so visitors see current information."
                ),
                "fields": (
                    "title",
                    "description",
                    "tournament_date",
                    "entry_fee",
                    "prize_info",
                    "display_order",
                    "is_active",
                    "content_preview",
                ),
            },
        ),
    )

    list_display = (
        "title",
        "tournament_date",
        "entry_fee",
        "prize_info",
        "display_order",
        "is_active",
    )

    list_editable = (
        "tournament_date",
        "entry_fee",
        "display_order",
        "is_active",
    )

    list_filter = (
        "is_active",
        "tournament_date",
    )

    search_fields = (
        "title",
        "description",
        "prize_info",
    )

    date_hierarchy = "tournament_date"

    ordering = (
        "display_order",
        "tournament_date",
        "id",
    )


@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):

    class Media:
        js = ("js/admin_gallery_preview.js",)

    list_display = (
        "title",
        "image_thumbnail",
        "display_order",
        "is_active",
        "created_at",
    )

    formfield_overrides = {
        models.ImageField: {
            "help_text": (
                "Choose a clear landscape photo. A 4:3 image (for example, "
                "1200 × 900 pixels) usually fits the gallery best. JPG or PNG "
                "is recommended; smaller files load faster."
            ),
        },
    }

    fieldsets = (
        ("Gallery image", {"fields": ("image", "image_preview")}),
        ("Details shown on the website", {"fields": ("title", "description")}),
        ("Display", {"fields": ("display_order", "is_active", "created_at")}),
    )

    list_editable = (
        "display_order",
        "is_active",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
    )

    ordering = (
        "display_order",
        "id",
    )

    readonly_fields = (
        "created_at",
        "image_preview",
    )

    @admin.display(description="Image")
    def image_thumbnail(self, obj):
        if not obj.image:
            return "No image"
        return format_html(
            '<img class="rsa-gallery-admin-thumbnail" src="{}" alt="{}">',
            obj.image.url,
            obj.title or "Gallery image",
        )

    @admin.display(description="Preview")
    def image_preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<div class="rsa-gallery-admin-preview" data-rsa-gallery-preview>'
                '<img class="rsa-gallery-preview-image" src="{}" alt="{}">'
                "</div>",
                obj.image.url,
                obj.title or "Gallery image preview",
            )
        return format_html(
            '<div class="rsa-gallery-admin-preview" data-rsa-gallery-preview>'
            '<p class="rsa-gallery-preview-empty">{}</p></div>',
            "Choose an image to preview it here.",
        )


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):

    def get_urls(self):
        custom_urls = [
            path(
                "schedule/",
                self.admin_site.admin_view(self.schedule_view),
                name="bookings_table_schedule",
            ),
        ]
        return custom_urls + super().get_urls()

    def schedule_view(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied

        requested_date = request.GET.get("date", "")
        schedule_date = parse_date(requested_date) if requested_date else timezone.localdate()
        date_error = bool(requested_date and schedule_date is None)
        if schedule_date is None:
            schedule_date = timezone.localdate()

        academy_settings = AcademySettings.objects.first()
        opening_time = academy_settings.opening_time if academy_settings else time(10, 0)
        closing_time = academy_settings.closing_time if academy_settings else time(23, 0)
        opening_datetime = datetime.combine(schedule_date, opening_time)
        closing_datetime = datetime.combine(schedule_date, closing_time)

        from core.views import get_time_slots

        slots = []
        for public_slot in get_time_slots():
            slot_time = datetime.strptime(public_slot.value, "%H:%M").time()
            slot_start = datetime.combine(schedule_date, slot_time)
            slot_end = slot_start + timedelta(hours=1)
            if slot_start >= opening_datetime and slot_end <= closing_datetime:
                slots.append(
                    {
                        "value": public_slot.value,
                        "label": public_slot.label,
                        "start": slot_start,
                        "end": slot_end,
                    }
                )

        bookings_by_table = {}
        bookings = Booking.objects.filter(
            booking_date=schedule_date,
            status__in=("Confirmed", "Pending"),
        ).select_related("table").order_by("start_time", "table__name")
        for booking in bookings:
            bookings_by_table.setdefault(booking.table_id, []).append(booking)

        table_rows = []
        for table in Table.objects.order_by("id"):
            table_bookings = bookings_by_table.get(table.pk, [])
            cells = []
            for slot in slots:
                events = []
                for booking in table_bookings:
                    booking_start = datetime.combine(schedule_date, booking.start_time)
                    booking_end = booking_start + timedelta(hours=booking.duration_hours)
                    if booking_start < slot["end"] and booking_end > slot["start"]:
                        events.append(
                            {
                                "url": reverse("admin:bookings_booking_change", args=[booking.pk]),
                                "reference": booking.booking_reference,
                                "customer": booking.customer_name,
                                "status": booking.status,
                                "starts_here": slot["start"] <= booking_start < slot["end"],
                                "start_label": booking_start.strftime("%I:%M %p").lstrip("0"),
                                "end_label": booking_end.strftime("%I:%M %p").lstrip("0"),
                            }
                        )

                if any(event["status"] == "Confirmed" for event in events):
                    state = "booked"
                elif any(event["status"] == "Pending" for event in events):
                    state = "pending"
                else:
                    state = "free" if table.is_active else "inactive"
                cells.append({"state": state, "events": events})

            table_rows.append(
                {
                    "table": table,
                    "cells": cells,
                    "confirmed_count": sum(
                        booking.status == "Confirmed" for booking in table_bookings
                    ),
                    "pending_count": sum(
                        booking.status == "Pending" for booking in table_bookings
                    ),
                }
            )

        context = {
            **self.admin_site.each_context(request),
            "title": "Visual table schedule",
            "opts": self.model._meta,
            "schedule_date": schedule_date,
            "date_error": date_error,
            "slots": slots,
            "table_rows": table_rows,
            "booking_add_url": reverse("admin:bookings_booking_add"),
            "booking_list_url": reverse("admin:bookings_booking_changelist"),
        }
        return TemplateResponse(
            request,
            "admin/bookings/table/schedule.html",
            context,
        )

    list_display = (
        "name",
        "table_type",
        "hourly_rate",
        "is_active",
        "confirmed_bookings_today",
    )

    list_editable = (
        "hourly_rate",
        "is_active",
    )

    list_filter = (
        "table_type",
        "is_active",
    )

    search_fields = (
        "name",
        "table_type",
    )

    ordering = (
        "id",
    )

    def get_queryset(self, request):
        today = timezone.localdate()
        return super().get_queryset(request).annotate(
            confirmed_bookings_today_count=Count(
                "bookings",
                filter=Q(
                    bookings__booking_date=today,
                    bookings__status="Confirmed",
                ),
            )
        )

    @admin.display(description="Confirmed bookings today", ordering="confirmed_bookings_today_count")
    def confirmed_bookings_today(self, obj):
        return obj.confirmed_bookings_today_count

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def has_delete_permission(self, request, obj=None):
        return False


class BookingDateShortcutFilter(admin.SimpleListFilter):
    title = "booking date"
    parameter_name = "booking_window"

    def lookups(self, request, model_admin):
        return (
            ("today", "Today"),
            ("upcoming", "Upcoming"),
            ("past", "Past"),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()
        if self.value() == "today":
            return queryset.filter(booking_date=today)
        if self.value() == "upcoming":
            return queryset.filter(booking_date__gte=today)
        if self.value() == "past":
            return queryset.filter(booking_date__lt=today)
        return queryset


@admin.action(description="Mark selected bookings as Confirmed")
def mark_confirmed(modeladmin, request, queryset):

    pending_bookings = list(
        queryset.filter(
            status="Pending"
        ).select_related("table")
    )

    updated = 0
    failed_emails = 0

    from core.views import send_booking_confirmation_notification

    for booking in pending_bookings:
        with transaction.atomic():
            changed = Booking.objects.filter(
                pk=booking.pk,
                status="Pending",
            ).update(
                status="Confirmed",
            )

            if not changed:
                continue

            updated += changed
            booking.status = "Confirmed"
            log_booking_status_change(
                request.user,
                booking,
                old_status="Pending",
                new_status="Confirmed",
            )

        if not send_booking_confirmation_notification(booking):
            failed_emails += 1

    modeladmin.message_user(
        request,
        f"{updated} pending booking(s) marked as Confirmed.",
        messages.SUCCESS,
    )

    if failed_emails:
        modeladmin.message_user(
            request,
            f"Confirmation email could not be sent for {failed_emails} booking(s). "
            "See the application log for details.",
            messages.WARNING,
        )


@admin.action(description="Mark selected bookings as Cancelled")
def mark_cancelled(modeladmin, request, queryset):

    if request.POST.get("confirm_booking_cancellation") != "yes":
        return TemplateResponse(
            request,
            "admin/bookings/booking/confirm_cancellation.html",
            {
                **modeladmin.admin_site.each_context(request),
                "title": "Confirm booking cancellation",
                "opts": modeladmin.model._meta,
                "queryset": queryset.filter(status="Confirmed").select_related("table"),
                "action_name": "mark_cancelled",
                "action_index": request.POST.get("index", "0"),
            },
        )

    confirmed_bookings = list(
        queryset.filter(
            status="Confirmed"
        ).select_related("table")
    )

    updated = 0
    failed_emails = 0

    from core.views import send_booking_cancellation_notification

    for booking in confirmed_bookings:
        with transaction.atomic():
            changed = Booking.objects.filter(
                pk=booking.pk,
                status="Confirmed",
            ).update(
                status="Cancelled",
            )

            if not changed:
                continue

            updated += changed
            booking.status = "Cancelled"
            log_booking_status_change(
                request.user,
                booking,
                old_status="Confirmed",
                new_status="Cancelled",
            )

        if not send_booking_cancellation_notification(booking):
            failed_emails += 1

    modeladmin.message_user(
        request,
        f"{updated} confirmed booking(s) marked as Cancelled.",
        messages.SUCCESS,
    )

    if failed_emails:
        modeladmin.message_user(
            request,
            f"Cancellation email could not be sent for {failed_emails} booking(s). "
            "See the application log for details.",
            messages.WARNING,
        )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):

    form = BookingAdminForm
    inlines = (
        BookingEmailNotificationInline,
        BookingCancellationInline,
    )

    class Media:
        js = ("js/admin_booking_contact.js",)

    list_display = (
        "booking_reference",
        "customer_name",
        "phone_quick_actions",
        "table",
        "booking_date",
        "start_time",
        "duration_hours",
        "amount",
        "status_badge",
    )

    list_filter = (
        BookingDateShortcutFilter,
        "status",
        "table",
    )

    search_fields = (
        "customer_name",
        "phone",
        "email",
        "table__name",
    )

    date_hierarchy = "booking_date"

    ordering = (
        "booking_date",
        "start_time",
    )

    list_per_page = 25

    readonly_fields = (
        "booking_reference",
        "created_at",
        "status",
    )

    actions = (
        mark_confirmed,
        mark_cancelled,
    )

    search_help_text = (
        "Search by customer name, phone, email, table, or booking reference."
    )

    def get_inline_instances(self, request, obj=None):
        inlines = super().get_inline_instances(request, obj)
        if obj is None:
            inlines = [
                inline
                for inline in inlines
                if not isinstance(inline, BookingCancellationInline)
            ]
        return inlines

    def get_urls(self):
        custom_urls = [
            path(
                "daily-print/",
                self.admin_site.admin_view(self.daily_print_view),
                name="bookings_booking_daily_print",
            ),
        ]
        return custom_urls + super().get_urls()

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj is not None:
            contact_fields = {"phone_actions", "customer_booking_history"}
            cleaned_fieldsets = []
            for name, options in fieldsets:
                options = options.copy()
                options["fields"] = tuple(
                    field
                    for field in options["fields"]
                    if field not in contact_fields
                )
                cleaned_fieldsets.append((name, options))
            fieldsets = cleaned_fieldsets
            fieldsets.append(
                (
                    "Customer contact and history",
                    {"fields": ("phone_actions", "customer_booking_history")},
                )
            )
        return fieldsets

    @admin.display(description="Phone")
    def phone_quick_actions(self, obj):
        return format_html(
            '<span class="rsa-booking-phone">{}</span> '
            '<a class="rsa-contact-link" href="tel:{}">Call</a> '
            '<button class="rsa-copy-phone" type="button" data-copy-phone="{}" '
            'aria-label="Copy phone number {}">Copy</button>',
            obj.phone,
            obj.phone,
            obj.phone,
            obj.phone,
        )

    @admin.display(description="Contact customer")
    def phone_actions(self, obj):
        if not obj.phone:
            return "No phone number has been saved."
        digits = re.sub(r"\D", "", obj.phone)
        whatsapp_url = (
            f"https://wa.me/{digits}"
            if obj.phone.strip().startswith("+")
            else "https://wa.me/"
        )
        return format_html(
            '<div class="rsa-booking-contact-actions">'
            '<a class="btn btn-outline-success btn-sm" href="tel:{}">'
            '<i class="fas fa-phone" aria-hidden="true"></i> Call</a> '
            '<button class="btn btn-outline-secondary btn-sm rsa-copy-phone" '
            'type="button" data-copy-phone="{}">Copy number</button> '
            '<a class="btn btn-outline-success btn-sm" href="{}" '
            'target="_blank" rel="noopener">'
            '<i class="fab fa-whatsapp" aria-hidden="true"></i> Open WhatsApp</a>'
            '<small>WhatsApp opens the saved number when it includes its country code.</small>'
            '</div>',
            obj.phone,
            obj.phone,
            whatsapp_url,
        )

    @admin.display(description="Previous and upcoming bookings")
    def customer_booking_history(self, obj):
        if not obj:
            return "Save the booking to see this customer’s other bookings."

        matching = Booking.objects.filter(
            Q(phone=obj.phone) | Q(email__iexact=obj.email)
        ).exclude(pk=obj.pk).select_related("table")
        today = timezone.localdate()
        upcoming = list(
            matching.filter(booking_date__gte=today).order_by(
                "booking_date",
                "start_time",
            )[:5]
        )
        previous = list(
            matching.filter(booking_date__lt=today).order_by(
                "-booking_date",
                "-start_time",
            )[:5]
        )
        history = upcoming + previous
        if not history:
            return format_html(
                '<p class="rsa-customer-history-empty">{}</p>',
                "No other bookings were found for this phone number or email.",
            )

        rows = format_html_join(
            "",
            '<tr><td><a href="{}">{}</a></td><td>{}</td><td>{}</td>'
            "<td>{}</td><td>{}</td></tr>",
            (
                (
                    reverse("admin:bookings_booking_change", args=[booking.pk]),
                    booking.booking_reference,
                    booking.booking_date,
                    booking.start_time.strftime("%I:%M %p").lstrip("0"),
                    booking.table.name,
                    booking.get_status_display(),
                )
                for booking in history
            ),
        )
        return format_html(
            '<div class="rsa-customer-history">'
            '<p>Matched by this customer’s phone number or email. '
            'Showing up to 5 upcoming and 5 recent earlier bookings.</p>'
            '<div class="table-responsive"><table class="table table-sm table-bordered">'
            '<thead><tr><th>Reference</th><th>Date</th><th>Time</th>'
            '<th>Table</th><th>Status</th></tr></thead><tbody>{}</tbody>'
            '</table></div></div>',
            rows,
        )

    def daily_print_view(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied

        requested_date = request.GET.get("date", "")
        report_date = parse_date(requested_date) if requested_date else timezone.localdate()
        date_error = bool(requested_date and report_date is None)
        if report_date is None:
            report_date = timezone.localdate()

        bookings = Booking.objects.filter(
            booking_date=report_date,
        ).select_related("table").order_by("start_time", "table__name")
        context = {
            **self.admin_site.each_context(request),
            "title": "Daily bookings print view",
            "opts": self.model._meta,
            "report_date": report_date,
            "date_error": date_error,
            "bookings": bookings,
        }
        return TemplateResponse(
            request,
            "admin/bookings/booking/daily_print.html",
            context,
        )

    def get_search_results(self, request, queryset, search_term):
        results, may_have_duplicates = super().get_search_results(
            request,
            queryset,
            search_term,
        )
        reference_match = re.fullmatch(
            r"RSA-(\d{8})-(\d{4,})",
            search_term.strip(),
            flags=re.IGNORECASE,
        )
        if reference_match:
            try:
                reference_date = datetime.strptime(
                    reference_match.group(1),
                    "%Y%m%d",
                ).date()
                reference_id = int(reference_match.group(2))
            except ValueError:
                return results, may_have_duplicates
            results |= queryset.filter(
                pk=reference_id,
                booking_date=reference_date,
            )
        return results, may_have_duplicates

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        status_classes = {
            "Confirmed": "success",
            "Pending": "warning",
            "Cancelled": "danger",
            "Completed": "secondary",
        }
        return format_html(
            '<span class="rsa-booking-status rsa-booking-status-{}">{}</span>',
            status_classes.get(obj.status, "secondary"),
            obj.get_status_display(),
        )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is None:
            return tuple(
                field
                for field in fields
                if field != "booking_reference"
            )
        return (*fields, "phone_actions", "customer_booking_history")

    def changeform_view(
        self,
        request,
        object_id=None,
        form_url="",
        extra_context=None,
    ):
        if request.method == "POST":
            table_id = request.POST.get("table")
            if table_id:
                with transaction.atomic():
                    try:
                        Table.objects.select_for_update().get(pk=table_id)
                    except (Table.DoesNotExist, ValueError, TypeError):
                        return super().changeform_view(
                            request,
                            object_id,
                            form_url,
                            extra_context,
                        )

                    return super().changeform_view(
                        request,
                        object_id,
                        form_url,
                        extra_context,
                    )

        return super().changeform_view(
            request,
            object_id,
            form_url,
            extra_context,
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        is_new_booking = not change
        super().save_model(request, obj, form, change)

        if is_new_booking and obj.status == "Confirmed":
            from core.views import send_booking_confirmation_notification

            def send_confirmation_after_save():
                if not send_booking_confirmation_notification(obj):
                    self.message_user(
                        request,
                        "The booking was saved, but its confirmation email "
                        "could not be sent. See the application log for details.",
                        messages.WARNING,
                    )

            transaction.on_commit(send_confirmation_after_save)


@admin.action(description="Retry failed or stalled email deliveries")
def retry_email_deliveries(modeladmin, request, queryset):
    stale_before = timezone.now() - BOOKING_EMAIL_STALE_AFTER
    retryable = queryset.filter(
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
    ).select_related("booking")

    if not retryable.exists():
        modeladmin.message_user(
            request,
            "The selection contains no failed, pending, or stalled email deliveries.",
            messages.INFO,
        )
        return

    from core.views import retry_booking_email_notification

    delivered = 0
    failed = 0
    for notification in retryable:
        if retry_booking_email_notification(notification):
            delivered += 1
        else:
            failed += 1

    modeladmin.message_user(
        request,
        f"{delivered} email notification(s) delivered or already sent; "
        f"{failed} delivery attempt(s) failed.",
        messages.SUCCESS if not failed else messages.WARNING,
    )


class DeliveryAttentionFilter(admin.SimpleListFilter):
    title = "delivery attention"
    parameter_name = "delivery_attention"

    def lookups(self, request, model_admin):
        return (
            ("needs_attention", "Needs attention"),
            ("stalled", "Stalled while sending"),
        )

    def queryset(self, request, queryset):
        stale_before = timezone.now() - BOOKING_EMAIL_STALE_AFTER
        stalled = Q(
            status=BookingEmailNotification.DeliveryStatus.SENDING
        ) & (
            Q(last_attempt_at__lte=stale_before)
            | Q(last_attempt_at__isnull=True)
        )

        if self.value() == "needs_attention":
            return queryset.filter(
                Q(
                    status__in=(
                        BookingEmailNotification.DeliveryStatus.PENDING,
                        BookingEmailNotification.DeliveryStatus.FAILED,
                    )
                )
                | stalled
            )

        if self.value() == "stalled":
            return queryset.filter(stalled)

        return queryset


@admin.register(BookingEmailNotification)
class BookingEmailNotificationAdmin(admin.ModelAdmin):
    inlines = (BookingEmailDeliveryAttemptInline,)

    list_display = (
        "booking_reference",
        "notification_type",
        "recipient_email",
        "delivery_health",
        "attempt_count",
        "last_attempt_at",
        "last_error_summary",
        "sent_at",
    )
    list_filter = (
        "notification_type",
        "status",
        "booking",
        DeliveryAttentionFilter,
    )
    search_fields = (
        "booking__customer_name",
        "booking__phone",
        "booking__email",
        "recipient_email",
    )
    readonly_fields = (
        "booking",
        "notification_type",
        "status",
        "recipient_email",
        "subject",
        "attempt_count",
        "last_error",
        "created_at",
        "last_attempt_at",
        "sent_at",
    )
    fields = readonly_fields
    actions = (retry_email_deliveries,)

    @admin.display(description="Booking reference")
    def booking_reference(self, obj):
        return obj.booking.booking_reference

    @admin.display(description="Delivery health", ordering="status")
    def delivery_health(self, obj):
        status = obj.status
        stale_before = timezone.now() - BOOKING_EMAIL_STALE_AFTER
        is_stalled = status == BookingEmailNotification.DeliveryStatus.SENDING and (
            obj.last_attempt_at is None or obj.last_attempt_at <= stale_before
        )
        if is_stalled:
            label, color, background = "Stalled", "#8B1E1E", "#FDECEC"
        elif status == BookingEmailNotification.DeliveryStatus.FAILED:
            label, color, background = "Failed", "#8B1E1E", "#FDECEC"
        elif status == BookingEmailNotification.DeliveryStatus.PENDING:
            label, color, background = "Pending", "#775900", "#FFF6D8"
        elif status == BookingEmailNotification.DeliveryStatus.SENDING:
            label, color, background = "Sending", "#245A7A", "#EAF4FA"
        else:
            label, color, background = "Sent", "#17633A", "#E9F6EE"

        return format_html(
            '<span style="display:inline-block;padding:3px 8px;border-radius:12px;'
            'font-weight:600;color:{};background:{}">{}</span>',
            color,
            background,
            label,
        )

    @admin.display(description="Latest delivery error")
    def last_error_summary(self, obj):
        return Truncator(obj.last_error).chars(90) if obj.last_error else "—"

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LogEntry)
class BookingAuditLogAdmin(admin.ModelAdmin):
    """Expose booking activity to owners without permitting log edits."""

    list_display = (
        "action_time",
        "user",
        "object_repr",
        "change_details",
    )
    list_filter = (
        "user",
        "action_time",
    )
    search_fields = (
        "object_repr",
        "object_id",
        "change_message",
        "user__username",
    )
    date_hierarchy = "action_time"
    ordering = ("-action_time",)
    readonly_fields = tuple(field.name for field in LogEntry._meta.fields)
    fields = readonly_fields
    actions = ("export_booking_activity_csv",)

    @admin.action(description="Export selected booking activity as CSV")
    def export_booking_activity_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            'attachment; filename="booking-activity.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            ("Timestamp", "Staff user", "Booking", "Booking ID", "Activity")
        )

        for entry in queryset.select_related("user").order_by("action_time", "pk"):
            writer.writerow(
                _safe_csv_cell(value)
                for value in (
                    entry.action_time.isoformat(),
                    entry.user.get_username(),
                    entry.object_repr,
                    entry.object_id,
                    entry.get_change_message(),
                )
            )

        return response

    @admin.display(description="Change details")
    def change_details(self, obj):
        return obj.get_change_message()

    def get_queryset(self, request):
        booking_content_type = ContentType.objects.get_for_model(
            Booking,
            for_concrete_model=False,
        )
        return super().get_queryset(request).filter(
            content_type=booking_content_type,
        )

    def has_module_permission(self, request):
        return bool(
            request.user.is_active
            and request.user.is_superuser
        )

    def has_view_permission(self, request, obj=None):
        return bool(
            request.user.is_active
            and request.user.is_superuser
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
