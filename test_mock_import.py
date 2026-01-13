#!/usr/bin/env python
"""
Test script for WTT3 import with mock data.
Run: uv run python test_mock_import.py
"""
import os
import django
from unittest.mock import Mock, patch
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
django.setup()

from reservations.models import Reservation, Reservable
from django.contrib.auth import get_user_model

User = get_user_model()

# Mock data that matches WTT3 API format
MOCK_RESERVATIONS_DATA = [
    {
        "id": "wtt3-001",
        "start": "2025-01-15T09:00:00Z",
        "end": "2025-01-15T11:00:00Z",
        "reason": "Predavanje 1",
        "reservables": ["room-101"],
        "owners": ["user1@example.com"],
    },
    {
        "id": "wtt3-002",
        "start": "2025-01-15T14:00:00Z",
        "end": "2025-01-15T16:00:00Z",
        "reason": "Predavanje 2",
        "reservables": ["room-102", "room-103"],
        "owners": ["user2@example.com", "user3@example.com"],
    },
    {
        "id": "wtt3-003",
        "start": "2025-01-16T10:00:00Z",
        "end": "2025-01-16T12:00:00Z",
        "reason": "Predavanje 3",
        "reservables": ["room-101"],
        "owners": [],
    },
]

# Alternative: Paginated response format
MOCK_PAGINATED_RESPONSE = {
    "count": 3,
    "next": None,
    "previous": None,
    "results": MOCK_RESERVATIONS_DATA
}


def setup_test_data():
    """Create test reservables and users."""
    # Create reservables
    reservables = {}
    for slug in ["room-101", "room-102", "room-103"]:
        reservable, _ = Reservable.objects.get_or_create(
            slug=slug,
            defaults={"type": "room", "name": f"Room {slug.split('-')[1]}"}
        )
        reservables[slug] = reservable

    # Create test users
    users = {}
    for email in ["user1@example.com", "user2@example.com", "user3@example.com"]:
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={"username": email.split("@")[0]}
        )
        users[email] = user

    return reservables, users


def test_with_mock_data():
    """Test import with mock data."""
    print("Setting up test data...")
    setup_test_data()

    print("\nTesting import with mock data...")

    # Mock the API response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_RESERVATIONS_DATA
    mock_response.raise_for_status = Mock()

    with patch('reservations.models.requests.get', return_value=mock_response):
        # Import reservations
        # Note: api_url is not actually used since requests.get is mocked
        created, updated = Reservation.objects.import_from_wtt3(
            api_url="https://mock-wtt3-api.example.com"
        )

        print(f"\nImport completed: {created} created, {updated} updated")

        # Verify results
        imported = Reservation.objects.filter(external_id__startswith="wtt3-")
        print(f"\nTotal imported reservations: {imported.count()}")

        for res in imported:
            print(f"\n  - ID: {res.external_id}")
            print(f"    Reason: {res.reason}")
            print(f"    Time: {res.start} to {res.end}")
            print(f"    Reservables: {[r.slug for r in res.reservables.all()]}")
            print(f"    Owners: {[u.email for u in res.owners.all()]}")


def test_with_paginated_response():
    """Test import with paginated API response."""
    print("\n\nTesting with paginated response format...")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_PAGINATED_RESPONSE
    mock_response.raise_for_status = Mock()

    # Clear previous test data
    Reservation.objects.filter(external_id__startswith="wtt3-").delete()

    with patch('reservations.models.requests.get', return_value=mock_response):
        created, updated = Reservation.objects.import_from_wtt3(
            api_url="https://mock-wtt3-api.example.com"
        )
        print(f"Paginated import: {created} created, {updated} updated")


def test_update_existing():
    """Test updating existing reservations."""
    print("\n\nTesting update of existing reservations...")

    # Delete if exists, then create existing reservation
    Reservation.objects.filter(external_id="wtt3-001").delete()
    existing = Reservation.objects.create(
        external_id="wtt3-001",
        start="2025-01-15T09:00:00Z",
        end="2025-01-15T10:00:00Z",
        reason="Old Meeting"
    )

    # Mock response with updated data
    updated_data = MOCK_RESERVATIONS_DATA[0].copy()
    updated_data["reason"] = "Updated Team Meeting"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [updated_data]
    mock_response.raise_for_status = Mock()

    with patch('reservations.models.requests.get', return_value=mock_response):
        created, updated = Reservation.objects.import_from_wtt3(
            api_url="https://mock-wtt3-api.example.com"
        )

        existing.refresh_from_db()
        print(f"Update test: {created} created, {updated} updated")
        print(f"   Reservation reason updated to: {existing.reason}")


if __name__ == "__main__":
    print("Testing WTT3 Import with Mock Data\n")
    print("=" * 50)

    try:
        test_with_mock_data()
        test_with_paginated_response()
        test_update_existing()

        print("\n" + "=" * 50)
        print("All tests completed successfully!")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()