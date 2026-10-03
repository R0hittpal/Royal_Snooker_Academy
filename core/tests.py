from datetime import time, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import re
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import Group
from django.test import TestCase
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from django.db import close_old_connections

from bookings.models import (
    Booking,
    BookingCancellation,
    BookingEmailDeliveryAttempt,
    BookingEmailNotification,
    Table,
)
from .views import (
    retry_booking_email_notification,
    send_booking_cancellation_notification,
    send_booking_confirmation_notification,
    send_booking_completion_notification,
)


class BookingEmailDeliveryTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(
            name="Table 1",
            table_type="Professional",
            hourly_rate=Decimal("20.00"),
        )
        self.booking = Booking.objects.create(
            table=self.table,
            customer_name="Test Customer",
            phone="1234567890",
            email="customer@example.com",
            booking_date=timezone.localdate() + timedelta(days=1),
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("20.00"),
            status="Confirmed",
        )

    @patch("core.views.send_rsa_html_email")
    def test_confirmation_delivery_is_tracked_and_idempotent(self, send_email):
        self.assertTrue(send_booking_confirmation_notification(self.booking))
        self.assertTrue(send_booking_confirmation_notification(self.booking))

        send_email.assert_called_once()
        notification = BookingEmailNotification.objects.get(
            booking=self.booking,
            notification_type=BookingEmailNotification.NotificationType.CONFIRMATION,
        )
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.SENT)
        self.assertEqual(notification.attempt_count, 1)
        self.assertIsNotNone(notification.sent_at)
        self.assertEqual(notification.recipient_email, self.booking.email)
        attempt = notification.delivery_attempts.get()
        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.status, BookingEmailDeliveryAttempt.AttemptStatus.SENT)
        self.assertIsNotNone(attempt.completed_at)

    @patch("core.views.send_rsa_html_email", side_effect=RuntimeError("provider failure"))
    def test_failed_delivery_is_recorded_without_saving_exception_details(self, send_email):
        self.assertFalse(send_booking_cancellation_notification(self.booking))

        notification = BookingEmailNotification.objects.get(
            booking=self.booking,
            notification_type=BookingEmailNotification.NotificationType.CANCELLATION,
        )
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.FAILED)
        self.assertEqual(notification.attempt_count, 1)
        self.assertIn("RuntimeError", notification.last_error)
        self.assertNotIn("provider failure", notification.last_error)
        attempt = notification.delivery_attempts.get()
        self.assertEqual(attempt.status, BookingEmailDeliveryAttempt.AttemptStatus.FAILED)
        self.assertIn("RuntimeError", attempt.error_summary)
        self.assertNotIn("provider failure", attempt.error_summary)
        self.assertIsNotNone(attempt.completed_at)
        send_email.assert_called_once()

    @patch("core.views.send_rsa_html_email")
    def test_retry_sends_saved_notification_and_marks_it_sent(self, send_email):
        notification = BookingEmailNotification.objects.create(
            booking=self.booking,
            notification_type=BookingEmailNotification.NotificationType.COMPLETION,
            status=BookingEmailNotification.DeliveryStatus.FAILED,
            recipient_email=self.booking.email,
            subject="Saved subject",
            plain_message="Saved text",
            html_message="<p>Saved HTML</p>",
            attempt_count=1,
            last_error="RuntimeError",
        )
        BookingEmailDeliveryAttempt.objects.create(
            notification=notification,
            attempt_number=1,
            status=BookingEmailDeliveryAttempt.AttemptStatus.FAILED,
            started_at=timezone.now() - timedelta(minutes=2),
            completed_at=timezone.now() - timedelta(minutes=2),
            error_summary="RuntimeError. Check the application log for details.",
        )

        self.assertTrue(retry_booking_email_notification(notification))

        notification.refresh_from_db()
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.SENT)
        self.assertEqual(notification.attempt_count, 2)
        self.assertEqual(notification.last_error, "")
        attempts = list(notification.delivery_attempts.order_by("attempt_number"))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].status, BookingEmailDeliveryAttempt.AttemptStatus.FAILED)
        self.assertEqual(attempts[1].attempt_number, 2)
        attempt = attempts[1]
        self.assertEqual(attempt.attempt_number, 2)
        self.assertEqual(attempt.status, BookingEmailDeliveryAttempt.AttemptStatus.SENT)
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.kwargs["subject"], "Saved subject")
        self.assertEqual(send_email.call_args.kwargs["plain_message"], "Saved text")

    @patch("core.views.send_rsa_html_email")
    def test_completion_delivery_uses_the_completion_notification_type(self, send_email):
        self.assertTrue(
            send_booking_completion_notification(
                self.booking,
                booking_url="https://example.com/booking/complete/",
            )
        )

        notification = BookingEmailNotification.objects.get(booking=self.booking)
        self.assertEqual(
            notification.notification_type,
            BookingEmailNotification.NotificationType.COMPLETION,
        )
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.SENT)
        send_email.assert_called_once()


class BookingLifecycleViewTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(
            name="Table 2",
            table_type="Professional",
            hourly_rate=Decimal("25.00"),
        )
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            username="rsa-manager",
            password="test-password",
        )
        manager_group, _ = Group.objects.get_or_create(name="RSA Manager")
        self.manager.groups.add(manager_group)

    def booking_payload(self, **overrides):
        return {
            "table": str(self.table.pk),
            "customer_name": "Test Customer",
            "phone": "9876543210",
            "email": "customer@example.com",
            "booking_date": (timezone.localdate() + timedelta(days=3)).isoformat(),
            "start_time": "10:00",
            "duration": "2",
            **overrides,
        }

    @patch("core.views.send_rsa_html_email")
    def test_customer_booking_creates_confirmation_and_success_page(self, send_email):
        response = self.client.post(
            reverse("booking"),
            self.booking_payload(),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["success"])
        booking = Booking.objects.get()
        self.assertEqual(booking.status, "Confirmed")
        self.assertEqual(booking.amount, Decimal("50.00"))
        self.assertEqual(booking.email_notifications.count(), 1)
        self.assertEqual(
            booking.email_notifications.get().notification_type,
            BookingEmailNotification.NotificationType.CONFIRMATION,
        )
        send_email.assert_called_once()

    @patch("core.views.send_rsa_html_email")
    def test_customer_booking_rejects_overlapping_slot(self, send_email):
        booking_date = timezone.localdate() + timedelta(days=3)
        Booking.objects.create(
            table=self.table,
            customer_name="Existing Customer",
            phone="9876543210",
            email="existing@example.com",
            booking_date=booking_date,
            start_time=time(11),
            duration_hours=1,
            amount=Decimal("25.00"),
            status="Confirmed",
        )

        response = self.client.post(
            reverse("booking"),
            self.booking_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertContains(response, "already booked")
        send_email.assert_not_called()

    def make_confirmed_booking(self, **overrides):
        values = {
            "table": self.table,
            "customer_name": "Test Customer",
            "phone": "9876543210",
            "email": "customer@example.com",
            "booking_date": timezone.localdate() + timedelta(days=2),
            "start_time": time(10),
            "duration_hours": 1,
            "amount": Decimal("25.00"),
            "status": "Confirmed",
        }
        values.update(overrides)
        return Booking.objects.create(**values)

    @patch("core.views.send_rsa_html_email")
    def test_manager_cancellation_changes_status_and_emails_customer(self, send_email):
        booking = self.make_confirmed_booking()
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("cancel_booking", args=[booking.pk]),
        )

        self.assertRedirects(response, reverse("admin_dashboard"))
        booking.refresh_from_db()
        self.assertEqual(booking.status, "Cancelled")
        notification = booking.email_notifications.get()
        self.assertEqual(
            notification.notification_type,
            BookingEmailNotification.NotificationType.CANCELLATION,
        )
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.SENT)
        audit_entry = LogEntry.objects.get(
            user=self.manager,
            object_id=str(booking.pk),
            content_type__app_label="bookings",
            content_type__model="booking",
            action_flag=CHANGE,
        )
        self.assertEqual(
            audit_entry.change_message,
            "Booking status changed from Confirmed to Cancelled.",
        )
        send_email.assert_called_once()

    @patch("core.views.send_rsa_html_email")
    def test_cancellation_requires_manager_and_post(self, send_email):
        booking = self.make_confirmed_booking()

        unauthenticated = self.client.post(
            reverse("cancel_booking", args=[booking.pk]),
        )
        self.assertRedirects(
            unauthenticated,
            f"{reverse('manager_login')}?next={reverse('cancel_booking', args=[booking.pk])}",
        )
        self.client.force_login(self.manager)
        wrong_method = self.client.get(reverse("cancel_booking", args=[booking.pk]))

        self.assertEqual(wrong_method.status_code, 405)
        booking.refresh_from_db()
        self.assertEqual(booking.status, "Confirmed")
        send_email.assert_not_called()

    @patch("core.views.send_rsa_html_email")
    def test_manager_completion_requires_ended_session_then_emails_customer(self, send_email):
        future_booking = self.make_confirmed_booking(
            booking_date=timezone.localdate() + timedelta(days=1),
        )
        self.client.force_login(self.manager)

        early_response = self.client.post(
            reverse("complete_booking", args=[future_booking.pk]),
        )
        self.assertRedirects(early_response, reverse("admin_dashboard"))
        future_booking.refresh_from_db()
        self.assertEqual(future_booking.status, "Confirmed")
        send_email.assert_not_called()

        ended_booking = self.make_confirmed_booking(
            booking_date=timezone.localdate() - timedelta(days=1),
        )
        completed_response = self.client.post(
            reverse("complete_booking", args=[ended_booking.pk]),
        )

        self.assertRedirects(completed_response, reverse("admin_dashboard"))
        ended_booking.refresh_from_db()
        self.assertEqual(ended_booking.status, "Completed")
        notification = ended_booking.email_notifications.get()
        self.assertEqual(
            notification.notification_type,
            BookingEmailNotification.NotificationType.COMPLETION,
        )
        self.assertEqual(notification.status, BookingEmailNotification.DeliveryStatus.SENT)
        audit_entry = LogEntry.objects.get(
            user=self.manager,
            object_id=str(ended_booking.pk),
            content_type__app_label="bookings",
            content_type__model="booking",
            action_flag=CHANGE,
        )
        self.assertEqual(
            audit_entry.change_message,
            "Booking status changed from Confirmed to Completed.",
        )
        send_email.assert_called_once()


