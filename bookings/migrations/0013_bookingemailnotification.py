from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0012_coachingcontent_price"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingEmailNotification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("confirmation", "Confirmation"),
                            ("cancellation", "Cancellation"),
                            ("completion", "Completion"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("sending", "Sending"),
                            ("sent", "Sent"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("recipient_email", models.EmailField(max_length=254)),
                ("subject", models.CharField(max_length=255)),
                ("plain_message", models.TextField()),
                ("html_message", models.TextField()),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "last_attempt_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_notifications",
                        to="bookings.booking",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("booking", "notification_type"),
                        name="booking_email_booking_type_uniq",
                    ),
                ],
            },
        ),
    ]
