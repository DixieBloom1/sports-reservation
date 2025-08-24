from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from .models import Booking, UserProfile, Court  # make sure UserProfile exists in models.py

class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "class": "form-control form-control-lg", "placeholder": "Username"
        })
        self.fields["password"].widget.attrs.update({
            "class": "form-control form-control-lg", "placeholder": "Password"
        })

class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control form-control-lg", "placeholder": "Password"})
    )
    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "class": "form-control form-control-lg", "placeholder": "Username"
        })
        self.fields["email"].widget.attrs.update({
            "class": "form-control form-control-lg", "placeholder": "Email"
        })

class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control form-control-lg", "placeholder": "Username"}),
            "email": forms.EmailInput(attrs={"class": "form-control form-control-lg", "placeholder": "Email"}),
        }

class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["phone"]
        widgets = {
            "phone": forms.TextInput(attrs={"class": "form-control form-control-lg", "placeholder": "+385..."}),
        }

class BookingForm(forms.ModelForm):
    court = forms.ModelChoiceField(queryset=Court.objects.none(), required=False)

    class Meta:
        model = Booking
        fields = ["court", "start_dt", "end_dt"]
        widgets = {
            "start_dt": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "end_dt": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
        }

    def __init__(self, *args, facility=None, **kwargs):
        super().__init__(*args, **kwargs)
        has_courts = False
        if facility is not None:
            qs = facility.courts.filter(is_active=True)
            self.fields["court"].queryset = qs
            has_courts = qs.exists()
        # If no courts, hide field and make it optional
        if not has_courts:
            self.fields["court"].required = False
            self.fields["court"].widget = forms.HiddenInput()