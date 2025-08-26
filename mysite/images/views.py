# images/views.py
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from validators import ValidationError

from .models import (
    Facility,
    Booking,
    Blackout,
    UserProfile,
    Court,
    FacilitySignupRequest,
    Sport,
)
from .forms import (
    RegisterForm,
    BookingForm,
    UserForm,
    ProfileForm,
    ProviderRegisterForm,
    FacilityForm,
    CourtForm,
    BlackoutForm,
)
from .services import available_slots, available_slots_court


def home(request):
    q = request.GET.get("q", "") or ""
    sport = request.GET.get("sport", "") or ""
    facilities = Facility.objects.all()
    if q:
        facilities = facilities.filter(Q(name__icontains=q) | Q(location__icontains=q))

    typed_sports_qs = (
        Facility.objects.exclude(sport_text="")
        .values_list("sport_text", flat=True)
        .distinct()
    )
    court_sports_qs = (
        Court.objects.filter(sport__isnull=False)
        .values_list("sport__name", flat=True)
        .distinct()
    )

    seen, SPORT_OPTIONS = set(), []
    for name in list(typed_sports_qs) + list(court_sports_qs):
        if not name:
            continue
        k = name.casefold()
        if k not in seen:
            seen.add(k)
            SPORT_OPTIONS.append(name)
    SPORT_OPTIONS.sort(key=str.casefold)

    if sport:
        facilities = facilities.filter(
            Q(sport_text__iexact=sport) | Q(courts__sport__name__iexact=sport)
        ).distinct()

    return render(
        request,
        "facilities/list.html",
        {"facilities": facilities, "q": q, "sport": sport, "SPORT_OPTIONS": SPORT_OPTIONS},
    )


def register_view(request):
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
def cancel_booking(request, pk):
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
    user = request.user
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
    logout(request)
    return redirect("images:login")


@login_required
def booking_confirmed(request, pk):
    booking = get_object_or_404(Booking, pk=pk, user=request.user)
    return render(request, "bookings/confirmed.html", {"booking": booking})


def facility_detail(request, pk):
    f = get_object_or_404(Facility, pk=pk)
    selected_date_str = request.GET.get("date")
    selected_date = (
        datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        if selected_date_str
        else date.today()
    )

    courts = f.courts.filter(is_active=True).order_by("name")
    has_courts = courts.exists()
    selected_court = None
    slots = []

    now = timezone.now()
    upcoming_blackouts = (
        Blackout.objects.filter(facility=f, end_dt__gte=now).order_by("start_dt")[:20]
    )
    past_blackouts = (
        Blackout.objects.filter(facility=f, end_dt__lt=now).order_by("-start_dt")[:20]
    )
    day_blackouts = Blackout.objects.filter(
        facility=f, start_dt__date__lte=selected_date, end_dt__date__gte=selected_date
    ).order_by("start_dt")

    if has_courts:
        selected_court_id = request.GET.get("court")
        if selected_court_id:
            selected_court = get_object_or_404(Court, pk=selected_court_id, facility=f)
            slots = available_slots_court(selected_court, selected_date)
        else:
            if "date" in request.GET:
                messages.warning(request, "Choose a court to see availability.")
    else:
        slots = available_slots(f, selected_date)

    return render(
        request,
        "facilities/detail.html",
        {
            "facility": f,
            "courts": courts,
            "has_courts": has_courts,
            "selected_court": selected_court,
            "slots": slots,
            "selected_date": selected_date,
            "past_blackouts": past_blackouts,
            "upcoming_blackouts": upcoming_blackouts,
            "day_blackouts": day_blackouts,
        },
    )


