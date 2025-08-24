from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "images"

urlpatterns = [
    path("", views.home, name="facilities_list"),
    path("facilities/<int:pk>/", views.facility_detail, name="facility_detail"),
    path("register/", views.register_view, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="account/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("book/<int:facility_id>/", views.book_view, name="book"),
    path("bookings/", views.my_bookings, name="my_bookings"),
    path("bookings/<int:pk>/cancel/", views.cancel_booking, name="cancel_booking"),
    path("admin/reports/usage.csv", views.usage_report_csv, name="usage_report"),
    path("profile/", views.profile_view, name="profile"),
    path("logout/", views.logout_post, name="logout"),
    path("bookings/<int:pk>/confirmed/", views.booking_confirmed, name="booking_confirmed"),
    path("bookings/<int:pk>/modify/", views.modify_booking, name="modify_booking"),
]

