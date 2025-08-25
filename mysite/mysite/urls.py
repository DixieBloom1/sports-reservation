"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from images import views as image_views


urlpatterns = [
    path("admin/requests/", image_views.facility_requests_list, name="facility_requests"),
    path("admin/requests/<int:pk>/approve/", image_views.facility_request_approve, name="facility_request_approve"),
    path("admin/requests/<int:pk>/deny/", image_views.facility_request_deny, name="facility_request_deny"),

    path('admin/', admin.site.urls),
    path("", include("images.urls")),
]
