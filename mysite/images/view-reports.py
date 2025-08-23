# reservations/views_reports.py
import csv
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from .models import Booking

@staff_member_required
def usage_report_csv(request):
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")
    qs = Booking.objects.filter(status="confirmed")
    if date_from: qs = qs.filter(start_dt__date__gte=date_from)
    if date_to: qs = qs.filter(start_dt__date__lte=date_to)

    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="usage.csv"'
    writer = csv.writer(resp)
    writer.writerow(["Facility", "Date", "Bookings", "Revenue"])

    rows = {}
    for b in qs:
        key = (b.facility.name, b.start_dt.date())
        rows.setdefault(key, {"count":0,"revenue":0})
        rows[key]["count"] += 1
        rows[key]["revenue"] += float(b.price)

    for (facility, day), agg in sorted(rows.items()):
        writer.writerow([facility, day, agg["count"], agg["revenue"]])

    return resp
