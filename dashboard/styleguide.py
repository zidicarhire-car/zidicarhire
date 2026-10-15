"""
Staff-only style guide (/dashboard/styleguide/) and the colour contrast rules it shows.

The same CONTRAST_PAIRS are checked against static/css/theme.css in light and dark mode by
dashboard/tests_design.py, so a colour change that breaks WCAG AA fails the tests.
"""
import re
from pathlib import Path

from django.conf import settings
from django.shortcuts import render

from .views import _ctx, staff_page

TOKENS_CSS = Path(settings.BASE_DIR) / 'static' / 'css' / 'theme.css'

COLOR_GROUPS = [
    ('Brand', [
        ('--brand', 'Indigo: header, footer, primary buttons'),
        ('--on-brand', 'Text on indigo'),
        ('--on-brand-muted', 'Secondary text on indigo'),
        ('--plate', 'Number-plate yellow: prices, refs, step numbers'),
        ('--plate-ink', 'Text and border on plate yellow'),
        ('--mpesa', 'M-Pesa green: icons, ticks, paid accents'),
        ('--mpesa-fill', 'M-Pesa button background'),
    ]),
    ('Surfaces and text', [
        ('--bg', 'Page background'),
        ('--surface', 'Cards, panels, inputs'),
        ('--surface-2', 'Sunken areas and hovered rows'),
        ('--placeholder', 'Photo boxes while loading'),
        ('--text', 'Body text'),
        ('--text-muted', 'The one muted grey'),
        ('--border', 'The one border grey'),
        ('--control-border', 'Input and checkbox outlines'),
        ('--primary', 'Primary button (light in dark mode)'),
        ('--focus', 'Keyboard focus ring'),
    ]),
    ('Feedback', [
        ('--danger', 'Errors'),
        ('--danger-bg', 'Error background'),
        ('--success-bg', 'Paid / success background'),
        ('--success-text', 'Paid / success text'),
        ('--warn-bg', 'Pending / warning background'),
        ('--warn-text', 'Pending / warning text'),
        ('--info-bg', 'Picked-up background'),
        ('--info-text', 'Picked-up text'),
    ]),
]

# (foreground, background, minimum ratio, what it is). 4.5 = body text, 3 = large text and UI parts.
CONTRAST_PAIRS = [
    ('--text', '--bg', 4.5, 'Body text on the page'),
    ('--text', '--surface', 4.5, 'Body text on a card'),
    ('--text', '--surface-2', 4.5, 'Body text in a sunken box'),
    ('--text-muted', '--bg', 4.5, 'Muted text on the page'),
    ('--text-muted', '--surface', 4.5, 'Muted text on a card'),
    ('--text-muted', '--surface-2', 4.5, 'Muted text in a sunken box'),
    ('--on-brand', '--brand', 4.5, 'Header and footer text'),
    ('--on-brand-muted', '--brand', 4.5, 'Secondary header and footer text'),
    ('--plate-ink', '--plate', 4.5, 'Number plate'),
    ('--plate', '--brand', 3, 'Yellow button on the indigo header'),
    ('--plate-ink', '--plate-hover', 4.5, 'Yellow button, hovered'),
    ('--plate', '--brand', 3, 'Yellow focus ring on indigo'),
    ('--focus-surface', '--surface', 3, 'Focus ring inside white boxes'),
    ('--link', '--bg', 4.5, 'Links on the page'),
    ('--link', '--surface', 4.5, 'Links on a card'),
    ('--on-primary', '--primary', 4.5, 'Primary button label'),
    ('--on-mpesa', '--mpesa-fill', 4.5, 'M-Pesa button label'),
    ('--mpesa', '--surface', 3, 'M-Pesa icons and ticks on a card'),
    ('--danger', '--surface', 4.5, 'Error text on a card'),
    ('--danger', '--danger-bg', 4.5, 'Error alert and failed status'),
    ('--success-text', '--success-bg', 4.5, 'Paid status'),
    ('--warn-text', '--warn-bg', 4.5, 'Pending status'),
    ('--text', '--warn-bg', 4.5, 'Text in a warning box'),
    ('--text-muted', '--warn-bg', 4.5, 'Muted text in a warning box'),
    ('--info-text', '--info-bg', 4.5, 'Picked-up status'),
    ('--neutral-text', '--neutral-bg', 4.5, 'Returned status and quiet tags'),
    ('--text', '--danger-bg', 4.5, 'Text in an error alert'),
    ('--text', '--success-bg', 4.5, 'Text in a success alert'),
    ('--text', '--info-bg', 4.5, 'Text in an info alert'),
    ('--control-border', '--surface', 3, 'Input outline'),
    ('--focus', '--surface', 3, 'Focus ring on a card'),
    ('--focus', '--bg', 3, 'Focus ring on the page'),
]


def read_tokens(css=None):
    """{'light': {name: value}, 'dark': {...}} with var() references resolved. Dark inherits light."""
    css = css if css is not None else TOKENS_CSS.read_text(encoding='utf-8')
    decl = re.compile(r'(--[\w-]+)\s*:\s*([^;]+);')
    light_match = re.search(r'^:root \{(.*?)^\}', css, re.S | re.M)
    dark_match = re.search(r'^\[data-bs-theme="dark"\] \{(.*?)^\}', css, re.S | re.M)
    light = dict(decl.findall(light_match.group(1) if light_match else ''))
    dark = {**light, **dict(decl.findall(dark_match.group(1) if dark_match else ''))}

    def resolve(values):
        out = {}
        for name, value in values.items():
            value = value.strip()
            for _ in range(5):
                ref = re.fullmatch(r'var\((--[\w-]+)\)', value)
                if not ref:
                    break
                value = values.get(ref.group(1), value).strip()
            out[name] = value
        return out
    return {'light': resolve(light), 'dark': resolve(dark)}


def _luminance(hex_color):
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(fg, bg):
    """WCAG 2 contrast ratio between two #rrggbb colours."""
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def contrast_report(tokens=None):
    tokens = tokens or read_tokens()
    rows = []
    for fg, bg, minimum, label in CONTRAST_PAIRS:
        row = {'fg': fg, 'bg': bg, 'min': minimum, 'label': label}
        for mode in ('light', 'dark'):
            ratio = contrast(tokens[mode][fg], tokens[mode][bg])
            row[mode] = round(ratio, 2)
            row[f'{mode}_ok'] = ratio >= minimum
        rows.append(row)
    return rows


SPACE = [('--space-1', 4), ('--space-2', 8), ('--space-3', 12), ('--space-4', 16), ('--space-5', 24),
         ('--space-6', 32), ('--space-7', 48), ('--space-8', 64), ('--space-9', 96)]
STATUSES = [('pending', 'Waiting for payment'), ('paid', 'Paid'), ('picked_up', 'Picked up'),
            ('completed', 'Returned'), ('cancelled', 'Cancelled'), ('failed', 'Payment failed')]


@staff_page
def styleguide(request):
    tokens = read_tokens()
    groups = [(title, [{'name': n, 'use': use, 'light': tokens['light'].get(n), 'dark': tokens['dark'].get(n)}
                       for n, use in items]) for title, items in COLOR_GROUPS]
    return render(request, 'dashboard/styleguide.html', _ctx(
        request, nav='styleguide', color_groups=groups, pairs=contrast_report(tokens),
        space=SPACE, statuses=STATUSES,
    ))
