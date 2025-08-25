from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import LoginForm

app_name = "images"

urlpatterns = [
    path("", views.home, name="facilities_list"),
    path("facilities/<int:pk>/", views.facility_detail, name="facility_detail"),
    path("register/", views.register_view, name="register"),
    path("login/", auth_views.LoginView.as_view(
        template_name="account/login.html",
        authentication_form=LoginForm
    ), name="login"),
    path("book/<int:facility_id>/", views.book_view, name="book"),
    path("bookings/", views.my_bookings, name="my_bookings"),
    path("bookings/<int:pk>/cancel/", views.cancel_booking, name="cancel_booking"),
    path("admin/reports/usage.csv", views.usage_report_csv, name="usage_report"),
    path("profile/", views.profile_view, name="profile"),
    path("logout/", views.logout_post, name="logout"),
    path("bookings/<int:pk>/confirmed/", views.booking_confirmed, name="booking_confirmed"),
    path("bookings/<int:pk>/modify/", views.modify_booking, name="modify_booking"),
    path("provider/register/", views.provider_register_view, name="provider_register"),
    path("provider/facilities/", views.provider_facilities, name="provider_facilities"),
    path("provider/facilities/add/", views.provider_add_facility, name="provider_add_facility"),
    path("provider/facilities/<int:facility_id>/courts/", views.provider_manage_courts, name="provider_manage_courts"),
    path("provider/bookings/", views.provider_bookings, name="provider_bookings"),
    path("provider/facilities/<int:facility_id>/edit/", views.provider_edit_facility, name="provider_edit_facility"),
    path("provider/facilities/<int:facility_id>/delete/", views.provider_delete_facility, name="provider_delete_facility"),
    path("provider/facilities/<int:facility_id>/blackouts/",
         views.provider_manage_blackouts, name="provider_manage_blackouts"),
    path("provider/facilities/<int:facility_id>/blackouts/<int:blackout_id>/delete/",
         views.provider_delete_blackout, name="provider_delete_blackout"),
]

