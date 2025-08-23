# reservations/management/commands/seed_demo.py
from django.core.management.base import BaseCommand
from reservations.models import Facility, Blackout
from datetime import time, datetime, timedelta
from django.utils import timezone

class Command(BaseCommand):
    help = "Seed demo facilities and a blackout"

    def handle(self, *args, **kwargs):
        Facility.objects.all().delete()
        names = [
            ("City Tennis Court", "tennis"),
            ("Downtown Football Pitch", "football"),
            ("Campus Gym", "gym"),
        ]
        for name, sport in names:
            Facility.objects.create(
                name=name, sport_type=sport, location="Center",
                description=f"{name} description.", slot_length_minutes=60,
                open_time=time(8,0), close_time=time(22,0), base_price=10
            )
        f = Facility.objects.first()
        now = timezone.now()
        Blackout.objects.create(
            facility=f,
            start_dt=now + timedelta(days=1, hours=2),
            end_dt=now + timedelta(days=1, hours=4),
            reason="Maintenance"
        )
        self.stdout.write(self.style.SUCCESS("Seeded demo data."))
