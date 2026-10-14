import json

from django.conf import settings
from django.utils.safestring import mark_safe

_UNSAFE = {ord('<'): '\u003C', ord('>'): '\u003E', ord('&'): '\u0026'}


def _branch(location):
    data = {
        '@type': 'AutoRental',  # schema.org's LocalBusiness type for car hire
        '@id': f'{settings.SITE_URL}{location.get_absolute_url()}#branch',
        'name': f'{settings.BUSINESS["name"]} {location.name}',
        'url': settings.SITE_URL + location.get_absolute_url(),
        'telephone': location.contact_phone,
        'email': settings.BUSINESS['email'],
        'priceRange': 'KES',
        'currenciesAccepted': 'KES',
        'paymentAccepted': 'M-Pesa',
        'address': {
            '@type': 'PostalAddress',
            'addressLocality': location.city,
            'addressRegion': f'{location.county} County' if location.county else location.city,
            'addressCountry': 'KE',
        },
    }
    if location.address:
        data['address']['streetAddress'] = location.address
    if location.latitude is not None and location.longitude is not None:
        data['geo'] = {'@type': 'GeoCoordinates', 'latitude': float(location.latitude),
                       'longitude': float(location.longitude)}
    if location.maps_url:
        data['hasMap'] = location.maps_url
    return data


def branch_jsonld(locations, request=None):
    """LocalBusiness structured data for each branch, ready for a <script type="application/ld+json">."""
    branches = [_branch(loc) for loc in locations]
    if not branches:
        return ''
    doc = {'@context': 'https://schema.org', **branches[0]} if len(branches) == 1 else {
        '@context': 'https://schema.org', '@graph': branches,
    }
    return mark_safe(json.dumps(doc, ensure_ascii=False).translate(_UNSAFE))
