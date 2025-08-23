from django.contrib import admin
from .models import Facility, Booking, Blackout

@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "sport_type", "location", "open_time", "close_time", "base_price")
    search_fields = ("name", "location", "sport_type")

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("facility", "user", "start_dt", "end_dt", "status", "price")
    list_filter = ("status", "facility")
    search_fields = ("user__username", "facility__name")

@admin.register(Blackout)
class BlackoutAdmin(admin.ModelAdmin):
    list_display = ("facility", "start_dt", "end_dt", "reason")
