import json
import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.safestring import mark_safe

from bookings.notifications import branch_recipients, send_alert
from bookings.utils import rate_limited
from fleet.models import Location

from .content import faq
from .models import ContactMessage

logger = logging.getLogger(__name__)

_UNSAFE = {ord('<'): '\\u003C', ord('>'): '\\u003E', ord('&'): '\\u0026'}


def faq_jsonld(items):
    """FAQPage structured data, only for answers the owner has confirmed."""
    doc = {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
        {'@type': 'Question', 'name': item['q'], 'acceptedAnswer': {'@type': 'Answer', 'text': item['a']}}
        for item in items if item['confirmed']
    ]}
    return mark_safe(json.dumps(doc, ensure_ascii=False).translate(_UNSAFE))


def about(request):
    return render(request, 'pages/about.html', {'branches_list': Location.objects.active()})


def faq_page(request):
    items = faq(settings)
    return render(request, 'pages/faq.html', {'faq': items, 'jsonld': faq_jsonld(items)})


def terms(request):
    return render(request, 'pages/terms.html')


def privacy(request):
    return render(request, 'pages/privacy.html')


class ContactForm(forms.Form):
    name = forms.CharField(max_length=120, label='Your name',
                           error_messages={'required': 'Enter your name so we know who to reply to.'})
    phone = forms.CharField(max_length=20, required=False, label='Phone number',
                            widget=forms.TextInput(attrs={'type': 'tel', 'inputmode': 'tel', 'autocomplete': 'tel'}))
    email = forms.EmailField(required=False, label='Email',
                             error_messages={'invalid': 'That email address looks incomplete. Check it, or leave it blank.'},
                             widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    location = forms.ModelChoiceField(queryset=Location.objects.none(), required=False, label='City',
                                      empty_label='Any city')
    message = forms.CharField(max_length=3000, widget=forms.Textarea(attrs={'rows': 5}), label='Your message',
                              error_messages={'required': 'Write your message.'})
    website = forms.CharField(required=False, label='Leave this empty',
                              widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].queryset = Location.objects.active()

    def clean(self):
        data = super().clean()
        if not data.get('phone') and not data.get('email') and 'phone' not in self.errors:
            self.add_error('phone', 'Give a phone number or an email address so we can reply.')
        return data


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if request.POST.get('website'):  # spam bots fill the hidden field
            return redirect('pages:contact')
        if rate_limited(request, 'contact', limit=5, window_seconds=3600):
            form.add_error(None, 'You have sent several messages already. Call or WhatsApp us instead.')
        elif form.is_valid():
            msg = ContactMessage.objects.create(
                name=form.cleaned_data['name'], phone=form.cleaned_data['phone'], email=form.cleaned_data['email'],
                location=form.cleaned_data['location'], message=form.cleaned_data['message'],
            )
            city = msg.location.name if msg.location_id else 'any city'
            send_alert(f'Website message from {msg.name} ({city})',
                  f'{msg.name} wrote through the contact form:\n\n{msg.message}\n\n'
                  f'Phone: {msg.phone or "-"}\nEmail: {msg.email or "-"}\nCity: {city}\n\n'
                  f'All messages: {settings.SITE_URL}/django-admin/pages/contactmessage/\n',
                  branch_recipients(msg.location))
            messages.success(request, "Thanks, your message was sent. We'll get back to you soon, usually within a few hours.")
            return redirect('pages:contact')
    else:
        form = ContactForm()
    return render(request, 'pages/contact.html', {'form': form})
