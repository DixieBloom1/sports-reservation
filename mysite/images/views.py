# images/views.py
import csv
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Facility, Booking, Blackout, UserProfile, Court
from .forms import RegisterForm, BookingForm, UserForm, ProfileForm
from .services import available_slots, available_slots_court


def home(request):
    """Facilities list + simple search/filter."""
    q = request.GET.get("q", "") or ""
    sport = request.GET.get("sport", "") or ""
    facilities = Facility.objects.all()
    if q:
        facilities = facilities.filter(Q(name__icontains=q) | Q(location__icontains=q))
    if sport:
        facilities = facilities.filter(sport_type=sport)
    return render(
        request,
        "facilities/list.html",
        {"facilities": facilities, "q": q, "sport": sport, "SPORT_CHOICES": Facility.SPORT_CHOICES},
    )

def register_view(request):
    """Simple user registration."""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
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
    has_courts = facility.courts.filter(is_active=True).exists()

    if request.method == "POST":
        form = BookingForm(request.POST, facility=facility)

        # preset relations before validation
        form.instance.user = request.user
        form.instance.facility = facility
        form.instance.price = facility.base_price

        if not has_courts:
            # Ensure court stays empty when the facility has no courts
            form.instance.court = None

        if form.is_valid():
            booking = form.save(commit=False)
            booking.save()
            target = booking.court.name if booking.court_id else facility.name
            send_mail(
                "Booking confirmed",
                f"You booked {target} on {booking.start_dt}.",
                "noreply@example.com",
                [request.user.email],
                fail_silently=True,
            )
            messages.success(request, "Booking confirmed.")
            return redirect("images:booking_confirmed", pk=booking.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        start = request.GET.get("start")
        end = request.GET.get("end")
        court_id = request.GET.get("court")
        initial = {}
        if start and end: initial.update({"start_dt": start, "end_dt": end})
        if has_courts and court_id: initial.update({"court": court_id})
        form = BookingForm(initial=initial, facility=facility)

    return render(request, "bookings/book.html", {"facility": facility, "form": form})


@login_required
def cancel_booking(request, pk):
    """Cancel a booking if ≥ 1 hour in advance."""
    b = get_object_or_404(Booking, pk=pk, user=request.user)
    if (b.start_dt - timezone.now()) < timedelta(hours=1):
        messages.error(request, "Cancellations must be at least 1 hour in advance.")
        return redirect("images:my_bookings")
    b.status = "cancelled"
    b.save()
    send_mail(
        "Booking cancelled",
        f"Your booking for {b.facility.name} was cancelled.",
        "noreply@example.com",
        [request.user.email],
        fail_silently=True,
    )
    messages.success(request, "Booking cancelled.")
    return redirect("images:my_bookings")


@staff_member_required
def usage_report_csv(request):
    """CSV report: bookings per facility/day + revenue."""
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="usage.csv"'
    writer = csv.writer(resp)
    writer.writerow(["Facility", "Date", "Bookings", "Revenue"])

    rows = {}
    for b in Booking.objects.filter(status="confirmed"):
        key = (b.facility.name, b.start_dt.date())
        rows.setdefault(key, {"count": 0, "rev": 0.0})
        rows[key]["count"] += 1
        rows[key]["rev"] += float(b.price)

    for (facility, day), agg in sorted(rows.items()):
        writer.writerow([facility, day, agg["count"], agg["rev"]])

    return resp


@login_required
def profile_view(request):
    """Edit username/email/phone."""
    user = request.user
    # ensure profile exists (in case signals didn't run earlier during dev)
    UserProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        uf = UserForm(request.POST, instance=user)
        pf = ProfileForm(request.POST, instance=user.profile)
        if uf.is_valid() and pf.is_valid():
            uf.save()
            pf.save()
            messages.success(request, "Profile updated.")
            return redirect("images:profile")
    else:
        uf = UserForm(instance=user)
        pf = ProfileForm(instance=user.profile)

    return render(request, "account/profile.html", {"user_form": uf, "profile_form": pf})


@require_POST
def logout_post(request):
    """POST-only logout for CSRF protection."""
    logout(request)
    return redirect("images:login")


@login_required
def booking_confirmed(request, pk):
    """Simple confirmation page after booking/modify."""
    booking = get_object_or_404(Booking, pk=pk, user=request.user)
    return render(request, "bookings/confirmed.html", {"booking": booking})


@login_required
def modify_booking(request, pk):
    """Modify an existing booking (≥ 1 hour before start)."""
    b = get_object_or_404(Booking, pk=pk, user=request.user, status="confirmed")

    if (b.start_dt - timezone.now()) < timedelta(hours=1):
        messages.error(request, "Modifications must be at least 1 hour in advance.")
        return redirect("images:my_bookings")

    if request.method == "POST":
        form = BookingForm(request.POST, instance=b)

        # Preserve locked fields
        form.instance.user = b.user
        form.instance.facility = b.facility
        form.instance.price = b.price

        if form.is_valid():
            try:
                updated = form.save(commit=False)  # extra safety; clean already ran
                updated.save()
                messages.success(request, "Booking updated.")
                return redirect("images:booking_confirmed", pk=b.pk)
            except Exception as e:
                messages.error(request, str(e))
    else:
        form = BookingForm(instance=b)

    return render(request, "bookings/modify.html", {"booking": b, "form": form})

@login_required
def book_view(request, facility_id):
    facility = get_object_or_404(Facility, id=facility_id)

    if request.method == "POST":
        form = BookingForm(request.POST, facility=facility)

        # preset required relations before validation
        form.instance.user = request.user
        form.instance.facility = facility
        form.instance.price = facility.base_price

        if form.is_valid():
            booking = form.save(commit=False)
            booking.save()
            send_mail(
                "Booking confirmed",
                f"You booked {booking.court.name} ({facility.name}) on {booking.start_dt}.",
                "noreply@example.com",
                [request.user.email],
                fail_silently=True,
            )
            messages.success(request, "Booking confirmed.")
            return redirect("images:booking_confirmed", pk=booking.pk)
    else:
        start = request.GET.get("start")
        end = request.GET.get("end")
        court_id = request.GET.get("court")
        initial = {}
        if start and end: initial.update({"start_dt": start, "end_dt": end})
        if court_id: initial.update({"court": court_id})
        form = BookingForm(initial=initial, facility=facility)

    return render(request, "bookings/book.html", {"facility": facility, "form": form})

@login_required
def modify_booking(request, pk):
    b = get_object_or_404(Booking, pk=pk, user=request.user, status="confirmed")
    if (b.start_dt - timezone.now()) < timedelta(hours=1):
        messages.error(request, "Modifications must be at least 1 hour in advance.")
        return redirect("images:my_bookings")

    if request.method == "POST":
        form = BookingForm(request.POST, instance=b, facility=b.facility)
        # lock relationships
        form.instance.user = b.user
        form.instance.facility = b.facility
        form.instance.price = b.price

        if form.is_valid():
            updated = form.save(commit=False)
            updated.save()
            messages.success(request, "Booking updated.")
            return redirect("images:booking_confirmed", pk=b.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = BookingForm(instance=b, facility=b.facility)

    return render(request, "bookings/modify.html", {"booking": b, "form": form})

def facility_detail(request, pk):
    f = get_object_or_404(Facility, pk=pk)
    selected_date_str = request.GET.get("date")
    selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date() if selected_date_str else date.today()

    courts = f.courts.filter(is_active=True).order_by("name")
    has_courts = courts.exists()

    selected_court = None
    slots = []

    # NEW: notices context
    now = timezone.now()
    upcoming_blackouts = Blackout.objects.filter(
        facility=f, end_dt__gte=now
    ).order_by("start_dt")[:20]
    day_blackouts = Blackout.objects.filter(
        facility=f, start_dt__date__lte=selected_date, end_dt__date__gte=selected_date
    ).order_by("start_dt")

    if has_courts:
        selected_court_id = request.GET.get("court")
        if selected_court_id:
            selected_court = get_object_or_404(Court, pk=selected_court_id, facility=f)
            slots = available_slots_court(selected_court, selected_date)
        else:
            # User clicked "Check" without choosing a court -> show a message
            if "date" in request.GET:  # indicates the form was submitted
                messages.warning(request, "Choose a court to see availability.")
    else:
        # No courts: show facility-level availability
        slots = available_slots(f, selected_date)

    return render(request, "facilities/detail.html", {
        "facility": f,
        "courts": courts,
        "has_courts": has_courts,
        "selected_court": selected_court,
        "slots": slots,
        "selected_date": selected_date,
        # NEW
        "upcoming_blackouts": upcoming_blackouts,
        "day_blackouts": day_blackouts,
    })


@login_required
def book_view(request, facility_id):
    facility = get_object_or_404(Facility, id=facility_id)
    has_courts = facility.courts.filter(is_active=True).exists()

    if request.method == "POST":
        form = BookingForm(request.POST, facility=facility)
        form.instance.user = request.user
        form.instance.facility = facility
        form.instance.price = facility.base_price
        if not has_courts:
            form.instance.court = None

        if form.is_valid():
            booking = form.save(commit=False)
            booking.save()
            target = booking.court.name if booking.court_id else facility.name
            send_mail(
                "Booking confirmed",
                f"You booked {target} on {booking.start_dt}.",
                "noreply@example.com",
                [request.user.email],
                fail_silently=True,
            )
            messages.success(request, "Booking confirmed.")
            return redirect("images:booking_confirmed", pk=booking.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        start = request.GET.get("start")
        end = request.GET.get("end")
        court_id = request.GET.get("court")
        initial = {}
        if start and end: initial.update({"start_dt": start, "end_dt": end})
        if has_courts and court_id: initial.update({"court": court_id})
        form = BookingForm(initial=initial, facility=facility)

    # NEW: notices for the booking page too (same modal)
    upcoming_blackouts = Blackout.objects.filter(
        facility=facility, end_dt__gte=timezone.now()
    ).order_by("start_dt")[:20]

    return render(request, "bookings/book.html", {
        "facility": facility,
        "form": form,
        "upcoming_blackouts": upcoming_blackouts,  # for the modal
    })