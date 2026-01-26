"""Import reservations from WTT3 (Wyse Timetables) API."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

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
        api_key: Bearer token for authentication. Defaults to WTT3_API_KEY from settings.
        start_date: Optional start date filter for reservations.
        end_date: Optional end date filter for reservations.

    Returns:
        Tuple of (created_count, updated_count) reservations.

    Raises:
        requests.RequestException: If API request fails.
    """
    api_url = api_url or getattr(settings, "WTT3_API_URL", "https://wise-tt.com/wtt_demo/ws/rest")
    api_key = api_key or getattr(settings, "WTT3_API_KEY", None)

    if not api_key:
        raise ValueError("WTT3_API_KEY must be configured.")

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    if start_date and end_date:
        current_date = start_date.date()
        end_date_only = end_date.date()
        dates_to_fetch = []
        while current_date <= end_date_only:
            dates_to_fetch.append(current_date)
            current_date += timedelta(days=1)
    elif start_date:
        dates_to_fetch = [start_date.date()]
    else:
        dates_to_fetch = [datetime.now().date()]

    created_count = 0
    updated_count = 0
    all_reservations = {}

    for date_obj in dates_to_fetch:
        # Convert date to WTT3 format: dd_mm_yyyy
        date_str = date_obj.strftime("%d_%m_%Y")
        endpoint = f"{api_url}/scheduleDateDetail"
        params = {"date": date_str}

        try:
            logger.info(f"Fetching reservations from WTT3 API for date {date_str}: {endpoint}")
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list):
                logger.warning(f"Unexpected response format for date {date_str}: expected list, got {type(data)}")
                continue

            for item in data:
                # Only process reservations (ID starts with "R")
                item_id = str(item.get("id", ""))
                if not item_id.startswith("R"):
                    continue  # Skip schedules (starting with "S")

                if item_id not in all_reservations:
                    all_reservations[item_id] = item

        except requests.RequestException as e:
            logger.error(f"Failed to fetch reservations from WTT3 API for date {date_str}: {e}")
            continue

    for res_data in all_reservations.values():
        try:
            external_id = str(res_data.get("id", ""))
            if not external_id.startswith("R"):
                continue

            start_date_str = res_data.get("startDate", "")  # Format: "dd.mm.yyyy"
            end_date_str = res_data.get("endDate", "")  # Format: "dd.mm.yyyy"
            start_hour_str = res_data.get("startHour", "")  # Format: "HH:mm"
            end_hour_str = res_data.get("endHour", "")  # Format: "HH:mm"

            if not all([start_date_str, end_date_str, start_hour_str, end_hour_str]):
                logger.warning(f"Skipping reservation {external_id}: missing date/time fields")
                continue

            try:
                # Parse start datetime: "dd.mm.yyyy" + "HH:mm"
                start_date_parts = start_date_str.split(".")
                start_hour_parts = start_hour_str.split(":")
                start_dt = timezone.make_aware(datetime(
                    year=int(start_date_parts[2]),
                    month=int(start_date_parts[1]),
                    day=int(start_date_parts[0]),
                    hour=int(start_hour_parts[0]),
                    minute=int(start_hour_parts[1])
                ))

                # Parse end datetime: "dd.mm.yyyy" + "HH:mm"
                end_date_parts = end_date_str.split(".")
                end_hour_parts = end_hour_str.split(":")
                end_dt = timezone.make_aware(datetime(
                    year=int(end_date_parts[2]),
                    month=int(end_date_parts[1]),
                    day=int(end_date_parts[0]),
                    hour=int(end_hour_parts[0]),
                    minute=int(end_hour_parts[1])
                ))
            except (ValueError, IndexError, AttributeError) as e:
                logger.warning(f"Skipping reservation {external_id}: invalid date/time format - {e}")
                continue

            reason = (
                res_data.get("note") or
                res_data.get("course") or
                "Imported from WTT3"
            )

            # Create or update reservation
            reservation, created = queryset.update_or_create(
                external_id=external_id,
                defaults={
                    "start": start_dt,
                    "end": end_dt,
                    "reason": reason[:255] if reason else "Imported from WTT3",
                }
            )

            # Handle reservables (rooms)
            room_names = res_data.get("rooms", [])
            if room_names:
                for room_name in room_names:
                    try:
                        reservable = Reservable.objects.filter(name=room_name).first()
                        if not reservable:
                            # Try by slug
                            reservable = Reservable.objects.filter(slug=room_name.lower().replace(" ", "-")).first()
                        if reservable:
                            reservation.reservables.add(reservable)
                        else:
                            logger.debug(f"Reservable with name '{room_name}' not found, skipping")
                    except Exception as e:
                        logger.warning(f"Error linking reservable '{room_name}': {e}")

            if created:
                created_count += 1
            else:
                updated_count += 1

        except Exception as e:
            logger.error(f"Error processing reservation from WTT3: {e}", exc_info=True)
            continue

    logger.info(f"Successfully imported {created_count} new and updated {updated_count} existing reservations from WTT3")
    return created_count, updated_count