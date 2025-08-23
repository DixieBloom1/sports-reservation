# reservations/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import Booking

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    class Meta:
        model = User
        fields = ["username", "email", "password"]

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["start_dt", "end_dt"]
        widgets = {
            "start_dt": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_dt": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
