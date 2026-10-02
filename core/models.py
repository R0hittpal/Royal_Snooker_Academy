from django.db import models


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

    def __str__(self):
        return self.academy_name

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"


class CoachingContent(models.Model):
    title = models.CharField(
        max_length=150,
    )

    description = models.TextField()

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

    duration_hours = models.PositiveIntegerField()

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
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

    def __str__(self):
        return (
            f"{self.customer_name} - "
            f"{self.table.name} - "
            f"{self.booking_date}"
        )