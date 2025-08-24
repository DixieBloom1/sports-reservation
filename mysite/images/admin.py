from django.contrib import admin
from .models import Facility, Court, Booking, Blackout, UserProfile


class CourtInline(admin.TabularInline):
    model = Court
    extra = 0

@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "sport_type", "location", "open_time", "close_time", "base_price")
    list_filter = ("sport_type",)
    search_fields = ("name", "location")
    inlines = [CourtInline]

@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("name", "facility", "is_active")
    list_filter = ("facility", "is_active")
    search_fields = ("name", "facility__name")

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("facility", "court", "user", "start_dt", "end_dt", "status", "price")
    list_filter = ("status", "facility", "court")
    search_fields = ("user__username", "facility__name", "court__name")

@admin.register(Blackout)
class BlackoutAdmin(admin.ModelAdmin):
    list_display = ("facility", "start_dt", "end_dt", "reason")

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
