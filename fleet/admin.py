from django.contrib import admin

from .models import Car, Extra, Location, OneWayRoute, PickupPoint


class PickupPointInline(admin.TabularInline):
    model = PickupPoint
    extra = 1


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'county', 'phone', 'is_active', 'display_order')
    list_editable = ('is_active', 'display_order')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [PickupPointInline]


@admin.register(OneWayRoute)
class OneWayRouteAdmin(admin.ModelAdmin):
    list_display = ('from_location', 'to_location', 'fee', 'is_active')
    list_filter = ('from_location', 'to_location', 'is_active')


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'category', 'price_per_day', 'units', 'is_active')
    list_filter = ('location', 'category', 'is_active')
    search_fields = ('name',)


@admin.register(Extra)
class ExtraAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'per_day', 'is_active', 'display_order')
    list_editable = ('price', 'per_day', 'is_active', 'display_order')
