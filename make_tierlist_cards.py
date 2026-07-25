"""Render the tier-list cards (HTML+CSS) to PNGs with headless Chrome.

    python make_tierlist_cards.py            # all 10
    python make_tierlist_cards.py 4K         # only variants matching "4K"

Heights are measured, not hardcoded: each card is first rendered tall at 1x and the
last non-background row is found, then re-rendered at that exact height at 2x. Edit
the copy and the canvas still fits with no dead space and no clipping.

Why two variants per card. Discord's inline preview box is roughly 550x400, so a tall
portrait image is *height*-limited and shown ~290px wide, which makes 13px body text
about 4px on screen. The compact cards stay under 0.727 aspect (= 400/550) so they are
*width*-limited instead and display at the full ~550px, and their type is a larger
share of a narrower canvas — together roughly 2.2x more legible in the preview. The
detail cards carry the prose and are meant to be clicked.

Needs Chrome (or Edge) and Pillow.
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# public/ is copied verbatim into dist/ by Vite, so writing here means the deploy
# workflow publishes the cards at https://msfs.razortek.nl/cards/<name>.png with no
# extra build step — handy for linking or embedding them instead of re-uploading.
OUT_DIR = os.path.join(HERE, 'public', 'cards')
SCALE = 2          # device pixel ratio of the final PNGs
PROBE_H = 1800     # tall enough that no card is clipped while measuring

# (output png, source html, query string, css width)
CARDS = [
    ('msfs24_cpu_tierlist.png',                'tierlist_card_cpu.html', '',                    1000),
    ('msfs24_cpu_tierlist_compact.png',        'tierlist_card_cpu.html', '?compact',             860),
    ('msfs24_gpu_tierlist_1080p.png',          'tierlist_card_gpu.html', '?res=1080p',          1000),
    ('msfs24_gpu_tierlist_1080p_compact.png',  'tierlist_card_gpu.html', '?res=1080p&compact',   900),
    ('msfs24_gpu_tierlist.png',                'tierlist_card_gpu.html', '?res=1440p',          1000),
    ('msfs24_gpu_tierlist_compact.png',        'tierlist_card_gpu.html', '?res=1440p&compact',   900),
    ('msfs24_gpu_tierlist_4k.png',             'tierlist_card_gpu.html', '?res=4K',             1000),
    ('msfs24_gpu_tierlist_4k_compact.png',     'tierlist_card_gpu.html', '?res=4K&compact',      900),
    ('msfs24_spec_table.png',                  'tierlist_card_spec.html', '',                   1080),
]

CHROMES = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    '/usr/bin/google-chrome', '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
]


def find_chrome():
    for c in CHROMES:
        if os.path.exists(c):
            return c
    sys.exit('no Chrome/Edge found - add its path to CHROMES')


def shoot(chrome, html, query, out, width, height, scale):
    url = 'file:///' + os.path.join(HERE, html).replace('\\', '/') + query
    subprocess.run([
        chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars',
        '--force-device-scale-factor=%d' % scale,
        '--window-size=%d,%d' % (width, height),
        '--screenshot=' + out, url,
    ], check=True, capture_output=True)


def content_height(png, width):
    """Last row that isn't the pure-black page background = the card's real height."""
    from PIL import Image
    im = Image.open(png).convert('RGB')
    w, h = im.size
    for y in range(h - 1, -1, -1):
        if im.getpixel((w // 2, y)) != (0, 0, 0) or im.getpixel((20, y)) != (0, 0, 0):
            return y
    return h


def main():
    chrome = find_chrome()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = os.path.join(HERE, '.probe.png')
    for out, html, query, width in CARDS:
        if only and only.lower() not in out.lower():
            continue
        shoot(chrome, html, query, tmp, width, PROBE_H, 1)
        height = content_height(tmp, width)
        dest = os.path.join(OUT_DIR, out)
        shoot(chrome, html, query, dest, width, height, SCALE)
        kb = os.path.getsize(dest) // 1024
        aspect = height / width
        warn = '  <-- over 0.727, Discord will shrink it' if 'compact' in out and aspect > 0.727 else ''
        print('%-38s %4dx%-4d css  %5dx%-5d png  %4d KB  aspect %.3f%s'
              % (out, width, height, width * SCALE, height * SCALE, kb, aspect, warn))
    if os.path.exists(tmp):
        os.remove(tmp)


if __name__ == '__main__':
    main()
