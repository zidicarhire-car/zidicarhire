"""PDF receipt for a paid booking, drawn with ReportLab (pure Python, works on PythonAnywhere)."""
from io import BytesIO

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from fleet import brand
from fleet.models import Location

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
INK = colors.HexColor(brand.INDIGO)
MUTED = colors.HexColor('#5A6380')
LINE = colors.HexColor('#D9DEE6')
YELLOW = colors.HexColor(brand.PLATE_YELLOW)
GREEN = colors.HexColor(brand.MPESA_GREEN)


def kes(amount):
    return f'KES {intcomma(amount)}'


def draw_plate(c, x, top, width):
    """The plate mark from zidicarhire-mark.svg, `width` points wide, top-left at (x, top)."""
    s = width / 212  # the plate is 212 units wide in the SVG
    ox, oy = x - 6 * s, top + 16 * s  # SVG origin so the plate's outer edge lands at (x, top)

    def pt(px, py):
        return ox + px * s, oy - py * s

    def rounded(box, fill):
        x0, y1 = pt(box['x'], box['y'])
        c.setLineWidth(box['stroke'] * s)
        c.setStrokeColor(colors.black)
        c.setFillColor(YELLOW)
        c.roundRect(x0, y1 - box['h'] * s, box['w'] * s, box['h'] * s, box['r'] * s, stroke=1, fill=fill)

    rounded(brand.PLATE, fill=1)
    rounded(brand.PLATE_INNER, fill=0)
    for points, is_hole in brand.letter_polygons():
        path = c.beginPath()
        path.moveTo(*pt(*points[0]))
        for p in points[1:]:
            path.lineTo(*pt(*p))
        path.close()
        c.setFillColor(YELLOW if is_hole else colors.black)
        c.drawPath(path, stroke=0, fill=1)
    return 88 * s  # plate height


def _label_value(c, x, y, label, value, width):
    c.setFont('Helvetica', 9)
    c.setFillColor(MUTED)
    c.drawString(x, y, label)
    c.setFont('Helvetica-Bold', 10)
    c.setFillColor(INK)
    c.drawRightString(x + width, y, value)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(x, y - 5, x + width, y - 5)
    return y - 18


def _when(day, at):
    return f'{day:%a} {day.day} {day:%b %Y}, {at:%H:%M}'


RECEIPT_BRANCH = 'nairobi'   # receipts carry the Nairobi office's address


def receipt_address():
    """The address printed on receipts: the Nairobi branch's (Dashboard > Locations), else BUSINESS_ADDRESS."""
    office = Location.objects.filter(slug=RECEIPT_BRANCH).first()
    if office is None:
        return settings.BUSINESS['address']
    address = office.address.strip()
    if office.city and office.city.lower() not in address.lower():
        address = f'{address}, {office.city}' if address else office.city
    return address


