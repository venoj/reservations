"""Tests for the reservations application."""

from django.test import TestCase

from reservations.models import Reservation


class ReservationsAppTestCase(TestCase):
    """Basic tests for reservations app (no WTT3; WTT3 is in reservations_connect)."""

    def test_reservation_model_exists(self):
        """Reservation model is available and has expected manager."""
        self.assertTrue(hasattr(Reservation.objects, "get_queryset"))
