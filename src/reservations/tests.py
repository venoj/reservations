"""Tests for the reservations application."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone as django_timezone

from reservations.models import Reservation, Reservable


class WTT3ImportTestCase(TestCase):
    """Test cases for WTT3 API import functionality."""

    def setUp(self):
        """Set up test data."""
        self.api_url = "https://wtt3.docs.apiary.io"
        self.mock_reservation_data = {
            "id": "12345",
            "start": "2025-01-10T10:00:00Z",
            "end": "2025-01-10T12:00:00Z",
            "reason": "Test reservation",
            "reservables": [],
            "owners": [],
        }

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_success(self, mock_get):
        """Test successful import from WTT3 API."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [self.mock_reservation_data]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Import reservations
        created, updated = Reservation.objects.import_from_wtt3(
            api_url=self.api_url
        )

        # Assertions
        self.assertEqual(created, 1)
        self.assertEqual(updated, 0)
        self.assertTrue(
            Reservation.objects.filter(external_id="12345").exists()
        )

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_paginated_response(self, mock_get):
        """Test import with paginated API response."""
        # Mock paginated API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [self.mock_reservation_data],
            "count": 1,
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        created, updated = Reservation.objects.import_from_wtt3(
            api_url=self.api_url
        )

        self.assertEqual(created, 1)

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_with_date_filter(self, mock_get):
        """Test import with date range filtering."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [self.mock_reservation_data]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 12, 31, tzinfo=timezone.utc)

        Reservation.objects.import_from_wtt3(
            api_url=self.api_url,
            start_date=start_date,
            end_date=end_date,
        )

        # Verify API was called with date parameters
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertIn("start", call_args.kwargs.get("params", {}))
        self.assertIn("end", call_args.kwargs.get("params", {}))

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_with_api_key(self, mock_get):
        """Test import with API key authentication."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        Reservation.objects.import_from_wtt3(
            api_url=self.api_url, api_key="test-api-key"
        )

        # Verify API was called with authorization header
        mock_get.assert_called_once()
        headers = mock_get.call_args.kwargs.get("headers", {})
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer test-api-key")

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_updates_existing(self, mock_get):
        """Test that existing reservations are updated."""
        # Create existing reservation
        existing = Reservation.objects.create(
            external_id="12345",
            start=django_timezone.now(),
            end=django_timezone.now(),
            reason="Old reason",
        )

        # Mock API response with updated data
        updated_data = self.mock_reservation_data.copy()
        updated_data["reason"] = "Updated reason"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [updated_data]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        created, updated = Reservation.objects.import_from_wtt3(
            api_url=self.api_url
        )

        # Verify update
        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)
        existing.refresh_from_db()
        self.assertEqual(existing.reason, "Updated reason")

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_api_error(self, mock_get):
        """Test handling of API errors."""
        import requests

        # Mock API error
        mock_get.side_effect = requests.RequestException("API Error")

        with self.assertRaises(requests.RequestException):
            Reservation.objects.import_from_wtt3(api_url=self.api_url)

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_with_reservables(self, mock_get):
        """Test import with reservables linking."""
        # Create a reservable
        reservable = Reservable.objects.create(
            slug="test-room", type="room", name="Test Room"
        )

        # Mock API response with reservable
        data_with_reservable = self.mock_reservation_data.copy()
        data_with_reservable["reservables"] = ["test-room"]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [data_with_reservable]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        created, updated = Reservation.objects.import_from_wtt3(
            api_url=self.api_url
        )

        # Verify reservable was linked
        reservation = Reservation.objects.get(external_id="12345")
        self.assertIn(reservable, reservation.reservables.all())