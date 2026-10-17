"""
Builds static/vendor/: Bootstrap, Bootstrap Icons and the two web fonts, served from our own domain instead of
three outside servers (one connection instead of four on a first visit). The icon font is cut down to the icons the
site uses and the fonts to Latin characters, which saves about 200 KB on a first visit.

Run it again after using a new icon anywhere (a "bi-..." class) or changing a version below:

    pip install fonttools brotli
    python tools/build_vendor.py

The outputs are committed, so the server needs nothing extra.
"""
import io
import re
import sys
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'static' / 'vendor'
BOOTSTRAP = '5.3.3'
ICONS = '1.11.3'
NPM = 'https://cdn.jsdelivr.net/npm'
# Same families, weights and widths the site used from Google Fonts.
FONTS_CSS = 'https://fonts.googleapis.com/css2?family=Inter:wght@400..700&family=Archivo:wdth,wght@62..75,700..800&display=swap'
MODERN_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
# Plates only use these widths and weights (theme.css --wdth-narrow and 75%, weights 700-800): drop the rest.
ARCHIVO_AXES = {'wdth': (70, 75), 'wght': (700, 800)}
# Where icon names can appear.
SOURCES = ['templates/**/*.html', 'static/js/**/*.js', '*/**/*.py']
# Latin, Latin-1, typographic punctuation, euro, arrows and minus: everything the site's text uses.
UNICODES = 'U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DC,U+2013-2014,U+2018-201E,U+2022,U+2026,U+2039-203A,U+20AC,U+2122,U+2190-2193,U+2212'


def fetch(url, ua=None):
    req = urllib.request.Request(url, headers={'User-Agent': ua or 'zidicarhire-build'})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read()


def used_icons():
    names = set()
    for pattern in SOURCES:
        for path in ROOT.glob(pattern):
            if 'node_modules' in path.parts or 'vendor' in path.parts or path.parts[len(ROOT.parts)] in ('mobile', 'desktop'):
                continue
            names.update(re.findall(r'\bbi-([a-z0-9]+(?:-[a-z0-9]+)*)', path.read_text(encoding='utf-8', errors='ignore')))
    return names


def build_icons():
    css = fetch(f'{NPM}/bootstrap-icons@{ICONS}/font/bootstrap-icons.css').decode()
    codepoints = dict(re.findall(r'\.bi-([a-z0-9-]+)::before \{ content: "\\([0-9a-f]+)"; \}', css))
    names = sorted(n for n in used_icons() if n in codepoints)
    missing = sorted(n for n in used_icons() if n not in codepoints and n not in ('theme',))
    font = TTFont(io.BytesIO(fetch(f'{NPM}/bootstrap-icons@{ICONS}/font/fonts/bootstrap-icons.woff2')))
    opts = subset.Options()
    opts.flavor = 'woff2'
    opts.layout_features = []
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=[int(codepoints[n], 16) for n in names])
    sub.subset(font)
    font.flavor = 'woff2'
    font.save(OUT / 'bootstrap-icons.woff2')
    rules = '\n'.join(f'.bi-{n}::before {{ content: "\\{codepoints[n]}"; }}' for n in names)
    (OUT / 'bootstrap-icons.css').write_text(
        f'/* Bootstrap Icons {ICONS} (MIT), only the {len(names)} icons this site uses. Built by tools/build_vendor.py. */\n'
        '@font-face { font-display: block; font-family: "bootstrap-icons"; src: url("bootstrap-icons.woff2") format("woff2"); }\n'
        '.bi::before, [class^="bi-"]::before, [class*=" bi-"]::before { display: inline-block; font-family: bootstrap-icons !important;'
        ' font-style: normal; font-weight: normal !important; font-variant: normal; text-transform: none; line-height: 1;'
        ' vertical-align: -.125em; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }\n'
        + rules + '\n', encoding='utf-8')
    return names, missing


def build_fonts():
    css = fetch(FONTS_CSS, MODERN_UA).decode()
    faces = re.findall(r'/\* ([a-z-]+) \*/\s*(@font-face \{.*?\})', css, re.S)
    out = []
    for script, face in faces:
        if script != 'latin':
            continue
        family = re.search(r"font-family: '([^']+)'", face).group(1)
        url = re.search(r'url\((https://[^)]+\.woff2)\)', face).group(1)
        font = TTFont(io.BytesIO(fetch(url, MODERN_UA)))
        if family == 'Archivo':
            font = instancer.instantiateVariableFont(font, ARCHIVO_AXES)
            face = re.sub(r'font-stretch: [^;]+;', 'font-stretch: 70% 75%;', face)
            face = re.sub(r'font-weight: [^;]+;', 'font-weight: 700 800;', face)
        opts = subset.Options()
        opts.flavor = 'woff2'
        opts.layout_features = ['kern', 'liga', 'calt', 'tnum', 'case']
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=subset.parse_unicodes(UNICODES))
        sub.subset(font)
        font.flavor = 'woff2'
        name = f'{family.lower()}.woff2'
        font.save(OUT / name)
        face = re.sub(r'url\([^)]+\)', f'url("{name}")', face)
        face = re.sub(r'unicode-range: [^;]+;', f'unicode-range: {UNICODES};', face)
        out.append(face)
    (OUT / 'fonts.css').write_text('/* Inter and Archivo (SIL Open Font License), Latin only. Built by tools/build_vendor.py. */\n'
                                    + '\n'.join(out) + '\n', encoding='utf-8')
    return [f.split("font-family: '")[1].split("'")[0] for f in out]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'bootstrap.min.css').write_bytes(fetch(f'{NPM}/bootstrap@{BOOTSTRAP}/dist/css/bootstrap.min.css'))
    (OUT / 'bootstrap.bundle.min.js').write_bytes(fetch(f'{NPM}/bootstrap@{BOOTSTRAP}/dist/js/bootstrap.bundle.min.js'))
    for f in (OUT / 'bootstrap.min.css', OUT / 'bootstrap.bundle.min.js'):   # source maps are not shipped
        f.write_bytes(re.sub(rb'\n?/\*# sourceMappingURL=[^*]+\*/\s*$|\n?//# sourceMappingURL=\S+\s*$', b'', f.read_bytes()))
    names, missing = build_icons()
    fonts = build_fonts()
    print(f'icons: {len(names)} kept', f'(unknown names ignored: {", ".join(missing)})' if missing else '')
    print('fonts:', ', '.join(fonts))
    for f in sorted(OUT.iterdir()):
        print(f'  {f.name:28} {f.stat().st_size / 1024:6.1f} KB')


if __name__ == '__main__':
    sys.exit(main())
