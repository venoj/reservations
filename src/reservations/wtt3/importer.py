"""Import reservations from WTT3 (Wyse Timetables) API."""

import logging
from datetime import datetime
from typing import Optional

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

from reservations.models import Reservable, Reservation

logger = logging.getLogger(__name__)

User = get_user_model()

def import_reservations_from_wtt3(
    queryset: models.QuerySet,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> tuple[int, int]:
    """Import reservations from Wyse Timetables (WTT3) API.

    Args:
        queryset: Reservation queryset to use for creating/updating records.
        api_url: Base URL for WTT3 API. Defaults to WTT3_API_URL from settings.
        api_key: API key for authentication. Defaults to WTT3_API_KEY from settings.
        start_date: Optional start date filter for reservations.
        end_date: Optional end date filter for reservations.

    Returns:
        Tuple of (created_count, updated_count) reservations.

    Raises:
        requests.RequestException: If API request fails.
    """
    api_url = api_url or getattr(settings, "WTT3_API_URL", "https://wtt3.docs.apiary.io")
    api_key = api_key or getattr(settings, "WTT3_API_KEY", None)

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Build API endpoint URL
    endpoint = f"{api_url}/reservations"
    params = {}

    if start_date:
        params["start"] = start_date.isoformat()
    if end_date:
        params["end"] = end_date.isoformat()

    try:
        logger.info(f"Fetching reservations from WTT3 API: {endpoint}")
        response = requests.get(endpoint, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Handle paginated responses
        reservations_data = data.get("results", data) if isinstance(data, dict) else data
        if not isinstance(reservations_data, list):
            reservations_data = [reservations_data]

        created_count = 0
        updated_count = 0

        for res_data in reservations_data:
            try:
                # Map WTT3 API fields to Reservation model
                external_id = str(res_data.get("id") or res_data.get("reservation_id", ""))

                # Parse datetime fields
                start_str = res_data.get("start") or res_data.get("start_time") or res_data.get("start_datetime")
                end_str = res_data.get("end") or res_data.get("end_time") or res_data.get("end_datetime")

                if not start_str or not end_str:
                    logger.warning(f"Skipping reservation {external_id}: missing start/end times")
                    continue

                # Try parsing ISO format datetime
                try:
                    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    logger.warning(f"Skipping reservation {external_id}: invalid datetime format")
                    continue

                reason = res_data.get("reason") or res_data.get("description") or res_data.get("title") or "Imported from WTT3"

                # Create or update reservation
                reservation, created = queryset.update_or_create(
                    external_id=external_id,
                    defaults={
                        "start": start_dt,
                        "end": end_dt,
                        "reason": reason[:255],
                    }
                )

                # Handle reservables if provided in API response
                reservable_slugs = res_data.get("reservables") or res_data.get("rooms") or []
                if reservable_slugs:
                    for slug in reservable_slugs:
                        try:
                            reservable = Reservable.objects.get(slug=slug)
                            reservation.reservables.add(reservable)
                        except Reservable.DoesNotExist:
                            logger.warning(f"Reservable with slug '{slug}' not found, skipping")

                # Handle owners if provided in API response
                owner_emails = res_data.get("owners") or res_data.get("user_emails") or []
                if owner_emails:
                    for email in owner_emails:
                        try:
                            user = User.objects.get(email=email)
                            reservation.owners.add(user)
                        except User.DoesNotExist:
                            logger.warning(f"User with email '{email}' not found, skipping")

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                logger.error(f"Error processing reservation from WTT3: {e}", exc_info=True)
                continue

        logger.info(f"Successfully imported {created_count} new and updated {updated_count} existing reservations from WTT3")
        return created_count, updated_count

    except requests.RequestException as e:
        logger.error(f"Failed to fetch reservations from WTT3 API: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error importing from WTT3: {e}", exc_info=True)
        raise