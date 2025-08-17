# reservations/models.py
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import datetime, timedelta, time as dtime

class Facility(models.Model):
    SPORT_CHOICES = [
        ("tennis", "Tennis"),
        ("football", "Football"),
        ("basketball", "Basketball"),
        ("swimming", "Swimming"),
        ("gym", "Gym"),
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

class Blackout(models.Model):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE)
    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    def clean(self):
        if self.start_dt >= self.end_dt:
            raise ValidationError("Blackout end must be after start.")

class Booking(models.Model):
    STATUS = [("confirmed", "Confirmed"), ("cancelled", "Cancelled")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE)
    start_dt = models.DateTimeField()
    end_dt = models.DateTimeField()
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="confirmed")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["facility", "start_dt"])]

    def clean(self):
        # duration matches facility slot length
        minutes = int((self.end_dt - self.start_dt).total_seconds() // 60)
        if minutes <= 0 or (self.facility and minutes % self.facility.slot_length_minutes != 0):
            raise ValidationError("Booking length must match the facility slot length.")

        # within open hours (same-day assumption for simplicity)
        local = timezone.localtime if timezone.is_aware(self.start_dt) else (lambda x: x)
        s, e = local(self.start_dt), local(self.end_dt)
        if not (dtime(self.facility.open_time.hour, self.facility.open_time.minute)
                <= s.time() < e.time()
                <= dtime(self.facility.close_time.hour, self.facility.close_time.minute)):
            raise ValidationError("Booking must be within facility opening hours.")

        # ≥ 1 hour in advance (create/modify)
        if self.status == "confirmed" and (self.start_dt - timezone.now()) < timedelta(hours=1):
            raise ValidationError("Bookings must be made at least 1 hour in advance.")

        # No overlap with other confirmed bookings
        overlap = Booking.objects.filter(
            facility=self.facility,
            status="confirmed",
            start_dt__lt=self.end_dt,
            end_dt__gt=self.start_dt,
        ).exclude(id=self.id).exists()
        if overlap:
            raise ValidationError("Time slot is already booked.")

        # No overlap with blackouts
        blocked = Blackout.objects.filter(
            facility=self.facility,
            start_dt__lt=self.end_dt,
            end_dt__gt=self.start_dt
        ).exists()
        if blocked:
            raise ValidationError("Time slot is blocked (maintenance/event).")

    def cancel_allowed(self):
        return (self.start_dt - timezone.now()) >= timedelta(hours=1)
