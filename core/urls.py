from django.urls import path

from .views import (
    admin_dashboard,
    manager_login,
    manager_logout,
    availability,
    booking,
    booking_cancellation_confirm,
    booking_cancellation_request,
    cancel_booking,
    complete_booking,
    coaching,
    contact,
    gallery,
    home,
    membership,
    tables,
    tournaments,
)


urlpatterns = [
    path(
        "",
        home,
        name="home",
    ),

    path(
        "tables/",
        tables,
        name="tables",
    ),

    path(
        "book/",
        booking,
        name="booking",
    ),

    path(
        "book/availability/",
        availability,
        name="availability",
    ),

    path(
        "book/cancel/",
        booking_cancellation_request,
        name="booking_cancellation_request",
    ),

    path(
        "book/cancel/confirm/<str:token>/",
        booking_cancellation_confirm,
        name="booking_cancellation_confirm",
    ),

    path(
        "manager/login/",
        manager_login,
        name="manager_login",
    ),

    path(
        "manager/logout/",
        manager_logout,
        name="manager_logout",
    ),

    path(
        "admin-dashboard/",
        admin_dashboard,
        name="admin_dashboard",
    ),

    path(
        "admin-dashboard/bookings/<int:booking_id>/cancel/",
        cancel_booking,
        name="cancel_booking",
    ),

    path(
        "admin-dashboard/bookings/<int:booking_id>/complete/",
        complete_booking,
        name="complete_booking",
    ),

    path(
        "coaching/",
        coaching,
        name="coaching",
    ),

    path(
        "membership/",
        membership,
        name="membership",
    ),

    path(
        "tournaments/",
        tournaments,
        name="tournaments",
    ),

    path(
        "gallery/",
        gallery,
        name="gallery",
    ),

    path(
        "contact/",
        contact,
        name="contact",
    ),
]