def provider_register_view(request):
    if request.method == "POST":
        form = ProviderRegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = User.objects.create(
                    username=form.cleaned_data["username"],
                    email=form.cleaned_data["email"],
                    is_active=False,
                    password=make_password(form.cleaned_data["password"]),
                )
                user.profile.role = "provider"
                user.profile.phone = form.cleaned_data.get("phone", "")
                user.profile.save()

                FacilitySignupRequest.objects.create(
                    user=user,
                    facility_name=form.cleaned_data["facility_name"],
                    offered_sports_text=form.cleaned_data["offered_sports_text"],
                    location=form.cleaned_data["location"],
                    description=form.cleaned_data.get("description", ""),
                    open_time=form.cleaned_data["open_time"],
                    close_time=form.cleaned_data["close_time"],
                    num_courts=form.cleaned_data["num_courts"],
                )
            messages.success(
                request,
                "Submitted! Admin must approve your account before you can sign in.",
            )
            return redirect("images:login")
    else:
        form = ProviderRegisterForm()
    return render(request, "account/provider_register.html", {"form": form})


@staff_member_required
def facility_requests_list(request):
    pending = (
        FacilitySignupRequest.objects.filter(status="pending")
        .select_related("user")
        .order_by("created_at")
    )
    return render(request, "admin_facility/requests.html", {"pending": pending})


@staff_member_required
@require_POST
def facility_request_approve(request, pk):
    req = get_object_or_404(FacilitySignupRequest, pk=pk, status="pending")
    with transaction.atomic():
        user = req.user
        user.is_active = True
        user.save()
        req.status = "approved"
        req.save()
    messages.success(
        request, f"Approved '{user.username}'. They can now sign in and add their facilities."
    )
    return redirect("facility_requests")


@staff_member_required
@require_POST
def facility_request_deny(request, pk):
    req = get_object_or_404(FacilitySignupRequest, pk=pk, status="pending")
    username = req.user.username
    with transaction.atomic():
        user = req.user
        req.delete()
        user.delete()
    messages.success(request, f"Denied and removed '{username}'.")
    return redirect("facility_requests")


@login_required
def provider_facilities(request):
    if request.user.profile.role != "provider":
        messages.error(request, "Only providers can access this page.")
        return redirect("images:facilities_list")
    facilities = Facility.objects.filter(owner=request.user).prefetch_related(
        "courts__sport"
    )
    return render(request, "provider/facilities.html", {"facilities": facilities})


@login_required
def provider_add_facility(request):
    if request.user.profile.role != "provider":
        messages.error(request, "Only providers can access this page.")
        return redirect("images:facilities_list")

    if request.method == "POST":
        form = FacilityForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.save(commit=False)
            f.owner = request.user
            f.save()

            sport_name = (form.cleaned_data.get("sport_name") or "").strip()
            if sport_name:
                sport = Sport.objects.filter(name__iexact=sport_name).first()
                if not sport:
                    sport = Sport.objects.create(name=sport_name)
                if not f.courts.exists():
                    Court.objects.create(
                        facility=f,
                        name="Court 1",
                        sport=sport,
                        is_active=True,
                    )

            messages.success(request, "Facility created.")
            return redirect("images:provider_facilities")
        messages.error(request, "Please correct the errors below.")
    else:
        form = FacilityForm()

    return render(request, "provider/add_facility.html", {"form": form})


@login_required
def provider_manage_courts(request, facility_id):
    f = get_object_or_404(Facility, id=facility_id, owner=request.user)
    courts = f.courts.order_by("name")

    if request.method == "POST":
        form = CourtForm(request.POST)
        form.instance.facility = f
        if form.is_valid():
            form.instance.name = form.cleaned_data["name"].strip()
            if f.courts.filter(name__iexact=form.instance.name).exists():
                form.add_error("name", "A court with this name already exists for this facility.")
            else:
                try:
                    form.save()
                    messages.success(request, "Court added.")
                    return redirect("images:provider_manage_courts", facility_id=f.id)
                except IntegrityError:
                    form.add_error("name", "A court with this name already exists for this facility.")
    else:
        form = CourtForm()

    return render(
        request,
        "provider/manage_courts.html",
        {"facility": f, "courts": courts, "form": form},
    )