class CustomerBookingCancellationTests(TestCase):
    def setUp(self):
        self.table = Table.objects.create(
            name="Customer Cancellation Table",
            table_type="Professional",
            hourly_rate=Decimal("30.00"),
        )
        self.booking = Booking.objects.create(
            table=self.table,
            customer_name="Cancellation Customer",
            phone="9876543210",
            email="customer@example.com",
            booking_date=timezone.localdate() + timedelta(days=2),
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("30.00"),
            status="Confirmed",
        )

    def request_cancellation_link(self, **overrides):
        payload = {
            "booking_reference": self.booking.booking_reference,
            "email": self.booking.email,
        }
        payload.update(overrides)
        return self.client.post(
            reverse("booking_cancellation_request"),
            payload,
        )

    @patch("core.views.send_rsa_html_email")
    def test_matching_booking_email_receives_short_lived_secure_link(self, send_email):
        response = self.request_cancellation_link()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If the details match an eligible upcoming booking")
        send_email.assert_called_once()
        cancellation = BookingCancellation.objects.get(booking=self.booking)
        self.assertEqual(len(cancellation.token_digest), 64)
        self.assertIsNone(cancellation.used_at)
        self.assertLessEqual(
            cancellation.expires_at - cancellation.requested_at,
            timedelta(minutes=30),
        )
        self.assertIn("Review cancellation", send_email.call_args.kwargs["html_message"])
        self.assertIn(self.booking.booking_reference, send_email.call_args.kwargs["plain_message"])

    @patch("core.views.send_rsa_html_email")
    def test_wrong_email_does_not_disclose_booking_or_send_email(self, send_email):
        response = self.request_cancellation_link(email="someone-else@example.com")

        self.assertContains(response, "If the details match an eligible upcoming booking")
        self.assertEqual(BookingCancellation.objects.count(), 0)
        send_email.assert_not_called()

    @patch("core.views.send_rsa_html_email")
    def test_customer_confirms_other_reason_and_link_cannot_be_reused(self, send_email):
        self.request_cancellation_link()
        html_message = send_email.call_args.kwargs["html_message"]
        confirmation_url = re.search(r'href="([^"]+)"', html_message).group(1)
        confirm_path = urlsplit(confirmation_url).path

        view_response = self.client.get(confirm_path)
        self.assertEqual(view_response.status_code, 200)
        self.assertContains(view_response, "Confirm cancellation")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "Confirmed")

        invalid_response = self.client.post(
            confirm_path,
            {"reason": "other", "reason_details": "   "},
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "Please add a short note")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "Confirmed")
        self.assertEqual(send_email.call_count, 1)

        response = self.client.post(
            confirm_path,
            {
                "reason": "other",
                "reason_details": "Schedule changed unexpectedly",
            },
        )
        self.assertContains(response, "Your booking has been cancelled")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "Cancelled")
        cancellation = BookingCancellation.objects.get(booking=self.booking)
        self.assertEqual(cancellation.reason, BookingCancellation.Reason.OTHER)
        self.assertEqual(cancellation.reason_details, "Schedule changed unexpectedly")
        self.assertIsNotNone(cancellation.used_at)
        self.assertEqual(
            self.booking.email_notifications.get().notification_type,
            BookingEmailNotification.NotificationType.CANCELLATION,
        )
        self.assertEqual(send_email.call_count, 2)

        replay_response = self.client.post(
            confirm_path,
            {"reason": BookingCancellation.Reason.PLANS_CHANGED},
        )
        self.assertContains(replay_response, "This link has already been used")
        self.assertEqual(send_email.call_count, 2)

    @patch("core.views.send_rsa_html_email")
    def test_cutoff_blocks_link_request_and_confirmation(self, send_email):
        now = timezone.now()
        local_session_start = timezone.localtime(now + timedelta(hours=1))
        self.booking.booking_date = local_session_start.date()
        self.booking.start_time = local_session_start.time().replace(microsecond=0)
        self.booking.save(update_fields=["booking_date", "start_time"])

        with patch("core.views.timezone.now", return_value=now):
            response = self.request_cancellation_link()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BookingCancellation.objects.count(), 0)
        send_email.assert_not_called()

    @patch("core.views.send_rsa_html_email")
    def test_expired_link_cannot_cancel_booking(self, send_email):
        self.request_cancellation_link()
        html_message = send_email.call_args.kwargs["html_message"]
        confirmation_url = re.search(r'href="([^"]+)"', html_message).group(1)
        confirm_path = urlsplit(confirmation_url).path
        cancellation = BookingCancellation.objects.get(booking=self.booking)
        cancellation.expires_at = timezone.now() - timedelta(seconds=1)
        cancellation.save(update_fields=["expires_at"])

        response = self.client.get(confirm_path)

        self.assertContains(response, "This link has expired")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "Confirmed")


class OwnerManagerAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_superuser(
            username="rsa-owner-access",
            email="owner@example.com",
            password="owner-password",
        )
        self.manager = user_model.objects.create_user(
            username="rsa-manager-access",
            password="manager-password",
        )
        manager_group, _ = Group.objects.get_or_create(name="RSA Manager")
        self.manager.groups.add(manager_group)
        self.regular_user = user_model.objects.create_user(
            username="regular-user",
            password="regular-password",
        )

    def test_manager_login_grants_operations_center_but_not_django_admin(self):
        response = self.client.post(
            reverse("manager_login"),
            {
                "username": self.manager.username,
                "password": "manager-password",
            },
        )

        self.assertRedirects(response, reverse("admin_dashboard"))
        self.assertEqual(
            self.client.get(reverse("admin_dashboard")).status_code,
            200,
        )
        admin_response = self.client.get(reverse("admin:index"))
        self.assertEqual(admin_response.status_code, 302)
        self.assertTrue(admin_response.url.startswith(reverse("admin:login")))
        schedule_response = self.client.get(reverse("admin:bookings_table_schedule"))
        self.assertEqual(schedule_response.status_code, 302)
        self.assertTrue(schedule_response.url.startswith(reverse("admin:login")))

    def test_owner_can_access_both_admin_and_operations_center(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What would you like to do?")
        self.assertContains(response, "Add a booking")
        self.assertContains(response, "Today’s bookings")
        self.assertContains(response, "Print today’s bookings")
        self.assertContains(response, "Table overview")
        self.assertContains(response, "Visual table schedule")
        self.assertEqual(
            self.client.get(reverse("admin_dashboard")).status_code,
            200,
        )

    def test_regular_user_is_logged_out_when_trying_operations_center(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("admin_dashboard"))

        self.assertRedirects(response, reverse("manager_login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unauthenticated_operations_request_redirects_to_manager_login(self):
        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("manager_login")))
        self.assertIn("next=", response.url)


class BookingEmailRetryConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        table = Table.objects.create(
            name="Concurrent Retry Table",
            table_type="Professional",
            hourly_rate=Decimal("30.00"),
        )
        booking = Booking.objects.create(
            table=table,
            customer_name="Concurrent Retry Customer",
            phone="9876543210",
            email="customer@example.com",
            booking_date=timezone.localdate() + timedelta(days=1),
            start_time=time(10),
            duration_hours=1,
            amount=Decimal("30.00"),
            status="Confirmed",
        )
        self.notification = BookingEmailNotification.objects.create(
            booking=booking,
            notification_type=BookingEmailNotification.NotificationType.CONFIRMATION,
            status=BookingEmailNotification.DeliveryStatus.PENDING,
            recipient_email=booking.email,
            subject="Confirmation",
            plain_message="Test confirmation",
            html_message="<p>Test confirmation</p>",
        )

    @staticmethod
    def retry_from_separate_connection(notification_id):
        close_old_connections()
        try:
            notification = BookingEmailNotification.objects.get(pk=notification_id)
            return retry_booking_email_notification(notification)
        finally:
            close_old_connections()

    @patch("core.views.send_rsa_html_email")
    def test_simultaneous_retries_claim_and_send_notification_only_once(self, send_email):
        first_send_started = Event()
        allow_first_send_to_finish = Event()

        def pause_first_send(**kwargs):
            first_send_started.set()
            if not allow_first_send_to_finish.wait(timeout=10):
                raise TimeoutError("Timed out waiting to finish the test email send.")

        send_email.side_effect = pause_first_send
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_attempt = executor.submit(
                self.retry_from_separate_connection,
                self.notification.pk,
            )
            try:
                self.assertTrue(first_send_started.wait(timeout=5))
                second_attempt = executor.submit(
                    self.retry_from_separate_connection,
                    self.notification.pk,
                )
                second_result = second_attempt.result(timeout=5)
            finally:
                allow_first_send_to_finish.set()

            first_result = first_attempt.result(timeout=5)

        self.notification.refresh_from_db()
        self.assertTrue(first_result)
        self.assertFalse(second_result)
        self.assertEqual(send_email.call_count, 1)
        self.assertEqual(self.notification.attempt_count, 1)
        attempt = self.notification.delivery_attempts.get()
        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.status, BookingEmailDeliveryAttempt.AttemptStatus.SENT)
        self.assertEqual(
            self.notification.status,
            BookingEmailNotification.DeliveryStatus.SENT,
        )
