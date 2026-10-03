import csv
import io
import tempfile
from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admin import (
    DeliveryAttentionFilter,
    mark_cancelled,
    mark_confirmed,
    retry_email_deliveries,
)
from .forms import BookingAdminForm
from .models import (
    AcademySettings,
    Booking,
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


class BookingAdminFormTests(TestCase):
    def setUp(self):
        AcademySettings.objects.create(
            opening_time=time(10),
            closing_time=time(23),
        )
        self.table = Table.objects.create(
            name="Table 1",
            table_type="Professional",
            hourly_rate=Decimal("20.00"),
        )
        self.booking_date = timezone.localdate() + timedelta(days=2)
        self.form_data = {
            "table": self.table.pk,
            "customer_name": "Test Customer",
            "phone": "1234567890",
            "email": "customer@example.com",
            "booking_date": self.booking_date.isoformat(),
            "start_time": "10:00",
            "duration_hours": 2,
            "amount": "40.00",
            "status": "Confirmed",
        }

    def test_accepts_valid_booking_with_correct_price(self):
        form = BookingAdminForm(data=self.form_data)

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_amount_that_does_not_match_table_rate(self):
        form = BookingAdminForm(
            data={**self.form_data, "amount": "39.00"}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

    def test_rejects_inactive_table_for_new_booking(self):
        self.table.is_active = False
        self.table.save(update_fields=["is_active"])

        form = BookingAdminForm(data=self.form_data)

        self.assertFalse(form.is_valid())
        self.assertIn("table", form.errors)

    def test_rejects_overlapping_confirmed_booking(self):
        Booking.objects.create(
            table=self.table,
            customer_name="Existing Customer",
            phone="0987654321",
            email="existing@example.com",
            booking_date=self.booking_date,
            start_time=time(11),
            duration_hours=1,
            amount=Decimal("20.00"),
            status="Confirmed",
        )

        form = BookingAdminForm(data=self.form_data)

        self.assertFalse(form.is_valid())
        self.assertIn("start_time", form.errors)


class BookingAdminCreationFlowTests(TestCase):
    def setUp(self):
        AcademySettings.objects.create(
            opening_time=time(10),
            closing_time=time(23),
        )
        self.table = Table.objects.create(
            name="Admin Booking Table",
            table_type="Professional",
            hourly_rate=Decimal("45.00"),
        )
        self.owner = get_user_model().objects.create_superuser(
            username="booking-creation-owner",
            email="owner@example.com",
            password="test-password",
        )
        self.client.force_login(self.owner)

    def booking_payload(self, **overrides):
        return {
            "table": str(self.table.pk),
            "customer_name": "Admin Customer",
            "phone": "9876543210",
            "email": "customer@example.com",
            "booking_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "start_time": "10:00:00",
            "duration_hours": "1",
            "amount": "45.00",
            "email_notifications-TOTAL_FORMS": "0",
            "email_notifications-INITIAL_FORMS": "0",
            "email_notifications-MIN_NUM_FORMS": "0",
            "email_notifications-MAX_NUM_FORMS": "1000",
            **overrides,
        }

    @patch("core.views.send_rsa_html_email")
    def test_admin_creation_saves_booking_and_sends_confirmation_after_commit(self, send_email):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                reverse("admin:bookings_booking_add"),
                self.booking_payload(),
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(callbacks), 1)
        booking = Booking.objects.get()
        self.assertEqual(booking.status, "Confirmed")
        self.assertEqual(booking.amount, Decimal("45.00"))
        notification = booking.email_notifications.get()
        self.assertEqual(
            notification.notification_type,
            BookingEmailNotification.NotificationType.CONFIRMATION,
        )
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.SENT)
        send_email.assert_called_once()


    @patch("core.views.send_rsa_html_email")
    def test_admin_creation_rejects_overlap_without_saving_or_sending(self, send_email):
        Booking.objects.create(
            table=self.table,
            customer_name="Existing Customer",
            phone="9876543210",
            email="existing@example.com",
            booking_date=timezone.localdate() + timedelta(days=2),
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("45.00"),
            status="Confirmed",
        )

        response = self.client.post(
            reverse("admin:bookings_booking_add"),
            self.booking_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertContains(response, "already booked")
        send_email.assert_not_called()


class OwnerAdminUsabilityTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser(
            username="rsa-usability-owner",
            email="owner@example.com",
            password="owner-password",
        )
        self.client.force_login(self.owner)
        self.table = Table.objects.create(
            name="Usability Table",
            table_type="Professional",
            hourly_rate=Decimal("25.00"),
        )

    def make_booking(self, booking_date):
        return Booking.objects.create(
            table=self.table,
            customer_name="Admin usability customer",
            phone="9876543210",
            email="customer@example.com",
            booking_date=booking_date,
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("25.00"),
            status="Confirmed",
        )

    def test_booking_date_shortcut_shows_only_today(self):
        today_booking = self.make_booking(timezone.localdate())
        self.make_booking(timezone.localdate() + timedelta(days=1))

        response = self.client.get(
            reverse("admin:bookings_booking_changelist"),
            {"booking_window": "today"},
        )

        self.assertEqual(response.status_code, 200)
        shown_ids = {booking.pk for booking in response.context["cl"].result_list}
        self.assertEqual(shown_ids, {today_booking.pk})

    def test_daily_print_page_shows_only_the_selected_date(self):
        report_date = timezone.localdate() + timedelta(days=2)
        included = self.make_booking(report_date)
        self.make_booking(report_date + timedelta(days=1))

        response = self.client.get(
            reverse("admin:bookings_booking_daily_print"),
            {"date": report_date.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily bookings")
        self.assertContains(response, included.customer_name)
        self.assertContains(response, included.booking_reference)
        self.assertContains(response, included.phone)
        self.assertContains(response, "Print this page")
        self.assertNotContains(response, (report_date + timedelta(days=1)).isoformat())

    def test_booking_reference_search_finds_the_matching_booking(self):
        booking = self.make_booking(timezone.localdate() + timedelta(days=2))

        response = self.client.get(
            reverse("admin:bookings_booking_changelist"),
            {"q": booking.booking_reference},
        )

        self.assertEqual(response.status_code, 200)
        shown_ids = {row.pk for row in response.context["cl"].result_list}
        self.assertEqual(shown_ids, {booking.pk})
        self.assertContains(response, "Search by customer name, phone, email, table, or booking reference.")

    def test_booking_detail_shows_customer_history_and_contact_actions(self):
        current = self.make_booking(timezone.localdate() + timedelta(days=3))
        earlier = self.make_booking(timezone.localdate() - timedelta(days=1))
        upcoming = self.make_booking(timezone.localdate() + timedelta(days=1))

        response = self.client.get(
            reverse("admin:bookings_booking_change", args=[current.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, earlier.booking_reference)
        self.assertContains(response, upcoming.booking_reference)
        self.assertContains(response, "data-copy-phone=\"9876543210\"")
        self.assertContains(response, "https://wa.me/")
        self.assertContains(response, "admin_booking_contact.js")

    def test_table_overview_shows_confirmed_bookings_today(self):
        today_booking = self.make_booking(timezone.localdate())

        response = self.client.get(reverse("admin:bookings_table_changelist"))

        self.assertEqual(response.status_code, 200)
        table_rows = {
            table.pk: table
            for table in response.context["cl"].result_list
        }
        self.assertEqual(
            table_rows[today_booking.table_id].confirmed_bookings_today_count,
            1,
        )

    def test_visual_table_schedule_marks_confirmed_pending_and_free_slots(self):
        schedule_date = timezone.localdate() + timedelta(days=2)
        confirmed = Booking.objects.create(
            table=self.table,
            customer_name="Visual schedule confirmed",
            phone="9876543210",
            email="customer@example.com",
            booking_date=schedule_date,
            start_time=time(11),
            duration_hours=2,
            amount=Decimal("50.00"),
            status="Confirmed",
        )
        Booking.objects.create(
            table=self.table,
            customer_name="Visual schedule pending",
            phone="9876543211",
            email="pending@example.com",
            booking_date=schedule_date,
            start_time=time(14),
            duration_hours=1,
            amount=Decimal("25.00"),
            status="Pending",
        )

        response = self.client.get(
            reverse("admin:bookings_table_schedule"),
            {"date": schedule_date.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        row = response.context["table_rows"][0]
        self.assertEqual(row["cells"][0]["state"], "free")
        self.assertEqual(row["cells"][1]["state"], "booked")
        self.assertEqual(row["cells"][2]["state"], "booked")
        self.assertEqual(row["cells"][3]["state"], "free")
        self.assertEqual(row["cells"][4]["state"], "pending")
        self.assertEqual(row["cells"][1]["events"][0]["reference"], confirmed.booking_reference)
        self.assertContains(response, "Visual table schedule")
        self.assertContains(response, "Only confirmed bookings block a table")

    def test_content_settings_forms_include_live_preview_and_script(self):
        site_settings = SiteSettings.objects.create(
            academy_name="Royal Snooker Academy",
            tagline="A premium place to play",
        )
        response = self.client.get(
            reverse(
                "admin:bookings_sitesettings_change",
                args=[site_settings.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-title-field=\"academy_name\"")
        self.assertContains(response, "admin_content_preview.js")

        home_settings = HomePageSettings.objects.create()
        home_response = self.client.get(
            reverse(
                "admin:bookings_homepagesettings_change",
                args=[home_settings.pk],
            )
        )
        self.assertEqual(home_response.status_code, 200)
        self.assertContains(home_response, "Homepage hero")

        coaching = CoachingContent.objects.create(
            title="Beginner lessons",
            description="Friendly coaching for new players.",
        )
        coaching_response = self.client.get(
            reverse("admin:bookings_coachingcontent_change", args=[coaching.pk])
        )
        self.assertEqual(coaching_response.status_code, 200)
        self.assertContains(coaching_response, "Friendly coaching for new players.")
        self.assertContains(coaching_response, "Use a short title")

        membership = MembershipContent.objects.create(
            title="Monthly membership",
            description="Practice during the month.",
            duration="1 month",
        )
        membership_response = self.client.get(
            reverse("admin:bookings_membershipcontent_change", args=[membership.pk])
        )
        self.assertContains(membership_response, "Check the price and duration")

        tournament = TournamentContent.objects.create(
            title="Academy tournament",
            description="Monthly event for members.",
        )
        tournament_response = self.client.get(
            reverse("admin:bookings_tournamentcontent_change", args=[tournament.pk])
        )
        self.assertContains(tournament_response, "Enter the event date")

    def test_gallery_admin_shows_upload_guidance_preview_and_thumbnail(self):
        add_response = self.client.get(reverse("admin:bookings_galleryimage_add"))
        self.assertEqual(add_response.status_code, 200)
        self.assertContains(add_response, "A 4:3 image")
        self.assertContains(add_response, "Choose an image to preview it here.")
        self.assertContains(add_response, "admin_gallery_preview.js")

        png_1x1 = b"gallery-image-content"
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                GalleryImage.objects.create(
                    title="Practice table",
                    image=SimpleUploadedFile(
                        "practice-table.png",
                        png_1x1,
                        content_type="image/png",
                    ),
                )
                list_response = self.client.get(
                    reverse("admin:bookings_galleryimage_changelist")
                )

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "rsa-gallery-admin-thumbnail")
        self.assertContains(list_response, "practice-table.png")

    def test_opening_hours_admin_explains_and_previews_customer_hours(self):
        hours = AcademySettings.objects.create(
            opening_time=time(9, 30),
            closing_time=time(22, 0),
        )

        response = self.client.get(
            reverse("admin:bookings_academysettings_change", args=[hours.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use the 24-hour clock")
        self.assertContains(response, "First time customers can start a booking")
        self.assertContains(response, "9:30 AM to 10:00 PM")
        self.assertContains(response, "Available every day")
        self.assertContains(response, "admin_opening_hours_preview.js")


class SingletonSettingsAdminTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/admin/")
        self.request.user = get_user_model()(
            is_staff=True,
            is_superuser=True,
        )
        self.singleton_models = (
            AcademySettings,
            SiteSettings,
            HomePageSettings,
        )

    def test_singleton_settings_cannot_be_deleted_from_admin(self):
        for model in self.singleton_models:
            with self.subTest(model=model.__name__):
                model_admin = admin.site._registry[model]
                self.assertFalse(model_admin.has_delete_permission(self.request))

    def test_existing_singleton_settings_cannot_be_added_again(self):
        AcademySettings.objects.create()
        SiteSettings.objects.create()
        HomePageSettings.objects.create()

        for model in self.singleton_models:
            with self.subTest(model=model.__name__):
                model_admin = admin.site._registry[model]
                self.assertFalse(model_admin.has_add_permission(self.request))


class BookingAdminActionTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(
            name="Table 3",
            table_type="Professional",
            hourly_rate=Decimal("30.00"),
        )
        self.request = RequestFactory().post("/admin/")
        self.request.user = get_user_model().objects.create_superuser(
            username="booking-admin-actions",
            email="admin@example.com",
            password="test-password",
        )
        self.request.session = {}
        self.request._messages = FallbackStorage(self.request)

    def make_booking(self, *, status):
        return Booking.objects.create(
            table=self.table,
            customer_name="Admin Action Customer",
            phone="9876543210",
            email="customer@example.com",
            booking_date=timezone.localdate() + timedelta(days=3),
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("30.00"),
            status=status,
        )

    @staticmethod
    def make_notification(booking, *, status, notification_type=None):
        return BookingEmailNotification.objects.create(
            booking=booking,
            notification_type=(
                notification_type
                or BookingEmailNotification.NotificationType.CONFIRMATION
            ),
            status=status,
            recipient_email=booking.email,
            subject="Saved subject",
            plain_message="Saved text",
            html_message="<p>Saved HTML</p>",
        )

    @patch("core.views.send_rsa_html_email")
    def test_confirm_action_updates_only_pending_and_sends_confirmation(self, send_email):
        pending = self.make_booking(status="Pending")
        cancelled = self.make_booking(status="Cancelled")
        model_admin = admin.site._registry[Booking]

        mark_confirmed(
            model_admin,
            self.request,
            Booking.objects.filter(pk__in=[pending.pk, cancelled.pk]),
        )

        pending.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual(pending.status, "Confirmed")
        self.assertEqual(cancelled.status, "Cancelled")
        notification = pending.email_notifications.get()
        self.assertEqual(
            notification.notification_type,
            BookingEmailNotification.NotificationType.CONFIRMATION,
        )
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.SENT)
        audit_entry = LogEntry.objects.get(
            user=self.request.user,
            object_id=str(pending.pk),
            content_type__app_label="bookings",
            content_type__model="booking",
            action_flag=CHANGE,
        )
        self.assertEqual(
            audit_entry.change_message,
            "Booking status changed from Pending to Confirmed.",
        )
        send_email.assert_called_once()

    @patch("core.views.send_rsa_html_email")
    def test_cancel_action_updates_only_confirmed_and_sends_cancellation(self, send_email):
        self.request.POST = {"confirm_booking_cancellation": "yes"}
        confirmed = self.make_booking(status="Confirmed")
        pending = self.make_booking(status="Pending")
        model_admin = admin.site._registry[Booking]

        mark_cancelled(
            model_admin,
            self.request,
            Booking.objects.filter(pk__in=[confirmed.pk, pending.pk]),
        )

        confirmed.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(confirmed.status, "Cancelled")
        self.assertEqual(pending.status, "Pending")
        notification = confirmed.email_notifications.get()
        self.assertEqual(
            notification.notification_type,
            BookingEmailNotification.NotificationType.CANCELLATION,
        )
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.SENT)
        audit_entry = LogEntry.objects.get(
            user=self.request.user,
            object_id=str(confirmed.pk),
            content_type__app_label="bookings",
            content_type__model="booking",
            action_flag=CHANGE,
        )
        self.assertEqual(
            audit_entry.change_message,
            "Booking status changed from Confirmed to Cancelled.",
        )
        send_email.assert_called_once()

    def test_cancel_action_shows_confirmation_without_changing_bookings(self):
        confirmed = self.make_booking(status="Confirmed")
        model_admin = admin.site._registry[Booking]

        response = mark_cancelled(
            model_admin,
            self.request,
            Booking.objects.filter(pk=confirmed.pk),
        )

        self.assertEqual(response.template_name, "admin/bookings/booking/confirm_cancellation.html")
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, "Confirmed")
        self.assertContains(response, "customers will be emailed")

    @patch("core.views.send_rsa_html_email")
    def test_retry_action_retries_failed_delivery_and_skips_sent_delivery(self, send_email):
        booking = self.make_booking(status="Confirmed")
        failed = self.make_notification(
            booking,
            status=BookingEmailNotification.DeliveryStatus.FAILED,
        )
        already_sent = self.make_notification(
            booking,
            status=BookingEmailNotification.DeliveryStatus.SENT,
            notification_type=BookingEmailNotification.NotificationType.CANCELLATION,
        )
        model_admin = admin.site._registry[BookingEmailNotification]

        retry_email_deliveries(
            model_admin,
            self.request,
            BookingEmailNotification.objects.filter(
                pk__in=[failed.pk, already_sent.pk]
            ),
        )

        failed.refresh_from_db()
        already_sent.refresh_from_db()
        self.assertEqual(failed.status, BookingEmailNotification.DeliveryStatus.SENT)
        self.assertEqual(already_sent.status, BookingEmailNotification.DeliveryStatus.SENT)
        self.assertEqual(failed.attempt_count, 1)
        self.assertEqual(already_sent.attempt_count, 0)
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.kwargs["subject"], "Saved subject")


class BookingEmailNotificationAdminTests(TestCase):
    def setUp(self):
        table = Table.objects.create(
            name="Table 4",
            table_type="Professional",
            hourly_rate=Decimal("35.00"),
        )
        self.booking = Booking.objects.create(
            table=table,
            customer_name="Email Admin Customer",
            phone="9876543210",
            email="customer@example.com",
            booking_date=timezone.localdate() + timedelta(days=1),
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("35.00"),
            status="Confirmed",
        )
        self.model_admin = admin.site._registry[BookingEmailNotification]
        self.request = RequestFactory().get("/admin/")

    def make_notification(self, *, notification_type, status, last_attempt_at=None):
        return BookingEmailNotification.objects.create(
            booking=self.booking,
            notification_type=notification_type,
            status=status,
            recipient_email=self.booking.email,
            subject="Delivery test",
            plain_message="Test message",
            html_message="<p>Test message</p>",
            last_attempt_at=last_attempt_at,
            last_error="",
        )

    def test_stalled_filter_matches_only_old_or_unclaimed_sending_deliveries(self):
        stale_sending = self.make_notification(
            notification_type=BookingEmailNotification.NotificationType.CONFIRMATION,
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            last_attempt_at=timezone.now() - timedelta(minutes=20),
        )
        unclaimed_sending = self.make_notification(
            notification_type=BookingEmailNotification.NotificationType.CANCELLATION,
            status=BookingEmailNotification.DeliveryStatus.SENDING,
        )
        recent_sending = self.make_notification(
            notification_type=BookingEmailNotification.NotificationType.COMPLETION,
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            last_attempt_at=timezone.now() - timedelta(minutes=2),
        )

        request = RequestFactory().get("/admin/?delivery_attention=stalled")
        delivery_filter = DeliveryAttentionFilter(
            request,
            request.GET.copy(),
            BookingEmailNotification.objects.all(),
            self.model_admin,
        )
        stalled_ids = set(
            delivery_filter.queryset(
                request,
                BookingEmailNotification.objects.all(),
            ).values_list("pk", flat=True)
        )

        self.assertEqual(stalled_ids, {stale_sending.pk, unclaimed_sending.pk})
        self.assertNotIn(recent_sending.pk, stalled_ids)

    def test_delivery_health_highlights_stalled_rows_and_error_summary_is_concise(self):
        notification = self.make_notification(
            notification_type=BookingEmailNotification.NotificationType.CONFIRMATION,
            status=BookingEmailNotification.DeliveryStatus.SENDING,
            last_attempt_at=timezone.now() - timedelta(minutes=20),
        )
        notification.last_error = "Provider timeout: " + ("detail " * 30)

        health = str(self.model_admin.delivery_health(notification))
        summary = self.model_admin.last_error_summary(notification)

        self.assertIn("Stalled", health)
        self.assertIn("#FDECEC", health)
        self.assertLessEqual(len(summary), 90)
        self.assertTrue(summary.endswith("…"))

    def test_notification_detail_shows_read_only_attempt_history(self):
        notification = self.make_notification(
            notification_type=BookingEmailNotification.NotificationType.CONFIRMATION,
            status=BookingEmailNotification.DeliveryStatus.SENT,
        )
        BookingEmailDeliveryAttempt.objects.create(
            notification=notification,
            attempt_number=1,
            status=BookingEmailDeliveryAttempt.AttemptStatus.SENT,
            error_summary="",
            completed_at=timezone.now(),
        )
        owner = get_user_model().objects.create_superuser(
            username="email-history-owner",
            email="owner@example.com",
            password="test-password",
        )
        self.client.force_login(owner)

        response = self.client.get(
            reverse(
                "admin:bookings_bookingemailnotification_change",
                args=[notification.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attempt number")
        self.assertContains(response, "Sent")

    def test_booking_inline_links_to_delivery_details_and_filtered_retry_list(self):
        notification = self.make_notification(
            notification_type=BookingEmailNotification.NotificationType.CONFIRMATION,
            status=BookingEmailNotification.DeliveryStatus.FAILED,
        )
        inline_class = admin.site._registry[Booking].inlines[0]
        inline = inline_class(Booking, admin.site)

        links = str(inline.delivery_links(notification))

        self.assertIn(
            reverse(
                "admin:bookings_bookingemailnotification_change",
                args=[notification.pk],
            ),
            links,
        )
        self.assertIn(
            reverse("admin:bookings_bookingemailnotification_changelist")
            + f"?booking__id__exact={self.booking.pk}",
            links,
        )
        self.assertIn("Review or retry", links)


class BookingAuditLogAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_superuser(
            username="rsa-owner-audit",
            email="owner@example.com",
            password="test-password",
        )
        table = Table.objects.create(
            name="Audit Table",
            table_type="Professional",
            hourly_rate=Decimal("40.00"),
        )
        self.booking = Booking.objects.create(
            table=table,
            customer_name="Audit Customer",
            phone="9876543210",
            email="customer@example.com",
            booking_date=timezone.localdate() + timedelta(days=2),
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("40.00"),
            status="Confirmed",
        )
        self.booking_log = LogEntry.objects.log_actions(
            user_id=self.owner.pk,
            queryset=[self.booking],
            action_flag=CHANGE,
            change_message="Booking status changed from Pending to Confirmed.",
            single_object=True,
        )
        LogEntry.objects.log_actions(
            user_id=self.owner.pk,
            queryset=[table],
            action_flag=CHANGE,
            change_message="Unrelated table update.",
            single_object=True,
        )

    def test_owner_audit_page_lists_booking_activity_only(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("admin:admin_logentry_changelist"))

        self.assertEqual(response.status_code, 200)
        result_ids = {entry.pk for entry in response.context["cl"].result_list}
        self.assertEqual(result_ids, {self.booking_log.pk})
        self.assertContains(response, "Booking status changed from Pending to Confirmed.")
        self.assertNotContains(response, "Unrelated table update.")

    def test_audit_entries_are_read_only_and_owner_only(self):
        model_admin = admin.site._registry[LogEntry]
        request = RequestFactory().get("/admin/")
        request.user = self.owner

        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

        staff_user = get_user_model().objects.create_user(
            username="non-owner-staff",
            password="test-password",
            is_staff=True,
        )
        request.user = staff_user
        self.assertFalse(model_admin.has_view_permission(request))

    def test_owner_can_export_selected_booking_activity_as_safe_csv(self):
        formula_booking = Booking.objects.create(
            table=self.booking.table,
            customer_name="=2+2",
            phone="9876543210",
            email="formula@example.com",
            booking_date=timezone.localdate() + timedelta(days=4),
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("40.00"),
            status="Confirmed",
        )
        formula_log = LogEntry.objects.log_actions(
            user_id=self.owner.pk,
            queryset=[formula_booking],
            action_flag=CHANGE,
            change_message="Booking status changed from Pending to Confirmed.",
            single_object=True,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("admin:admin_logentry_changelist"),
            {
                "action": "export_booking_activity_csv",
                "_selected_action": [str(self.booking_log.pk), str(formula_log.pk)],
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("booking-activity.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
        self.assertEqual(
            rows[0],
            ["Timestamp", "Staff user", "Booking", "Booking ID", "Activity"],
        )
        self.assertEqual(len(rows), 3)
        formula_row = next(row for row in rows[1:] if row[3] == str(formula_booking.pk))
        self.assertTrue(formula_row[2].startswith("'=2+2"))
