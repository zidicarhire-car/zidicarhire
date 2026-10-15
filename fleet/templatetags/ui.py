"""Presentation helpers for templates. Nothing here changes what a form accepts."""
from django import template

register = template.Library()

SELECTS = {'select', 'selectmultiple', 'nullbooleanselect'}
LISTS = {'checkboxselectmultiple', 'radioselect'}


@register.filter
def bs(field):
    """
    Renders a form field's widget with Bootstrap classes ({{ form.name|bs }}): form-control, form-select or
    form-check-input, plus is-invalid and aria-describedby when it has errors. Text fields get a placeholder
    (Bootstrap floating labels need one). The widget's own attributes are kept.
    """
    kind = field.widget_type
    if kind in LISTS:
        return field.as_widget()
    attrs = dict(field.field.widget.attrs)
    if kind == 'checkbox':
        css = 'form-check-input'
    elif kind in SELECTS:
        css = 'form-select'
    else:
        css = 'form-control'
        attrs.setdefault('placeholder', field.label or ' ')
    attrs['class'] = ' '.join(filter(None, [attrs.get('class', ''), css, 'is-invalid' if field.errors else '']))
    if field.errors:
        attrs['aria-invalid'] = 'true'
        attrs['aria-describedby'] = f'{field.auto_id}-error'
    elif field.help_text:
        attrs['aria-describedby'] = f'{field.auto_id}-help'
    return field.as_widget(attrs=attrs)


@register.filter
def floats(field):
    """True when the field can use a Bootstrap floating label (not checkboxes, lists or multi-selects)."""
    return field.widget_type not in LISTS | {'checkbox', 'selectmultiple', 'clearablefile', 'file'}