@login_required
def provider_bookings(request):
    if request.user.profile.role != "provider":
        messages.error(request, "Only providers can access this page.")
        return redirect("images:facilities_list")
    bookings = (
        Booking.objects.filter(facility__owner=request.user)
        .select_related("facility", "court", "user")
        .order_by("-start_dt")
    )
    return render(request, "provider/bookings.html", {"bookings": bookings})


def _back_to_facility(facility):
    try:
        return redirect("images:facility_detail", pk=facility.id)
    except Exception:
        return redirect("images:facilities_list")


@require_http_methods(["GET", "POST"])
@login_required
def book_view(request, facility_id):
    facility = get_object_or_404(Facility, pk=facility_id)

    court_raw = request.GET.get("court") or request.POST.get("court")
    court_id = (court_raw or "").strip()
    court = get_object_or_404(Court, pk=court_id, facility=facility) if court_id else None

    if not court and facility.courts.filter(is_active=True).exists():
        messages.warning(request, "Choose a court to book.")
        return _back_to_facility(facility)

    start_raw = request.GET.get("start") if request.method == "GET" else request.POST.get("start")
    end_raw = request.GET.get("end") if request.method == "GET" else request.POST.get("end")
    start_str = (start_raw or "").strip()
    end_str = (end_raw or "").strip()
    if not start_str or not end_str:
        messages.error(request, "Missing start or end time.")
        return _back_to_facility(facility)

    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        tz = timezone.get_current_timezone()
        if timezone.is_naive(start): start = timezone.make_aware(start, tz)
        if timezone.is_naive(end):   end = timezone.make_aware(end, tz)
    except ValueError:
        messages.error(request, "Invalid date/time format.")
        return _back_to_facility(facility)

    if start >= end:
        messages.error(request, "Start must be before end.")
        return _back_to_facility(facility)

    length_min = int((end - start).total_seconds() // 60)
    if length_min <= 0 or (length_min % facility.slot_length_minutes) != 0:
        messages.error(request, "Invalid slot length for this facility.")
        return _back_to_facility(facility)

    local_start = timezone.localtime(start)
    local_end = timezone.localtime(end)
    if not (facility.open_time <= local_start.time() and local_end.time() <= facility.close_time):
        messages.error(request, "Booking must be within opening hours.")
        return _back_to_facility(facility)
    if (start - timezone.now()) < timedelta(hours=1):
        messages.error(request, "Bookings must be made at least 1 hour in advance.")
        return _back_to_facility(facility)

    if Blackout.objects.filter(facility=facility, start_dt__lt=end, end_dt__gt=start).exists():
        messages.error(request, "That time is unavailable due to a posted notice/blackout.")
        return _back_to_facility(facility)

    total_hours = Decimal(length_min) / Decimal(60)
    price = (facility.base_price * total_hours).quantize(Decimal("0.01"))

    if request.method == "GET":
        now = timezone.now()
        upcoming_blackouts = Blackout.objects.filter(facility=facility, end_dt__gte=now).order_by("start_dt")[:20]
        past_blackouts = Blackout.objects.filter(facility=facility, end_dt__lt=now).order_by("-start_dt")[:20]
        day_blackouts = Blackout.objects.filter(
            facility=facility,
            start_dt__date__lte=start.date(),
            end_dt__date__gte=start.date(),
        ).order_by("start_dt")

        return render(
            request,
            "book/confirm.html",
            {
                "facility": facility,
                "court": court,
                "start": start,
                "end": end,
                "price": price,  # <-- show this on the confirm page
                "upcoming_blackouts": upcoming_blackouts,
                "past_blackouts": past_blackouts,
                "day_blackouts": day_blackouts,
            },
        )

    clash_qs = Booking.objects.filter(
        status="confirmed",
        facility=facility,
        start_dt__lt=end,
        end_dt__gt=start,
    )
    clash_qs = clash_qs.filter(court=court) if court else clash_qs.filter(court__isnull=True)
    if clash_qs.exists():
        messages.error(request, "That slot is no longer available.")
        return _back_to_facility(facility)

    booking = Booking(
        facility=facility,
        court=court,
        user=request.user,
        start_dt=start,
        end_dt=end,
        price=price,
    )
    try:
        booking.full_clean()
        booking.save()
    except ValidationError as e:
        messages.error(request, "; ".join(e.messages) if hasattr(e, "messages") else str(e))
        return _back_to_facility(facility)

    messages.success(request, "Booking created.")
    return redirect("images:my_bookings")


@login_required
def modify_booking(request, pk):
    b = get_object_or_404(Booking, pk=pk, user=request.user, status="confirmed")
    if (b.start_dt - timezone.now()) < timedelta(hours=1):
        messages.error(request, "Modifications must be at least 1 hour in advance.")
        return redirect("images:my_bookings")

    if request.method == "POST":
        form = BookingForm(request.POST, instance=b, facility=b.facility)
        form.instance.user = b.user
        form.instance.facility = b.facility
        form.instance.price = b.price

        if form.is_valid():
            updated = form.save(commit=False)
            updated.save()
            messages.success(request, "Booking updated.")
            return redirect("images:booking_confirmed", pk=b.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = BookingForm(instance=b, facility=b.facility)

    return render(request, "bookings/modify.html", {"booking": b, "form": form})


@login_required
def provider_edit_facility(request, facility_id):
    if request.user.profile.role != "provider":
        messages.error(request, "Only providers can access this page.")
        return redirect("images:facilities_list")

    facility = get_object_or_404(Facility, id=facility_id, owner=request.user)

    if request.method == "POST":
        form = FacilityForm(request.POST, request.FILES, instance=facility)
        if form.is_valid():
            form.save()
            messages.success(request, "Facility updated.")
            return redirect("images:provider_facilities")
        messages.error(request, "Please fix the errors below.")
    else:
        form = FacilityForm(instance=facility)

    return render(
        request, "provider/edit_facility.html", {"form": form, "facility": facility}
    )


@login_required
@require_POST
def provider_delete_facility(request, facility_id):
    if request.user.profile.role != "provider":
        messages.error(request, "Only providers can access this page.")
        return redirect("images:facilities_list")

    facility = get_object_or_404(Facility, id=facility_id, owner=request.user)

    has_future_bookings = Booking.objects.filter(
        facility=facility, status="confirmed", start_dt__gte=timezone.now()
    ).exists()
    if has_future_bookings:
        messages.error(
            request, "You cannot delete a facility with future confirmed bookings."
        )
        return redirect("images:provider_facilities")

    facility.delete()
    messages.success(request, "Facility deleted.")
    return redirect("images:provider_facilities")


@login_required
def provider_manage_blackouts(request, facility_id):
    f = get_object_or_404(Facility, id=facility_id, owner=request.user)
    blackouts = f.blackouts.all()

    if request.method == "POST":
        form = BlackoutForm(request.POST)
        if form.is_valid():
            b = form.save(commit=False)
            b.facility = f
            if b.start_dt >= b.end_dt:
                form.add_error("end_dt", "End must be after start.")
            else:
                b.save()
                messages.success(request, "Notice/blackout added.")
                return redirect("images:provider_manage_blackouts", facility_id=f.id)
    else:
        form = BlackoutForm()

    return render(
        request,
        "provider/manage_blackouts.html",
        {"facility": f, "form": form, "blackouts": blackouts},
    )


@login_required
@require_POST
def provider_delete_blackout(request, facility_id, blackout_id):
    f = get_object_or_404(Facility, id=facility_id, owner=request.user)
    b = get_object_or_404(Blackout, id=blackout_id, facility=f)
    b.delete()
    messages.success(request, "Notice removed.")
    return redirect("images:provider_manage_blackouts", facility_id=f.id)
