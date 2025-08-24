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
        ("tennis", "Tennis"), ("football", "Football"),
        ("basketball", "Basketball"), ("swimming", "Swimming"), ("gym", "Gym"),
    ]
    name = models.CharField(max_length=120, unique=True)
    sport_type = models.CharField(max_length=30, choices=SPORT_CHOICES)
    location = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="facility_images/", blank=True, null=True)
    slot_length_minutes = models.PositiveIntegerField(default=60)
    open_time = models.TimeField(default=dtime(8, 0))
    close_time = models.TimeField(default=dtime(22, 0))
    base_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    def __str__(self):
        return self.name

class Court(models.Model):
    """A single court/pitch that belongs to a facility."""
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="courts")
    name = models.CharField(max_length=50)  # e.g., "Court 1", "Pitch A"
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("facility", "name")
        ordering = ["facility__name", "name"]

    def __str__(self):
        return f"{self.facility.name} - {self.name}"

class Blackout(models.Model):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="blackouts")
    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.facility.name} blackout {self.start_dt:%Y-%m-%d %H:%M}–{self.end_dt:%H:%M}"

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
        # Basic sanity
        if not self.facility_id:
            raise ValidationError("Facility must be set.")
        if self.court_id and self.court.facility_id != self.facility_id:
            raise ValidationError("Selected court doesn't belong to the chosen facility.")
        if not self.start_dt or not self.end_dt:
            raise ValidationError("Start and end time are required.")
        if self.start_dt >= self.end_dt:
            raise ValidationError("End time must be after start time.")

        # Slot length: positive and aligned to facility slot
        minutes = int((self.end_dt - self.start_dt).total_seconds() // 60)
        if minutes <= 0 or minutes % self.facility.slot_length_minutes != 0:
            raise ValidationError("Booking length must be a positive multiple of the facility slot length.")

        # Within opening hours
        local_start = timezone.localtime(self.start_dt)
        local_end = timezone.localtime(self.end_dt)
        open_t, close_t = self.facility.open_time, self.facility.close_time
        if not (open_t <= local_start.time() and local_end.time() <= close_t):
            raise ValidationError("Booking must be within facility opening hours.")

        # At least 1 hour in advance
        if (self.start_dt - timezone.now()) < timedelta(hours=1):
            raise ValidationError("Bookings must be made at least 1 hour in advance.")

        # Blackouts (facility-wide)
        if Blackout.objects.filter(
            facility=self.facility,
            start_dt__lt=self.end_dt,
            end_dt__gt=self.start_dt,
        ).exists():
            raise ValidationError("This time falls within a blackout period.")

        # Overlap check (same court; fallback to facility if court not selected)
        qs = Booking.objects.filter(status="confirmed")
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if self.court_id:
            qs = qs.filter(court=self.court)
        else:
            qs = qs.filter(facility=self.facility)
        if qs.filter(start_dt__lt=self.end_dt, end_dt__gt=self.start_dt).exists():
            raise ValidationError("This time overlaps with another booking.")

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=30, blank=True)
    def __str__(self): return f"Profile({self.user.username})"

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
