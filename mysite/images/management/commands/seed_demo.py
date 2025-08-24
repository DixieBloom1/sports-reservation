from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from images.models import Facility, Blackout
from datetime import time, timedelta
from django.utils import timezone

class Command(BaseCommand):
    help = "Seed demo facilities, an admin user, and a blackout"

    def handle(self, *args, **kwargs):
        # Admin user
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin123")
            self.stdout.write(self.style.SUCCESS("Created admin (admin/admin)"))

        # Facilities
        Facility.objects.all().delete()
        data = [
            ("City Tennis Court", "tennis", "Center", "Nice clay court.", 60, time(8,0), time(22,0), 12),
            ("Downtown Football Pitch", "football", "Riverside", "5-a-side pitch.", 60, time(9,0), time(21,0), 20),
            ("Campus Gym", "gym", "Campus", "Weights & cardio.", 60, time(7,0), time(23,0), 8),
        ]
        facilities = []
        for name, sport, loc, desc, slot, open_t, close_t, price in data:
            facilities.append(Facility.objects.create(
                name=name, sport_type=sport, location=loc, description=desc,
                slot_length_minutes=slot, open_time=open_t, close_time=close_t, base_price=price
            ))
        self.stdout.write(self.style.SUCCESS(f"Created {len(facilities)} facilities."))

        # Blackout tomorrow on first facility (2h maintenance)
        f = facilities[0]
        start = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=1, hours=2)
        Blackout.objects.create(facility=f, start_dt=start, end_dt=start + timedelta(hours=2), reason="Maintenance")
        self.stdout.write(self.style.SUCCESS("Added a blackout on the first facility."))

        self.stdout.write(self.style.SUCCESS("Seed done. Login: /admin (admin/admin123)"))
