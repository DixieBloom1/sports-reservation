from datetime import datetime, timedelta
from django.utils import timezone
from .models import Booking, Blackout

def generate_slots(facility, date):
    start = timezone.make_aware(datetime.combine(date, facility.open_time))
    end = timezone.make_aware(datetime.combine(date, facility.close_time))
    step = timedelta(minutes=facility.slot_length_minutes)
    slots = []
    t = start
    while t + step <= end:
        slots.append((t, t + step))
        t += step
    return slots

def available_slots(facility, date):
    slots = generate_slots(facility, date)
    booked = list(Booking.objects.filter(
        facility=facility, status="confirmed",
        start_dt__date=date
    ).values_list("start_dt", "end_dt"))

    blocked = list(Blackout.objects.filter(
        facility=facility,
        start_dt__date__lte=date, end_dt__date__gte=date
    ).values_list("start_dt", "end_dt"))

    def is_free(s,e):
        for bs,be in booked:
            if s < be and e > bs: return False
        for os,oe in blocked:
            if s < oe and e > os: return False
        if (s - timezone.now()) < timedelta(hours=1):
            return False
        return True

    return [(s,e) if is_free(s,e) else None for s,e in slots if is_free(s,e)]
