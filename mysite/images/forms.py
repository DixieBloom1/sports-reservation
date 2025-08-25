from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from .models import Booking, UserProfile, Court, Facility  # make sure UserProfile exists in models.py

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

class ProviderRegisterForm(forms.Form):
    # account
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class":"form-control form-control-lg"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class":"form-control form-control-lg"}))
    phone = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class":"form-control form-control-lg"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class":"form-control form-control-lg"}))
    # facility (sport text field only for admin info)
    facility_name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"class":"form-control"}))
    offered_sports_text = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class":"form-control", "placeholder":"e.g., Padel, Badminton, Yoga"})
    )
    location = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"class":"form-control"}))
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"class":"form-control", "rows":3}))
    open_time = forms.TimeField(widget=forms.TimeInput(attrs={"type":"time","class":"form-control"}))
    close_time = forms.TimeField(widget=forms.TimeInput(attrs={"type":"time","class":"form-control"}))
    num_courts = forms.IntegerField(min_value=0, initial=1, widget=forms.NumberInput(attrs={"class":"form-control"}))

class FacilityForm(forms.ModelForm):
    class Meta:
        model = Facility
        fields = ["name", "sport_type", "location", "description", "slot_length_minutes", "open_time", "close_time", "base_price", "image"]
        widgets = {
            "name": forms.TextInput(attrs={"class":"form-control"}),
            "sport_type": forms.Select(attrs={"class":"form-select"}),  # dropdown stays
            "location": forms.TextInput(attrs={"class":"form-control"}),
            "description": forms.Textarea(attrs={"class":"form-control", "rows":3}),
            "slot_length_minutes": forms.NumberInput(attrs={"class":"form-control"}),
            "open_time": forms.TimeInput(attrs={"type":"time","class":"form-control"}),
            "close_time": forms.TimeInput(attrs={"type":"time","class":"form-control"}),
            "base_price": forms.NumberInput(attrs={"class":"form-control"}),
            "image": forms.ClearableFileInput(attrs={"class":"form-control"}),
        }

class CourtForm(forms.ModelForm):
    sport_name = forms.CharField(
        max_length=50, label="Sport",
        widget=forms.TextInput(attrs={"class":"form-control", "placeholder":"e.g., Padel"})
    )
    class Meta:
        model = Court
        fields = ["name", "is_active"]
        widgets = {"name": forms.TextInput(attrs={"class":"form-control"})}