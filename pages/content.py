"""
Questions and answers shown on the FAQ page (and the first few on the home page).

Answers marked OWNER_TO_CONFIRM depend on your own rules (deposit, age, fuel, cancellations). They show
on the site with a yellow "Owner to confirm" note until you replace the text here and set `confirmed=True`.
"""
OWNER_TO_CONFIRM = False


def faq(settings_):
    hold = settings_.BOOKING_HOLD_MINUTES
    return [
        {
            'q': 'How do I pay?',
            'a': ('With M-Pesa. When you book, we send a payment prompt to your phone. Enter your M-Pesa PIN '
                  'and your booking is confirmed straight away. We hold the car for you for '
                  f'{hold} minutes while you pay.'),
            'confirmed': True, 'home': True,
        },
        {
            'q': 'What do I need to bring when I collect the car?',
            'a': ('Your national ID or passport and your driving licence, with the same numbers you gave '
                  'when booking.'),
            'confirmed': True, 'home': True,
        },
        {
            'q': 'Can I collect the car at the airport or my hotel?',
            'a': ('Yes. When you book, choose where to collect the car: our branch office, the airport or '
                  'hotel delivery. Any pick-up fee is shown before you pay.'),
            'confirmed': True, 'home': True,
        },
        {
            'q': 'How are the days counted?',
            'a': ('Every started 24 hours counts as a day. Pick up on Monday at 10:00 and return on Thursday at '
                  '10:00, and it is 3 days. Return at 11:00 and it becomes 4. Hires of 7 days or more often '
                  'cost less per day.'),
            'confirmed': True, 'home': True,
        },
        {
            'q': 'Can I return the car in another city?',
            'a': ('Yes, on the routes listed when you book, for a one-way fee. Choose the city under '
                  '"Return to" in the search or the booking form.'),
            'confirmed': True,
        },
        {
            'q': 'Where is my receipt?',
            'a': ('We email it to you as a PDF when you pay, if you gave an email address. You can also '
                  'download it any time from "Find my booking" with your booking number and phone number.'),
            'confirmed': True,
        },
        {
            'q': 'Is there a security deposit?',
            'a': 'Explain whether you take a deposit, how much, how it is paid and when it is returned.',
            'confirmed': OWNER_TO_CONFIRM,
        },
        {
            'q': 'How old do I need to be to hire a car?',
            'a': 'Give your minimum age and how long the driver must have held a licence.',
            'confirmed': OWNER_TO_CONFIRM,
        },
        {
            'q': 'Is fuel included? Is there a mileage limit?',
            'a': 'Explain your fuel policy (for example full to full) and any daily mileage limit.',
            'confirmed': OWNER_TO_CONFIRM,
        },
        {
            'q': 'Can I change or cancel my booking?',
            'a': ('Explain your cancellation and refund rules. Customers can change bookings by chat, '
                  'WhatsApp or phone, quoting the booking number.'),
            'confirmed': OWNER_TO_CONFIRM,
        },
    ]