def build_pdf(booking):
    biz = settings.BUSINESS
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f'Receipt {booking.ref}')
    c.setAuthor(biz['name'])
    content_w = PAGE_W - 2 * MARGIN

    # ---- header: plate mark, business details, RECEIPT ----
    top = PAGE_H - MARGIN
    plate_h = draw_plate(c, MARGIN, top, 46 * mm)
    y = top - plate_h - 9 * mm
    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 13)
    c.drawString(MARGIN, y, biz['name'])
    c.setFont('Helvetica', 9)
    c.setFillColor(MUTED)
    details = [receipt_address(), f'Phone {biz["phone"]}' if biz['phone'] else '', biz['email'],
               f'KRA PIN {biz["kra_pin"]}' if biz['kra_pin'] else '',
               f'M-Pesa till {biz["till_number"]}' if biz['till_number'] else '']
    for line in filter(None, details):
        y -= 12
        c.drawString(MARGIN, y, line)

    right = PAGE_W - MARGIN
    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 26)
    c.drawRightString(right, top - 26, 'RECEIPT')
    paid_at = timezone.localtime(booking.paid_at) if booking.paid_at else None
    meta = [('Booking number', booking.ref),
            ('Date paid', f'{paid_at:%d %b %Y, %H:%M}' if paid_at else '-'),
            ('M-Pesa receipt', booking.mpesa_receipt or '-')]
    my = top - 50
    for label, value in meta:
        c.setFont('Helvetica', 9)
        c.setFillColor(MUTED)
        c.drawRightString(right - 95, my, label)
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(INK)
        c.drawRightString(right, my, value)
        my -= 15

    # ---- customer and hire ----
    y = min(y, my) - 12 * mm
    col_w = (content_w - 10 * mm) / 2
    left_x, right_x = MARGIN, MARGIN + col_w + 10 * mm
    for x, title in ((left_x, 'Customer'), (right_x, 'Car hire')):
        c.setFont('Helvetica-Bold', 11)
        c.setFillColor(INK)
        c.drawString(x, y, title)
    ly = ry = y - 18
    ly = _label_value(c, left_x, ly, 'Name', booking.customer_name[:40], col_w)
    ly = _label_value(c, left_x, ly, 'Phone', booking.masked_phone, col_w)
    if booking.email:
        ly = _label_value(c, left_x, ly, 'Email', booking.email[:40], col_w)

    city = booking.pickup_location.name if booking.pickup_location_id else biz['location']
    where = f'{booking.pickup_point.name[:34]}, {city}' if booking.pickup_point_id else city
    back = booking.return_location.name if booking.return_location_id else city
    ry = _label_value(c, right_x, ry, 'Car', booking.car.name[:40], col_w)
    ry = _label_value(c, right_x, ry, 'Pick-up', _when(booking.pickup_date, booking.pickup_time), col_w)
    ry = _label_value(c, right_x, ry, 'Pick-up place', where[:44], col_w)
    ry = _label_value(c, right_x, ry, 'Return', _when(booking.return_date, booking.return_time), col_w)
    ry = _label_value(c, right_x, ry, 'Return place', back, col_w)
    ry = _label_value(c, right_x, ry, 'Days', str(booking.days), col_w)

    # ---- price breakdown ----
    y = min(ly, ry) - 8 * mm
    c.setFont('Helvetica-Bold', 11)
    c.setFillColor(INK)
    c.drawString(MARGIN, y, 'Price')
    y -= 18
    for line in booking.price_lines():
        if line.get('total'):
            c.setStrokeColor(INK)
            c.setLineWidth(1)
            c.line(MARGIN, y + 11, right, y + 11)
            c.setFont('Helvetica-Bold', 12)
            c.drawString(MARGIN, y - 3, 'Total')
            c.drawRightString(right, y - 3, kes(line['amount']))
            y -= 22
        else:
            c.setFont('Helvetica', 10)
            c.setFillColor(INK)
            c.drawString(MARGIN, y, line['label'][:70])
            c.drawRightString(right, y, kes(line['amount']))
            y -= 15

    paid = booking.amount_paid or booking.amount
    y = _label_value(c, MARGIN, y - 4, 'Amount paid', kes(paid), content_w)
    if paid != booking.amount:
        diff = booking.amount - paid
        label = 'Balance due at pick-up' if diff > 0 else 'To be refunded'
        y = _label_value(c, MARGIN, y, label, kes(abs(diff)), content_w)
    y = _label_value(c, MARGIN, y, 'Payment method', 'M-Pesa', content_w)

    # ---- status stamp ----
    stamp = 'BOOKING FEE PAID' if paid < booking.amount else 'PAID'
    stamp_w = c.stringWidth(stamp, 'Helvetica-Bold', 12) + 12 * mm
    c.setFillColor(GREEN)
    c.roundRect(MARGIN, y - 22, max(34 * mm, stamp_w), 24, 4, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 12)
    c.drawCentredString(MARGIN + max(34 * mm, stamp_w) / 2, y - 14, stamp)

    # ---- footer ----
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(MARGIN, 30 * mm, right, 30 * mm)
    c.setFillColor(INK)
    c.setFont('Helvetica-Bold', 10)
    c.drawString(MARGIN, 24 * mm, f'Thank you for hiring with {biz["name"]}.')
    c.setFont('Helvetica', 8.5)
    c.setFillColor(MUTED)
    c.drawString(MARGIN, 19 * mm, f'Terms of hire: {settings.SITE_URL}/terms/')
    c.drawString(MARGIN, 15 * mm, f'Questions about this booking? Call {biz["phone"]} or email {biz["email"]}, '
                                  f'and quote {booking.ref}.')
    c.showPage()
    c.save()
    return buf.getvalue()
