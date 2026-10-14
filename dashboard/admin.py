from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import StaffProfile

User = get_user_model()


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    can_delete = False
    verbose_name = 'Branch'
    verbose_name_plural = 'Branch (dashboard access)'


admin.site.unregister(User)


@admin.register(User)
class StaffUserAdmin(UserAdmin):
    inlines = [StaffProfileInline]
    list_display = UserAdmin.list_display + ('branch',)

    @admin.display(description='Branch')
    def branch(self, obj):
        profile = getattr(obj, 'staff_profile', None)
        return profile.location if profile and profile.location else 'All branches'
