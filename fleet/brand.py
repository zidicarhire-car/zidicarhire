"""
The ZidiCarHire number-plate mark as plain geometry, copied from static/img/zidicarhire-mark.svg,
so the Pillow images (apple-touch icon, Open Graph image) and the ReportLab receipt draw the
same shape as the SVG logo files.

Coordinates use the SVG's own space: the plate fills x 6..218, y 16..104 (212 x 88).
"""

INDIGO = '#1C2340'
PLATE_YELLOW = '#F6C21C'
BLACK = '#000000'
MPESA_GREEN = '#2E9E3E'

PLATE_BOX = (0, 10, 224, 110)  # area to fit the plate into, including its 6px outline

PLATE = {'x': 6, 'y': 16, 'w': 212, 'h': 88, 'r': 12, 'stroke': 6}
PLATE_INNER = {'x': 15, 'y': 25, 'w': 194, 'h': 70, 'r': 6, 'stroke': 2}
LETTERS_DX = 5  # the letters group is translated 5 units right in the SVG


def _cubic(p0, p1, p2, p3, steps=12):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        pts.append((
            mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
            mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1],
        ))
    return pts


def letter_polygons():
    """
    'ZIDI' as filled polygons. Returns a list of (points, is_hole). Holes (the inside of the D)
    must be painted in the plate colour after the solid shapes.
    """
    z = [(42, 36), (80, 36), (80, 46), (55, 74), (80, 74), (80, 84), (42, 84), (42, 74), (67, 46), (42, 46)]
    i1 = [(90, 36), (101, 36), (101, 84), (90, 84)]
    d_outer = [(111, 36), (131, 36)]
    d_outer += _cubic((131, 36), (144, 36), (151, 46), (151, 60))
    d_outer += _cubic((151, 60), (151, 74), (144, 84), (131, 84))
    d_outer += [(111, 84)]
    d_inner = [(122, 46), (122, 74), (130, 74)]
    d_inner += _cubic((130, 74), (136, 74), (140, 69), (140, 60))
    d_inner += _cubic((140, 60), (140, 51), (136, 46), (130, 46))
    i2 = [(161, 36), (172, 36), (172, 84), (161, 84)]
    shift = lambda pts: [(x + LETTERS_DX, y) for x, y in pts]  # noqa: E731
    return [(shift(z), False), (shift(i1), False), (shift(d_outer), False), (shift(i2), False),
            (shift(d_inner), True)]


# The favicon (zidicarhire-favicon.svg, 64 x 64): yellow tile with a single Z.
FAVICON = {
    'tile': {'x': 3, 'y': 3, 'w': 58, 'h': 58, 'r': 10, 'stroke': 4},
    'inner': {'x': 9.5, 'y': 9.5, 'w': 45, 'h': 45, 'r': 5, 'stroke': 1.5},
    'z': [(17, 17), (47, 17), (47, 25), (27, 40), (47, 40), (47, 47), (17, 47), (17, 39), (37, 25), (17, 25)],
}
