from datetime import datetime, timedelta
from django.utils import timezone
from .models import Booking, Blackout


def generate_slots(facility, date):
    start = timezone.make_aware(datetime.combine(date, facility.open_time))
    end = timezone.make_aware(datetime.combine(date, facility.close_time))
    step = timedelta(minutes=facility.slot_length_minutes)
    res, t = [], start
    while t + step <= end:
        res.append((t, t + step))
        t += step
    return res


def _filter_free(slots, booked, blocked):
    now = timezone.now()

    def free(s, e):
        if (s - now) < timedelta(hours=1):
            return False
        for bs, be in booked:
            if s < be and e > bs:
                return False
        for os, oe in blocked:
            if s < oe and e > os:
                return False
        return True

    return [(s, e) for s, e in slots if free(s, e)]


def available_slots(facility, date):
    slots = generate_slots(facility, date)
    booked = list(
        Booking.objects.filter(
            facility=facility,
            court__isnull=True,
            status="confirmed",
            start_dt__date=date,
        ).values_list("start_dt", "end_dt")
    )
    blocked = list(
        Blackout.objects.filter(
            facility=facility,
            start_dt__date__lte=date,
            end_dt__date__gte=date,
        ).values_list("start_dt", "end_dt")
    )
    return _filter_free(slots, booked, blocked)


def available_slots_court(court, date):
    facility = court.facility
    slots = generate_slots(facility, date)
    booked = list(
        Booking.objects.filter(
            court=court, status="confirmed", start_dt__date=date
        ).values_list("start_dt", "end_dt")
    )
    blocked = list(
        Blackout.objects.filter(
            facility=facility,
            start_dt__date__lte=date,
            end_dt__date__gte=date,
        ).values_list("start_dt", "end_dt")
    )
    return _filter_free(slots, booked, blocked)
