"""Models for the reservations application."""

import logging
from datetime import datetime
from typing import Iterable, Optional

import requests
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

class UserProfile(models.Model):
    """The user profile model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        related_name="reservations_profile",
        on_delete=models.CASCADE,
    )


class ReservableSet(models.Model):
    """The set of reservables."""

    #: The name of the set.
    name = models.CharField(
        max_length=255,
        verbose_name=_("ReservableSet name"),
        help_text=_(
            "ReservableSet model is used to group common reservables together."
        ),
    )

    #: The slug of the reservable set.
    slug = models.SlugField(unique=True)

    #: The reservables in this set.
    reservables = models.ManyToManyField("Reservable", related_name="reservableset_set")

    def __str__(self) -> str:
        """Return the human readable representation."""
        return self.name


class Resource(models.Model):
    """The resource a reservable can have."""

    #: The slug of the resource.
    slug = models.SlugField(unique=True)

    # The type of the resource.
    type = models.CharField(max_length=255, help_text=_("The type of the resource."))

    #: The name of the resource.
    name = models.CharField(max_length=255, default="")

    def __str__(self) -> str:
        """Return the human readable representation."""
        return self.slug


class NResources(models.Model):
    """Represent the number of resources the reservable has."""

    #: The resource.
    resource = models.ForeignKey("Resource", on_delete=models.CASCADE)

    #: The reservable.
    reservable = models.ForeignKey("Reservable", on_delete=models.CASCADE)

    #: How many resources the reservable has.
    n = models.IntegerField()

    def __str__(self):
        """Return the human readable representation."""
        return "{0} <= {1} x {2}".format(self.reservable, self.resource, self.n)


class Reservable(models.Model):
    """The reservable object.

    It represents anything we can reserve.
    """

    #: The reservable slug.
    slug = models.SlugField(unique=True)

    #: The reservable type. It is used to group reservables.
    type = models.CharField(max_length=255)

    #: The reservable name.
    name = models.CharField(max_length=255)

    #: The reservable resources.
    resources = models.ManyToManyField("Resource", through="NResources")

    class Meta:
        permissions = (
            ("reserve", "Create a reservation using this reservable"),
            ("double_reserve", "Create an overlapping reservation"),
            ("manage_reservations", "Manage reservations using this reservable"),
        )
        verbose_name = _("reservables")

    def __str__(self) -> str:
        """Return human readable representation."""
        return self.slug


class NRequirements(models.Model):
    """Model represents a requirement a reservation has."""

    #: The resource the reservation requires.
    resource = models.ForeignKey("Resource", on_delete=models.CASCADE)

    #: The reservation.
    reservation = models.ForeignKey("Reservation", on_delete=models.CASCADE)

    #: How many resources the reservatien requires.
    n = models.IntegerField()


class ReservationManager(models.Manager):
    """Custom model manager for reservations."""

    def owned_by_user(self, user) -> models.QuerySet:
        """Get the queryset of reservations (co)owned by the given user."""
        return self.get_queryset().filter(owners=user)

    def prune(self):
        """Delete all reservations without reservables."""
        self.get_queryset().filter(reservables__isnull=True).delete()

    def overlapping(self, start: datetime, end: datetime, reservables: models.QuerySet):
        """Return the set of overlapping reservations for reservables."""
        return Reservation.objects.filter(
            start__lt=end, end=start, reservables__in=reservables.all()
        )

    def import_from_wtt3(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[int, int]:
        """Import reservations from Wyse Timetables (WTT3) API.

        Args:
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
                    reservation, created = self.get_queryset().update_or_create(
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
                        from django.contrib.auth import get_user_model
                        User = get_user_model()
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


class Reservation(models.Model):
    """A model represent a reservation."""

    #: External ID from WTT3 (Wyse Timetables) API
    external_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("External reservation ID"),
        help_text=_("ID from Wyse Timetables (WTT3) API"),
    )

    #: Why the reservation was made.
    reason = models.CharField(
        max_length=255, verbose_name=_("A reason for the reservation.")
    )

    #: Start of the reservation.
    start = models.DateTimeField(verbose_name=_("A start time of the reservation"))

    #: End of the reservation.
    end = models.DateTimeField(verbose_name=_("An end time of the reservation"))

    #: Owners of the reservation.
    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_("The reservation owners")
    )

    #: Reservables in the reservation.
    reservables = models.ManyToManyField(
        "Reservable", verbose_name=_("reservables"), related_name="reservations"
    )

    #: Requirements for the reservation.
    requirements = models.ManyToManyField(
        "Resource",
        through="NRequirements",
        verbose_name=_("resources"),
        help_text=_("Reservation requirements"),
    )

    # Override the default object manager.
    objects = ReservationManager()

    class Meta:
        """Add constraints to the database."""

        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_start_before_end",
                check=models.Q(start__lt=models.F("end")),
            )
        ]

    def overlapping_reservations(
        self, reservables: Optional[Iterable[Reservable]] = None
    ) -> models.QuerySet:
        """Get a queryset of reservations overlapping with this one.

        When reservables are given only check for reservations containing the given
        reservables.
        """
        if reservables is None:
            reservables = self.reservables
        return Reservation.objects.filter(
            start__lt=self.end, end__gt=self.start, reservables__in=reservables.all()
        ).exclude(pk=self.pk)

    def __str__(self) -> str:
        """Return human readable representation."""
        return f"{self.start} <-> {self.end}, {self.reason}"
