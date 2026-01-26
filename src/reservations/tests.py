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
        self.api_url = "https://wise-tt.com/wtt_demo/ws/rest"
        self.api_key = "test-token"
        self.mock_reservation_data = {
            "id": "R12345",
            "startDate": "10.01.2025",
            "endDate": "10.01.2025",
            "startHour": "10:00",
            "endHour": "12:00",
            "note": "Test reservation",
            "course": "Test Course",
            "rooms": ["A-001"],
            "roomIds": [1],
            "lecturers": [],
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
            api_url=self.api_url,
            api_key=self.api_key
        )

        # Assertions
        self.assertEqual(created, 1)
        self.assertEqual(updated, 0)
        self.assertTrue(
            Reservation.objects.filter(external_id="R12345").exists()
        )
        reservation = Reservation.objects.get(external_id="R12345")
        self.assertEqual(reservation.reason, "Test reservation")

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_paginated_response(self, mock_get):
        """Test import with multiple dates."""
        # Mock API response for multiple dates
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [self.mock_reservation_data]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        start_date = datetime(2025, 1, 10, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 11, tzinfo=timezone.utc)

        created, updated = Reservation.objects.import_from_wtt3(
            api_url=self.api_url,
            api_key=self.api_key,
            start_date=start_date,
            end_date=end_date
        )

        # Should be called multiple times (once per date)
        self.assertGreater(mock_get.call_count, 0)
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
        end_date = datetime(2025, 1, 2, tzinfo=timezone.utc)

        Reservation.objects.import_from_wtt3(
            api_url=self.api_url,
            api_key=self.api_key,
            start_date=start_date,
            end_date=end_date,
        )

        self.assertGreater(mock_get.call_count, 0)
        call_args = mock_get.call_args
        params = call_args.kwargs.get("params", {})
        self.assertIn("date", params)
        self.assertRegex(params["date"], r"\d{2}_\d{2}_\d{4}")

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
        self.assertGreater(mock_get.call_count, 0)
        headers = mock_get.call_args.kwargs.get("headers", {})
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer test-api-key")

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_updates_existing(self, mock_get):
        """Test that existing reservations are updated."""
        # Create existing reservation
        existing = Reservation.objects.create(
            external_id="R12345",
            start=django_timezone.now(),
            end=django_timezone.now(),
            reason="Old reason",
        )

        # Mock API response with updated data
        updated_data = self.mock_reservation_data.copy()
        updated_data["note"] = "Updated reason"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [updated_data]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        created, updated = Reservation.objects.import_from_wtt3(
            api_url=self.api_url,
            api_key=self.api_key
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

        created, updated = Reservation.objects.import_from_wtt3(
            api_url=self.api_url,
            api_key=self.api_key
        )
        self.assertEqual(created, 0)
        self.assertEqual(updated, 0)

    @patch("reservations.wtt3.importer.requests.get")
    def test_import_from_wtt3_with_reservables(self, mock_get):
        """Test import with reservables linking."""
        # Create a reservable
        reservable = Reservable.objects.create(
            slug="a-001", type="room", name="A-001"
        )

        # Mock API response with reservable
        data_with_reservable = self.mock_reservation_data.copy()
        data_with_reservable["rooms"] = ["A-001"]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [data_with_reservable]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        created, updated = Reservation.objects.import_from_wtt3(
            api_url=self.api_url,
            api_key=self.api_key
        )

        # Verify reservable was linked
        reservation = Reservation.objects.get(external_id="R12345")
        self.assertIn(reservable, reservation.reservables.all())