import csv
from datetime import date, datetime, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Facility, Booking, Blackout
from .forms import RegisterForm, BookingForm
from .services import available_slots

def home(request):
    q = request.GET.get("q", "")
    sport = request.GET.get("sport", "")
    facilities = Facility.objects.all()
    if q:
        facilities = facilities.filter(name__icontains=q) | facilities.filter(location__icontains=q)
    if sport:
        facilities = facilities.filter(sport_type=sport)
    return render(request, "facilities/list.html", {
        "facilities": facilities, "q": q, "sport": sport, "SPORT_CHOICES": Facility.SPORT_CHOICES
    })

def facility_detail(request, pk):
    f = get_object_or_404(Facility, pk=pk)
    selected = request.GET.get("date")
    selected_date = datetime.strptime(selected, "%Y-%m-%d").date() if selected else date.today()
    slots = available_slots(f, selected_date)
    return render(request, "facilities/detail.html", {
        "facility": f, "slots": slots, "selected_date": selected_date
    })

def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"]
            )
            messages.success(request, "Account created. Please log in.")
            return redirect("images:login")
    else:
        form = RegisterForm()
    return render(request, "account/register.html", {"form": form})

@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).order_by("-start_dt")
    return render(request, "bookings/my_bookings.html", {"bookings": bookings})

@login_required
def book_view(request, facility_id):
    facility = get_object_or_404(Facility, id=facility_id)
    if request.method == "POST":
        form = BookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.user = request.user
            booking.facility = facility
            booking.price = facility.base_price
            try:
                booking.full_clean()
                booking.save()
                send_mail(
                    "Booking confirmed",
                    f"You booked {facility.name} on {booking.start_dt}.",
                    "noreply@example.com",
                    [request.user.email],
                    fail_silently=True,
                )
                messages.success(request, "Booking confirmed.")
                return redirect("images:my_bookings")
            except Exception as e:
                messages.error(request, str(e))
    else:
        start = request.GET.get("start")
        end = request.GET.get("end")
        initial = {"start_dt": start, "end_dt": end} if start and end else {}
        form = BookingForm(initial=initial)
    return render(request, "bookings/book.html", {"facility": facility, "form": form})

@login_required
def cancel_booking(request, pk):
    b = get_object_or_404(Booking, pk=pk, user=request.user)
    if (b.start_dt - timezone.now()) < timedelta(hours=1):
        messages.error(request, "Cancellations must be at least 1 hour in advance.")
        return redirect("images:my_bookings")
    b.status = "cancelled"
    b.save()
    send_mail("Booking cancelled", f"Your booking for {b.facility.name} was cancelled.",
              "noreply@example.com", [request.user.email], fail_silently=True)
    messages.success(request, "Booking cancelled.")
    return redirect("images:my_bookings")

@staff_member_required
def usage_report_csv(request):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="usage.csv"'
    writer = csv.writer(resp)
    writer.writerow(["Facility", "Date", "Bookings", "Revenue"])

    rows = {}
    from .models import Booking
    for b in Booking.objects.filter(status="confirmed"):
        key = (b.facility.name, b.start_dt.date())
        rows.setdefault(key, {"count": 0, "rev": 0.0})
        rows[key]["count"] += 1
        rows[key]["rev"] += float(b.price)

    for (facility, day), agg in sorted(rows.items()):
        writer.writerow([facility, day, agg["count"], agg["rev"]])

    return resp
