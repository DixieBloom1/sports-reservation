from datetime import timedelta, time as dtime, datetime
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Facility(models.Model):
    SPORT_CHOICES = [
        ("tennis", "Tennis"),
        ("football", "Football"),
        ("basketball", "Basketball"),
        ("swimming", "Swimming"),
        ("gym", "Gym"),
    ]
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="owned_facilities", null=True, blank=True
    )
    name = models.CharField(max_length=120, unique=True)
    sport_type = models.CharField(max_length=30, choices=SPORT_CHOICES)
    location = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="facility_images/", blank=True, null=True)
    slot_length_minutes = models.PositiveIntegerField(default=60)
    open_time = models.TimeField(default=dtime(8, 0))
    close_time = models.TimeField(default=dtime(22, 0))
    base_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    def __str__(self): return self.name

class Sport(models.Model):
    """Dynamic sports added by providers when creating courts."""
    name = models.CharField(max_length=50, unique=True)
    class Meta:
        ordering = ["name"]
    def __str__(self): return self.name

class Court(models.Model):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="courts")
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    # NEW: sport per court (providers type it; we store/normalize here)
    sport = models.ForeignKey(Sport, on_delete=models.SET_NULL, null=True, blank=True, related_name="courts")
    class Meta:
        unique_together = ("facility", "name")
        ordering = ["facility__name", "name"]
    def __str__(self): return f"{self.facility.name} - {self.name}"

class Booking(models.Model):
    STATUS = [("confirmed", "Confirmed"), ("cancelled", "Cancelled")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="bookings")
    court = models.ForeignKey(Court, on_delete=models.CASCADE, related_name="bookings", null=True, blank=True)
    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="confirmed")
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        target = self.court.name if self.court_id else self.facility.name
        return f"{target} • {self.start_dt:%Y-%m-%d %H:%M}"
    def clean(self):
        if not self.facility_id:
            raise ValidationError("Facility must be set.")
        if self.court_id and self.court.facility_id != self.facility_id:
            raise ValidationError("Selected court doesn't belong to the chosen facility.")
        if not self.start_dt or not self.end_dt:
            raise ValidationError("Start and end time are required.")
        if self.start_dt >= self.end_dt:
            raise ValidationError("End time must be after start time.")
        minutes = int((self.end_dt - self.start_dt).total_seconds() // 60)
        if minutes <= 0 or minutes % self.facility.slot_length_minutes != 0:
            raise ValidationError("Booking length must be a positive multiple of the facility slot length.")
        local_start = timezone.localtime(self.start_dt)
        local_end = timezone.localtime(self.end_dt)
        if not (self.facility.open_time <= local_start.time() and local_end.time() <= self.facility.close_time):
            raise ValidationError("Booking must be within facility opening hours.")
        if (self.start_dt - timezone.now()) < timedelta(hours=1):
            raise ValidationError("Bookings must be made at least 1 hour in advance.")
        if Blackout.objects.filter(facility=self.facility, start_dt__lt=self.end_dt, end_dt__gt=self.start_dt).exists():
            raise ValidationError("This time falls within a blackout period.")
        qs = Booking.objects.filter(status="confirmed")
        if self.pk: qs = qs.exclude(pk=self.pk)
        qs = qs.filter(court=self.court) if self.court_id else qs.filter(facility=self.facility)
        if qs.filter(start_dt__lt=self.end_dt, end_dt__gt=self.start_dt).exists():
            raise ValidationError("This time overlaps with another booking.")

class Blackout(models.Model):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="blackouts")
    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)
    def __str__(self): return f"{self.facility.name} blackout {self.start_dt:%Y-%m-%d %H:%M}–{self.end_dt:%H:%M}"

class UserProfile(models.Model):
    ROLE_CHOICES = [("customer", "Customer"), ("provider", "Provider")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=30, blank=True)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="customer")
    def __str__(self): return f"Profile({self.user.username})"


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created: UserProfile.objects.create(user=instance)

class FacilitySignupRequest(models.Model):
    """Providers submit this; admin reviews/approves. Sport text here is just for admin info."""
    STATUS_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("denied", "Denied")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="facility_request")
    facility_name = models.CharField(max_length=120)
    offered_sports_text = models.CharField(max_length=200)  # free-text, e.g. "Padel, Badminton"
    location = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    open_time = models.TimeField(default=dtime(8, 0))
    close_time = models.TimeField(default=dtime(22, 0))
    num_courts = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.facility_name} by {self.user.username} ({self.status})"