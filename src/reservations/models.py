"""Models for the reservations application."""

import logging
from datetime import datetime
from typing import Iterable, Optional

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


class Reservation(models.Model):
    """A model represent a reservation."""

    #: External ID from an external reservation system (e.g. import source).
    external_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("External reservation ID"),
        help_text=_("ID from external reservation system"),
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
