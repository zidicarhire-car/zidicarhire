from django import forms
from django.conf import settings

from fleet.models import Car, Location, OneWayRoute, PickupPoint


class CarForm(forms.ModelForm):
    features = forms.MultipleChoiceField(
        choices=Car.FEATURES, required=False, widget=forms.CheckboxSelectMultiple, label='Features')

    class Meta:
        model = Car
        fields = ['name', 'location', 'price_per_day', 'min_booking_fee', 'weekly_rate', 'monthly_rate',
                  'category', 'transmission', 'fuel', 'seats', 'doors', 'luggage', 'engine_size',
                  'air_con', 'units', 'description', 'features', 'is_active']
        labels = {
            'location': 'Branch',
            'luggage': 'Large bags',
            'price_per_day': 'Hire price per day (KES)',
            'min_booking_fee': 'Minimum booking fee (KES, optional)',
            'weekly_rate': 'Weekly price (KES, optional)',
            'monthly_rate': 'Monthly price (KES, optional)',
            'units': 'Number of this car available',
            'is_active': 'Show on website',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, staff_location=None, default_location=None, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['location']
        field.empty_label = None
        if staff_location is not None:
            # Branch staff can only add or move cars within their own branch.
            field.queryset = Location.objects.filter(pk=staff_location.pk)
            field.help_text = 'Cars you add are listed at your branch.'
        self.fields['price_per_day'].help_text = 'What customers pay for each day. Shown on the website as "KES … per day".'
        self.fields['price_per_day'].widget.attrs.update({'inputmode': 'numeric', 'min': 1, 'placeholder': 'e.g. 3500'})
        self.fields['min_booking_fee'].help_text = (
            f'The least a customer pays online to book this car; they pay the rest at pick-up. '
            f'Leave blank for the standard KES {settings.BOOKING_MIN_FEE:,}.')
        self.fields['min_booking_fee'].widget.attrs.update(
            {'inputmode': 'numeric', 'min': 1, 'placeholder': f'{settings.BOOKING_MIN_FEE}'})
        if not self.instance.pk and default_location is not None:
            field.initial = default_location.pk
        if self.instance.pk:
            field.help_text = ('The same car model in another city is a separate car with its own price. '
                               'Change this only when the car has moved branch.')

    def clean(self):
        data = super().clean()
        daily = data.get('price_per_day')
        if daily:
            for field, days, label in (('weekly_rate', 7, 'weekly'), ('monthly_rate', 30, 'monthly')):
                rate = data.get(field)
                if rate and rate >= daily * days:
                    self.add_error(field, f'The {label} price should be less than {days} days at the daily price '
                                          f'(KES {daily * days:,}), or leave it empty.')
        return data

    def clean_min_booking_fee(self):
        fee = self.cleaned_data.get('min_booking_fee')
        if fee is not None and fee < 1:
            raise forms.ValidationError('Enter a booking fee of at least KES 1, or leave it blank.')
        return fee

    def clean_price_per_day(self):
        price = self.cleaned_data['price_per_day']
        if price < 1:
            raise forms.ValidationError('Enter a price of at least KES 1.')
        return price


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['name', 'slug', 'city', 'county', 'address', 'phone', 'whatsapp', 'opening_hours', 'maps_url',
                  'notify_email', 'latitude', 'longitude', 'seo_title', 'meta_description', 'intro',
                  'display_order', 'is_active']
        labels = {'slug': 'Web address name', 'notify_email': 'Branch alert email', 'is_active': 'Show on website'}
        widgets = {
            'intro': forms.Textarea(attrs={'rows': 4}),
            'meta_description': forms.Textarea(attrs={'rows': 2}),
        }


PickupPointFormSet = forms.inlineformset_factory(
    Location, PickupPoint, fields=['name', 'fee', 'display_order', 'is_active'], extra=2, can_delete=False,
    labels={'fee': 'Fee (KES)', 'display_order': 'Order', 'is_active': 'Offer'},
)

RouteFormSet = forms.modelformset_factory(
    OneWayRoute, fields=['from_location', 'to_location', 'fee', 'is_active'], extra=2,
    labels={'from_location': 'From', 'to_location': 'Return to', 'fee': 'One-way fee (KES)', 'is_active': 'Offer'},
)
