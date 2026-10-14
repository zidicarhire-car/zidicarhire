from django.conf import settings
from django.db import models


class StaffProfile(models.Model):
    """Ties a staff account to one branch. Staff without a branch (the owner) see all of Kenya."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_profile')
    location = models.ForeignKey(
        'fleet.Location', on_delete=models.PROTECT, null=True, blank=True, related_name='staff',
        help_text="Leave blank for someone who manages every branch. Superusers always see everything.",
    )

    def __str__(self):
        return f'{self.user.get_username()} ({self.location or "all branches"})'


def staff_location(user):
    """The branch this staff member is limited to, or None if they can see all of Kenya."""
    if not user.is_authenticated or user.is_superuser:
        return None
    try:
        return user.staff_profile.location
    except StaffProfile.DoesNotExist:
        return None
