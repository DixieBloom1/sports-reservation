# images/views.py
import csv
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from .models import Facility, Booking, Blackout, UserProfile, Court, FacilitySignupRequest, Sport
from .forms import RegisterForm, BookingForm, UserForm, ProfileForm, ProviderRegisterForm, FacilityForm, CourtForm
from .services import available_slots, available_slots_court


def home(request):
    q = request.GET.get("q", "") or ""
    sport = request.GET.get("sport", "") or ""

    facilities = Facility.objects.all()
    if q:
        facilities = facilities.filter(Q(name__icontains=q) | Q(location__icontains=q))

    # Build dropdown from live data only:
    # - facility.sport_text on existing facilities
    # - court.sport.name for courts that exist
    typed_sports_qs = Facility.objects.exclude(sport_text="") \
                                      .values_list("sport_text", flat=True) \
                                      .distinct()
    court_sports_qs = Court.objects.filter(sport__isnull=False) \
                                   .values_list("sport__name", flat=True) \
                                   .distinct()

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
            Q(sport_text__iexact=sport) |
            Q(courts__sport__name__iexact=sport)
        ).distinct()

    return render(request, "facilities/list.html", {
        "facilities": facilities, "q": q, "sport": sport, "SPORT_OPTIONS": SPORT_OPTIONS
    })
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

def provider_register_view(request):
    if request.method == "POST":
        form = ProviderRegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = User.objects.create(
                    username=form.cleaned_data["username"],
                    email=form.cleaned_data["email"],
                    is_active=False,  # cannot login yet
                    password=make_password(form.cleaned_data["password"]),
                )
                user.profile.role = "provider"
                user.profile.phone = form.cleaned_data.get("phone", "")
                user.profile.save()

                FacilitySignupRequest.objects.create(
                    user=user,
                    facility_name=form.cleaned_data["facility_name"],
                    offered_sports_text=form.cleaned_data["offered_sports_text"],  # free text for admin info
                    location=form.cleaned_data["location"],
                    description=form.cleaned_data.get("description", ""),
                    open_time=form.cleaned_data["open_time"],
                    close_time=form.cleaned_data["close_time"],
                    num_courts=form.cleaned_data["num_courts"],
                )
            messages.success(request, "Submitted! Admin must approve your account before you can sign in.")
            return redirect("images:login")
    else:
        form = ProviderRegisterForm()
    return render(request, "account/provider_register.html", {"form": form})

@staff_member_required
def facility_requests_list(request):
    pending = (FacilitySignupRequest.objects
               .filter(status="pending")
               .select_related("user")
               .order_by("created_at"))
    return render(request, "admin_facility/requests.html", {"pending": pending})



@staff_member_required
@require_POST
def facility_request_approve(request, pk):
    """Approve a provider request: activate the user and mark request approved.
    No Facility is created here; providers must add facilities themselves."""
    req = get_object_or_404(FacilitySignupRequest, pk=pk, status="pending")

    with transaction.atomic():
        user = req.user
        user.is_active = True
        user.save()

        req.status = "approved"
        req.save()

    messages.success(
        request,
        f"Approved '{user.username}'. They can now sign in and add their facilities."
    )
    return redirect("facility_requests")

@staff_member_required
@require_POST
def facility_request_deny(request, pk):
    """Deny a request: delete request + user (as if it never existed)."""
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
    facilities = (Facility.objects
                  .filter(owner=request.user)
                  .prefetch_related("courts__sport"))
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
            # DO NOT set f.sport_type here (we’re not using the choices field)
            f.save()

            # Free-text sport -> ensure it exists in Sport table
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
        else:
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

    return render(request, "provider/manage_courts.html", {"facility": f, "courts": courts, "form": form})
@login_required
def provider_bookings(request):
    if request.user.profile.role != "provider":
        messages.error(request, "Only providers can access this page.")
        return redirect("images:facilities_list")
    bookings = Booking.objects.filter(facility__owner=request.user).select_related("facility", "court", "user").order_by("-start_dt")
    return render(request, "provider/bookings.html", {"bookings": bookings})

def _back_to_facility(facility):
    try:
        return redirect("images:facility_detail", pk=facility.id)  # use pk as your view expects
    except Exception:
        return redirect("images:facilities_list")

@require_http_methods(["GET", "POST"])
@login_required
def book_view(request, facility_id):
    facility = get_object_or_404(Facility, pk=facility_id)

    # court (optional)
    court_id = request.GET.get("court") or request.POST.get("court")
    court = None
    if court_id:
        court = get_object_or_404(Court, pk=court_id, facility=facility)

    # start/end required
    start_str = request.GET.get("start") if request.method == "GET" else request.POST.get("start")
    end_str   = request.GET.get("end")   if request.method == "GET" else request.POST.get("end")
    if not start_str or not end_str:
        messages.error(request, "Missing start or end time.")
        return _back_to_facility(facility)

    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        if timezone.is_naive(start):
            start = timezone.make_aware(start, timezone.get_current_timezone())
        if timezone.is_naive(end):
            end = timezone.make_aware(end, timezone.get_current_timezone())
    except ValueError:
        messages.error(request, "Invalid date/time format.")
        return _back_to_facility(facility)

    if start >= end:
        messages.error(request, "Start must be before end.")
        return _back_to_facility(facility)

    if request.method == "GET":
        return render(
            request,
            "book/confirm.html",
            {"facility": facility, "court": court, "start": start, "end": end},
        )

    # POST: try to create
    clash_qs = Booking.objects.filter(
        facility=facility,
        start_dt__lt=end,
        end_dt__gt=start,
    )
    if court:
        clash_qs = clash_qs.filter(court=court)
    if clash_qs.exists():
        messages.error(request, "That slot is no longer available.")
        return _back_to_facility(facility)

    Booking.objects.create(
        facility=facility,
        court=court,
        user=request.user,
        start_dt=start,
        end_dt=end,
        # status via model default
    )
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

@login_required
def provider_edit_facility(request, facility_id):
    """Provider can edit only their own facility."""
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
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = FacilityForm(instance=facility)

    return render(request, "provider/edit_facility.html", {"form": form, "facility": facility})


# DELETE
@login_required
@require_POST
def provider_delete_facility(request, facility_id):
    """Provider deletes their facility (block if future confirmed bookings exist)."""
    if request.user.profile.role != "provider":
        messages.error(request, "Only providers can access this page.")
        return redirect("images:facilities_list")

    facility = get_object_or_404(Facility, id=facility_id, owner=request.user)

    # Block deletion if there are future confirmed bookings
    has_future_bookings = Booking.objects.filter(
        facility=facility,
        status="confirmed",
        start_dt__gte=timezone.now(),
    ).exists()
    if has_future_bookings:
        messages.error(request, "You cannot delete a facility with future confirmed bookings.")
        return redirect("images:provider_facilities")

    facility.delete()
    messages.success(request, "Facility deleted.")
    return redirect("images:provider_facilities")