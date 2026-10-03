from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class AcademySettings(models.Model):
    opening_time = models.TimeField(default="10:00")
    closing_time = models.TimeField(default="23:00")

    def __str__(self):
        return "Academy Settings"

    class Meta:
        verbose_name = "Academy Settings"
        verbose_name_plural = "Academy Settings"


class SiteSettings(models.Model):
    academy_name = models.CharField(
        max_length=150,
        default="Royal Snooker Academy",
    )

    tagline = models.CharField(
        max_length=255,
        default="Premium Snooker Tables & Professional Coaching",
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    whatsapp_number = models.CharField(
        max_length=30,
        blank=True,
    )

    address = models.TextField(
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    contact_intro = models.TextField(
        blank=True,
        default=(
            "Have a question about table bookings, coaching, "
            "memberships or tournaments? Get in touch with us."
        ),
    )

    def __str__(self):
        return self.academy_name

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"


class HomePageSettings(models.Model):
    hero_title = models.CharField(
        max_length=200,
        default="Premium Snooker Experience",
    )

    hero_description = models.TextField(
        default=(
            "Experience premium snooker tables, professional coaching "
            "and a welcoming environment at Royal Snooker Academy."
        ),
    )

    introduction_title = models.CharField(
        max_length=200,
        default="Welcome to Royal Snooker Academy",
    )

    introduction_text = models.TextField(
        default=(
            "Royal Snooker Academy provides a professional and comfortable "
            "environment for players of all skill levels."
        ),
    )

    featured_title = models.CharField(
        max_length=200,
        default="Everything You Need to Play Better",
    )

    featured_text = models.TextField(
        default=(
            "Book premium tables, improve your game with professional "
            "coaching, participate in tournaments and enjoy a great "
            "snooker experience."
        ),
    )

    tables_stat = models.PositiveIntegerField(
        default=5,
    )

    coaching_stat = models.CharField(
        max_length=50,
        default="Professional",
    )

    tournaments_stat = models.CharField(
        max_length=50,
        default="Regular",
    )

    is_active = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return "Home Page Settings"

    class Meta:
        verbose_name = "Home Page Settings"
        verbose_name_plural = "Home Page Settings"


class CoachingContent(models.Model):
    title = models.CharField(
        max_length=150,
    )

    description = models.TextField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    display_order = models.PositiveIntegerField(
        default=1,
    )

    is_active = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Coaching Content"
        verbose_name_plural = "Coaching Content"
        ordering = ["display_order", "id"]


class MembershipContent(models.Model):
    title = models.CharField(
        max_length=150,
    )

    description = models.TextField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    duration = models.CharField(
        max_length=100,
        blank=True,
    )

    display_order = models.PositiveIntegerField(
        default=1,
    )

    is_active = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Membership Content"
        verbose_name_plural = "Membership Content"
        ordering = ["display_order", "id"]


class TournamentContent(models.Model):
    title = models.CharField(
        max_length=150,
    )

    description = models.TextField()

    tournament_date = models.DateField(
        null=True,
        blank=True,
    )

    entry_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    prize_info = models.CharField(
        max_length=255,
        blank=True,
    )

    display_order = models.PositiveIntegerField(
        default=1,
    )

    is_active = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Tournament Content"
        verbose_name_plural = "Tournament Content"
        ordering = ["display_order", "tournament_date", "id"]


class GalleryImage(models.Model):
    title = models.CharField(
        max_length=150,
        blank=True,
    )

    image = models.ImageField(
        upload_to="gallery/",
    )

    description = models.TextField(
        blank=True,
    )

    display_order = models.PositiveIntegerField(
        default=1,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return self.title or f"Gallery Image {self.id}"

    class Meta:
        verbose_name = "Gallery Image"
        verbose_name_plural = "Gallery Images"
        ordering = ["display_order", "id"]


class Table(models.Model):
    name = models.CharField(
        max_length=50,
    )

    table_type = models.CharField(
        max_length=100,
    )

    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(0),
        ],
    )

    is_active = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.name


class Booking(models.Model):
    table = models.ForeignKey(
        Table,
        on_delete=models.CASCADE,
        related_name="bookings",
    )

    customer_name = models.CharField(
        max_length=100,
    )

    phone = models.CharField(
        max_length=20,
    )

    email = models.EmailField()

    booking_date = models.DateField()

    start_time = models.TimeField()

    duration_hours = models.PositiveIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(4),
        ],
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(0),
        ],
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("Pending", "Pending"),
            ("Confirmed", "Confirmed"),
            ("Cancelled", "Cancelled"),
            ("Completed", "Completed"),
        ],
        default="Confirmed",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    @property
    def booking_reference(self):
        return (
            f"RSA-{self.booking_date.strftime('%Y%m%d')}-"
            f"{self.id:04d}"
        )

    def __str__(self):
        return (
            f"{self.customer_name} - "
            f"{self.table.name} - "
            f"{self.booking_date}"
        )

    class Meta:
        indexes = [
            models.Index(
                fields=["table", "booking_date", "status"],
                name="booking_table_date_status_idx",
            ),
            models.Index(
                fields=["booking_date", "status"],
                name="booking_date_status_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    duration_hours__gte=1,
                    duration_hours__lte=4,
                ),
                name="booking_duration_1_to_4_hours",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="booking_amount_non_negative",
            ),
        ]


class BookingCancellation(models.Model):
    class Reason(models.TextChoices):
        PLANS_CHANGED = "plans_changed", "My plans changed"
        BOOKED_WRONG_DETAILS = "booked_wrong_details", "I selected the wrong date or time"
        UNABLE_TO_ATTEND = "unable_to_attend", "I can no longer attend"
        BOOKED_BY_MISTAKE = "booked_by_mistake", "I made this booking by mistake"
        OTHER = "other", "Other"

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="customer_cancellation",
    )
    token_digest = models.CharField(max_length=64, unique=True)
    requested_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(
        max_length=32,
        choices=Reason.choices,
        blank=True,
    )
    reason_details = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return f"Customer cancellation — {self.booking.booking_reference}"

    class Meta:
        verbose_name = "Customer Cancellation"
        verbose_name_plural = "Customer Cancellations"


class BookingEmailNotification(models.Model):
    class NotificationType(models.TextChoices):
        CONFIRMATION = "confirmation", "Confirmation"
        CANCELLATION = "cancellation", "Cancellation"
        COMPLETION = "completion", "Completion"

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="email_notifications",
    )

    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
    )

    status = models.CharField(
        max_length=10,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )

    recipient_email = models.EmailField()

    subject = models.CharField(max_length=255)

    plain_message = models.TextField()

    html_message = models.TextField()

    attempt_count = models.PositiveIntegerField(default=0)

    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    last_attempt_at = models.DateTimeField(null=True, blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.booking.booking_reference}"

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "notification_type"],
                name="booking_email_booking_type_uniq",
            ),
        ]


class BookingEmailDeliveryAttempt(models.Model):
    class AttemptStatus(models.TextChoices):
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    notification = models.ForeignKey(
        BookingEmailNotification,
        on_delete=models.CASCADE,
        related_name="delivery_attempts",
    )
    attempt_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10,
        choices=AttemptStatus.choices,
        default=AttemptStatus.SENDING,
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_summary = models.TextField(blank=True)

    def __str__(self):
        return f"Attempt {self.attempt_number} — {self.notification}"

    class Meta:
        ordering = ["-attempt_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "attempt_number"],
                name="booking_email_attempt_number_uniq",
            ),
        ]
