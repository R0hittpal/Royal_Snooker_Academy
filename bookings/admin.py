from django.contrib import admin
from django.contrib import messages

from .models import (
    AcademySettings,
    Booking,
    CoachingContent,
    GalleryImage,
    HomePageSettings,
    MembershipContent,
    SiteSettings,
    Table,
    TournamentContent,
)


@admin.register(AcademySettings)
class AcademySettingsAdmin(admin.ModelAdmin):

    list_display = (
        "opening_time",
        "closing_time",
    )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):

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
                ),
            },
        ),
    )


@admin.register(HomePageSettings)
class HomePageSettingsAdmin(admin.ModelAdmin):

    fieldsets = (
        (
            "Hero Section",
            {
                "fields": (
                    "hero_title",
                    "hero_description",
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


@admin.register(CoachingContent)
class CoachingContentAdmin(admin.ModelAdmin):

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
class MembershipContentAdmin(admin.ModelAdmin):

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
class TournamentContentAdmin(admin.ModelAdmin):

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

    list_display = (
        "title",
        "image",
        "display_order",
        "is_active",
        "created_at",
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
    )


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "table_type",
        "hourly_rate",
        "is_active",
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


@admin.action(description="Mark selected bookings as Confirmed")
def mark_confirmed(modeladmin, request, queryset):

    updated = queryset.filter(
        status="Pending"
    ).update(
        status="Confirmed"
    )

    modeladmin.message_user(
        request,
        f"{updated} pending booking(s) marked as Confirmed.",
        messages.SUCCESS,
    )


@admin.action(description="Mark selected bookings as Cancelled")
def mark_cancelled(modeladmin, request, queryset):

    updated = queryset.filter(
        status="Confirmed"
    ).update(
        status="Cancelled"
    )

    modeladmin.message_user(
        request,
        f"{updated} confirmed booking(s) marked as Cancelled.",
        messages.SUCCESS,
    )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):

    list_display = (
        "booking_reference",
        "customer_name",
        "phone",
        "table",
        "booking_date",
        "start_time",
        "duration_hours",
        "amount",
        "status",
        "created_at",
    )

    list_filter = (
        "booking_date",
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
