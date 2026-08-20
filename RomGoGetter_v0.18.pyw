# RomGoGetter v0.17
# Copyright (c) 2026 Shoko
# MIT License — see LICENSE file for details
# https://github.com/shokoe/RomGoGetter
#
# 1G1R ROM downloader and curator for archive.org, lolroms.com and compatible sources.

import sys
import os
import hashlib
import html
import json
import re
import shutil
import threading
import time
import tkinter as tk
import xml.etree.ElementTree as ET
from tkinter import ttk, messagebox, filedialog, simpledialog
import urllib.request
import urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, quote

if sys.platform == 'win32':
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

import socket
socket.setdefaulttimeout(30)

FIRST_PAREN_PATTERN = re.compile(r'^\s*[^(]*\(([^)]+)\)')
REST_PAREN_PATTERN  = re.compile(r'\(([^)]+)\)')
LANG_PATTERN        = re.compile(r'^[A-Z][a-z]([,+][A-Z][a-z])*$')
REV_PATTERN         = re.compile(r'\([Rr]ev ?([^)]*)\)')

DISC_PATTERN        = re.compile(r'\(Dis[ck]\s*\d+\)', re.IGNORECASE)
SIZE_PATTERN        = re.compile(r'([\d.]+)\s*(K|M|G)', re.IGNORECASE)
TITLE_PATTERN       = re.compile(r'Files for\s+(.+)', re.IGNORECASE)
WESTERN = {
    'USA', 'US', 'U', 'Europe', 'EUR', 'E', 'Australia', 'AUS',
    'Canada', 'CAN', 'UK', 'France', 'FRA', 'Germany', 'GER',
    'Spain', 'SPA', 'Italy', 'ITA', 'Netherlands', 'HOL',
    'Sweden', 'SWE', 'Brazil', 'BRA',
}
ENGLISH_COUNTRIES = {
    'USA', 'US', 'U', 'UK', 'Europe', 'EUR', 'E',
    'Australia', 'AUS', 'Canada', 'CAN',
    'New Zealand', 'NZ', 'Ireland', 'IRE',
}
EXCLUDE_ATTRIBUTES  = {'Demo', 'Cheat', 'Kiosk', 'Beta', 'Alpha', 'Proto', 'Prototype', 'Sample', 'Update'}
EXCLUDE_TITLE_WORDS = {'Magazine', 'Demo Disk', 'Demo Disc', 'Bonus Disk', 'Bonus Disc',
                       'Covermount', 'OXM', 'Tips', 'Tricks'}
NON_GAME_EXTS = {
    '.xml', '.json', '.txt', '.nfo', '.dat', '.csv', '.html', '.htm',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tga', '.svg',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.sqlite', '.db', '.ini', '.cfg', '.log',
    '.torrent', '.nzb',
    '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.flac', '.ogg', '.wav', '.m4a',
    '.tmp', '.bak', '.lnk', '.url', '.exe', '.dll', '.so',
}
CHUNK_SIZE    = 1024 * 1024
MAX_PARALLEL  = 3
MAX_RETRIES   = 3
STUCK_TIMEOUT = 60

APP_NAME      = 'RomGoGetter'
APP_VER       = 'v0.17'
SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    f'{APP_NAME}_settings.json'
)
GROUPS_FILE     = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    f'{APP_NAME}_groups.json'
)
DAT_GROUPS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    f'{APP_NAME}_dat_groups.json'
)

BG      = '#1e1e1e'
BG2     = '#2d2d2d'
BG3     = '#383838'
FG      = '#ffffff'
FG2     = '#aaaaaa'
ACC     = '#0078d4'
GREEN   = '#4caf50'
RED     = '#ff6b6b'
YELLOW  = '#ffc107'
PURPLE  = '#b070f0'

# Font definitions — populated after Tk root is created via _init_fonts()
FONT    = None
FONT_SM = None
FONT_LG = None
FONT_XL = None
_BASE_FONT_SIZE = 10

def _init_fonts(base_size=10):
    """Create or update named tkinter fonts. Call after Tk() is instantiated."""
    import tkinter.font as tkfont
    global FONT, FONT_SM, FONT_LG, FONT_XL, _BASE_FONT_SIZE
    _BASE_FONT_SIZE = base_size
    if FONT is None:
        FONT    = tkfont.Font(name='AppFont',   family='Consolas', size=base_size)
        FONT_SM = tkfont.Font(name='AppFontSm', family='Consolas', size=base_size - 1)
        FONT_LG = tkfont.Font(name='AppFontLg', family='Consolas', size=base_size + 2, weight='bold')
        FONT_XL = tkfont.Font(name='AppFontXl', family='Consolas', size=base_size + 4, weight='bold')
    else:
        FONT.configure(size=base_size)
        FONT_SM.configure(size=base_size - 1)
        FONT_LG.configure(size=base_size + 2)
        FONT_XL.configure(size=base_size + 4)


# ── Settings ──────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


def load_groups() -> dict:
    try:
        if os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_groups(groups: dict):
    try:
        with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(groups, f, indent=2)
    except Exception:
        pass


def load_dat_groups() -> dict:
    try:
        if os.path.exists(DAT_GROUPS_FILE):
            with open(DAT_GROUPS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_dat_groups(groups: dict):
    try:
        with open(DAT_GROUPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(groups, f, indent=2)
    except Exception:
        pass


# ── Formatting ────────────────────────────────────────────────────────────────

def parse_size_bytes(size_str: str) -> int:
    if not size_str:
        return 0
    try:
        return int(size_str.strip())
    except ValueError:
        pass
    m = SIZE_PATTERN.search(size_str)
    if not m:
        return 0
    value, unit = float(m.group(1)), m.group(2).upper()
    return int(value * {'K': 1024, 'M': 1024**2, 'G': 1024**3}[unit])


def format_size(total_bytes: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if total_bytes < 1024:
            return f"{total_bytes:.1f} {unit}"
        total_bytes /= 1024
    return f"{total_bytes:.1f} PB"


def format_eta(seconds: float) -> str:
    if seconds < 0 or seconds == float('inf'):
        return '--:--'
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s   = divmod(rem, 60)
    if h: return f"{h}h{m:02d}m{s:02d}s"
    if m: return f"{m}m{s:02d}s"
    return f"{s}s"


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s   = divmod(rem, 60)
    if h: return f"{h}h{m:02d}m{s:02d}s"
    if m: return f"{m}m{s:02d}s"
    return f"{s}s"


# ── ROM parsing ───────────────────────────────────────────────────────────────

def parse_rom_filename(filename: str) -> dict:
    name        = os.path.splitext(filename)[0]
    base_title  = name.split('(')[0].strip()
    # Include disc number in title so each disc is its own 1G1R group
    disc_match  = DISC_PATTERN.search(name)
    if disc_match:
        base_title = f"{base_title} {disc_match.group(0)}"
    first_match = FIRST_PAREN_PATTERN.match(name)
    if not first_match:
        return {'title': base_title, 'filename': filename,
                'countries': set(), 'languages': set(), 'attributes': set()}

    first_content = first_match.group(1).strip()
    countries     = set()
    attributes    = set()
    languages     = set()

    # If first paren looks like a hex title ID (e.g. Wii U: 101B3E00), treat as attribute
    # and scan all remaining parens for countries/languages
    if re.match(r'^[0-9A-Fa-f]{6,10}$', first_content):
        attributes.add(first_content)
        scan_start = 0  # scan all parens
    else:
        countries  = {c.strip() for c in first_content.split(',')}
        scan_start = first_match.end()

    rest_of_name = name[scan_start:]
    for token in REST_PAREN_PATTERN.findall(rest_of_name):
        token = token.strip()
        if not countries and re.match(r'^[A-Z][a-zA-Z ,]+$', token) and token not in languages:
            # Could be a country — check against known sets
            parts = {c.strip() for c in token.split(',')}
            if parts & (WESTERN | {'Japan', 'Korea', 'China', 'Taiwan', 'Brazil', 'Russia'}):
                countries = parts
                continue
        if LANG_PATTERN.match(token):
            languages.update(re.split(r'[,+]', token))
        elif not DISC_PATTERN.match(f'({token})'):
            attributes.add(token)
    return {'title': base_title, 'filename': filename,
            'countries': countries, 'languages': languages, 'attributes': attributes}


def is_non_english(instances: list) -> bool:
    return all(
        'En' not in i['languages'] and not i['countries'] & WESTERN
        for i in instances
    )


_FAN_TRANS_EN_PATTERN = re.compile(
    r'\bT-(?:English|En|Eng)\b', re.IGNORECASE)
_FAN_TRANS_ANY_PATTERN = re.compile(
    r'\bT-(?:English|En|Eng|French|Fr|German|De|Spanish|Es|Italian|It|Portuguese|Pt|'
    r'Dutch|Nl|Russian|Ru|Polish|Pl|Korean|Kr|Chinese|Zh|Japanese|Ja)\b',
    re.IGNORECASE)

def is_fan_translation(instance: dict) -> bool:
    """Return True if this is any fan translation."""
    return any(_FAN_TRANS_ANY_PATTERN.match(a) for a in instance['attributes'])

def is_english_fan_translation(instance: dict) -> bool:
    """Return True if this is an English fan translation (T-English, T-En, T-Eng)."""
    return any(_FAN_TRANS_EN_PATTERN.match(a) for a in instance['attributes'])

def is_excluded(instance: dict) -> bool:
    for attr in instance['attributes']:
        # Match exact or prefixed: 'Demo', 'Demo 1', 'Kiosk Demo', etc.
        for excl in EXCLUDE_ATTRIBUTES:
            if attr == excl or attr.startswith(excl + ' ') or attr.startswith(excl + ','):
                return True
    title = instance.get('filename', '')
    return any(w.lower() in title.lower() for w in EXCLUDE_TITLE_WORDS)


def _ver_date_key(filename: str) -> tuple:
    """Extract (version_tuple, date_tuple) from parenthesised tokens for numeric comparison.
    version: highest dotted numeric e.g. (2.01.00) or comma-sep (1.04.00, 2.01.00) → max component
    date:    YYYY-MM-DD in parens, or bare 4-digit year if no dotted version present
    """
    ver, date = (), ()
    for m in re.finditer(r'\(([^)]+)\)', filename):
        token = m.group(1).strip()
        # Date: YYYY-MM-DD
        dm = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', token)
        if dm:
            d = tuple(int(x) for x in dm.groups())
            if d > date:
                date = d
            continue
        # Version: dotted numeric, possibly comma-separated — take max
        for part in token.split(','):
            vm = re.match(r'^(\d+(?:\.\d+)+)', part.strip())
            if vm:
                try:
                    t = tuple(int(x) for x in vm.group(1).split('.'))
                    if t > ver:
                        ver = t
                except ValueError:
                    pass
    # Year-only fallback (e.g. (2011)) only when no dotted version found
    if not ver:
        for m in re.finditer(r'\((\d{4})\)', filename):
            yr = int(m.group(1))
            if 1970 <= yr <= 2100:
                t = (yr,)
                if t > ver:
                    ver = t
    return ver, date


def rev_key(instance: dict) -> tuple:
    """Sort key: Rev > version > date > native English country > language count.
    Higher is better. Numeric revs sort numerically (11 > 7), alpha lexicographically.
    """
    fname      = instance.get('filename', '')
    m          = REV_PATTERN.search(fname)
    native_en  = 1 if instance['countries'] & ENGLISH_COUNTRIES else 0
    lang_count = len(instance['languages'])
    ver, date  = _ver_date_key(fname)
    if m:
        rev_str = m.group(1).strip()
        try:
            return (1, int(rev_str), 0, ver, date, native_en, lang_count)
        except ValueError:
            return (1, 0, rev_str, ver, date, native_en, lang_count)
    return (0, 0, '', ver, date, native_en, lang_count)


def select_best(instances: list) -> dict | None:
    non_excl = [i for i in instances if not is_excluded(i)]
    # Fan translations count as English — prefer them over untranslated JP/etc.
    english = [i for i in non_excl if 'En' in i['languages'] or is_english_fan_translation(i)]
    if english:
        best = max(english, key=rev_key)
    else:
        western = [i for i in non_excl if i['countries'] & WESTERN]
        if western:
            best = max(western, key=rev_key)
        else:
            if non_excl:
                best = max(non_excl, key=rev_key)
            else:
                return None
    return {'filename': best['filename'], 'size': best['size']}


# ── DAT parsing ───────────────────────────────────────────────────────────────

def parse_dat_file(path: str) -> tuple[list, str | None]:
    """Parse a No-Intro / Redump style DAT file.
    Returns ([(filename, size_str), ...], header_name | None).
    Every <rom> entry is included as-is — no filtering applied.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise ValueError(f"Invalid DAT XML: {e}")

    root     = tree.getroot()
    header   = root.find('header')
    dat_name = None
    if header is not None:
        name_el  = header.find('name')
        dat_name = name_el.text.strip() if name_el is not None and name_el.text else None

    results = []
    for game in root.iter('game'):
        for rom in game.iter('rom'):
            fname = rom.get('name', '').strip()
            size  = rom.get('size', '').strip()
            if fname:
                results.append((fname, size))
    return results, dat_name


def parse_size_bytes_dat(size_str: str) -> int:
    """DAT <rom size="..."> is always a raw byte count as an integer string."""
    try:
        return int(size_str)
    except (ValueError, TypeError):
        return parse_size_bytes(size_str)


# ── Network ───────────────────────────────────────────────────────────────────

def make_headers(access: str = None, secret: str = None) -> dict:
    h = {'User-Agent': 'Mozilla/5.0'}
    if access and secret:
        h['Authorization'] = f'LOW {access}:{secret}'
    return h


def fetch_page(url: str, access: str = None, secret: str = None) -> str:
    req = urllib.request.Request(url, headers=make_headers(access, secret))
    with urllib.request.urlopen(req) as r:
        return r.read().decode('utf-8', errors='replace')


def extract_page_title(html_content: str) -> str | None:
    m = TITLE_PATTERN.search(html_content)
    if not m:
        return None
    title = m.group(1).strip()
    # Strip any HTML tags that may have been captured
    title = re.sub(r'<[^>]+>', '', title).strip()
    return title or None


def is_view_archive_url(url: str) -> bool:
    """Detect archive.org view_archive.php ZIP viewer URLs."""
    return 'view_archive.php' in url and 'archive=' in url


def fetch_archive_filenames(url: str, access: str = None, secret: str = None) -> tuple[list, str | None]:
    html_content = fetch_page(url, access, secret)
    page_title   = extract_page_title(html_content)
    table_match  = re.search(
        r'<table\s+class="directory-listing-table">(.*?)</table>',
        html_content, re.DOTALL | re.IGNORECASE
    )
    if not table_match:
        return [], page_title
    results = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table_match.group(1), re.DOTALL | re.IGNORECASE):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        if not cells:
            continue
        first_cell = cells[0]
        size_str   = re.sub(r'<[^>]+>', '', cells[2]).strip() if len(cells) > 2 else ''
        href_match = re.search(r'<a\s+href=["\']([^"\']+)["\']', first_cell, re.IGNORECASE)
        if href_match:
            href = href_match.group(1)
            if href.startswith('/'):
                fname = html.unescape(unquote(href.split('/')[-1]))
                direct_url = 'https://archive.org' + href
            else:
                fname = html.unescape(unquote(href))
                direct_url = url.rstrip('/') + '/' + quote(fname, safe='')
            if fname and '.' in fname and fname != '../':
                results.append((fname, size_str, direct_url))
        else:
            # Fallback: extract text — no direct_url available
            text = html.unescape(re.sub(r'<[^>]+>', '', first_cell).strip())
            if text and '.' in text and text != 'Name':
                results.append((text, size_str, url.rstrip('/') + '/' + quote(text, safe='')))
    return results, page_title


def is_lolroms_url(url: str) -> bool:
    u = url.split('#')[0].lower()
    return 'lolroms.com' in u or ('web.archive.org' in u and 'lolroms.com' in u)


def is_minerva_url(url: str) -> bool:
    u = url.strip()
    if 'minerva-archive.org' in u.lower():
        return True
    # Local HTML file saved from Minerva browse page
    if os.path.isfile(u) and u.lower().endswith(('.htm', '.html')):
        return True
    return False


# ── Bencode parser (pure Python, no deps) ─────────────────────────────────────

def bdecode(data: bytes, idx: int = 0):
    """Decode bencoded data. Returns (value, next_index)."""
    if data[idx:idx+1] == b'd':
        idx += 1
        d = {}
        while data[idx:idx+1] != b'e':
            k, idx = bdecode(data, idx)
            v, idx = bdecode(data, idx)
            d[k] = v
        return d, idx + 1
    elif data[idx:idx+1] == b'l':
        idx += 1
        lst = []
        while data[idx:idx+1] != b'e':
            v, idx = bdecode(data, idx)
            lst.append(v)
        return lst, idx + 1
    elif data[idx:idx+1] == b'i':
        end = data.index(b'e', idx)
        return int(data[idx+1:end]), end + 1
    else:
        colon = data.index(b':', idx)
        n = int(data[idx:colon])
        start = colon + 1
        return data[start:start+n], start + n

def bencode(val) -> bytes:
    """Encode value to bencode bytes."""
    if isinstance(val, dict):
        items = sorted(val.items(), key=lambda x: x[0] if isinstance(x[0], bytes) else x[0].encode())
        return b'd' + b''.join(bencode(k) + bencode(v) for k, v in items) + b'e'
    elif isinstance(val, list):
        return b'l' + b''.join(bencode(v) for v in val) + b'e'
    elif isinstance(val, int):
        return b'i' + str(val).encode() + b'e'
    elif isinstance(val, bytes):
        return str(len(val)).encode() + b':' + val
    elif isinstance(val, str):
        enc = val.encode('utf-8')
        return str(len(enc)).encode() + b':' + enc
    raise TypeError(f"Cannot bencode {type(val)}")


# ── Minerva URL/torrent helpers ───────────────────────────────────────────────

MINERVA_VER_RE = re.compile(r'v[\d.]+', re.IGNORECASE)

RA_SYSTEMS = [
    ('Nintendo',  [
        ('NES/Famicom',                    '7-nes-famicom'),
        ('Famicom Disk System',            '81-famicom-disk-system'),
        ('SNES/Super Famicom',             '3-snes-super-famicom'),
        ('Nintendo 64',                    '2-nintendo-64'),
        ('GameCube',                       '16-gamecube'),
        ('Wii',                            '19-wii'),
        ('Game Boy',                       '4-game-boy'),
        ('Game Boy Color',                 '6-game-boy-color'),
        ('Game Boy Advance',               '5-game-boy-advance'),
        ('Nintendo DS',                    '18-nintendo-ds'),
        ('Nintendo DSi',                   '78-nintendo-dsi'),
        ('Pokemon Mini',                   '24-pokemon-mini'),
        ('Virtual Boy',                    '28-virtual-boy'),
    ]),
    ('Sony', [
        ('PlayStation',                    '12-playstation'),
        ('PlayStation 2',                  '21-playstation-2'),
        ('PlayStation Portable',           '41-playstation-portable'),
    ]),
    ('Atari', [
        ('Atari 2600',                     '25-atari-2600'),
        ('Atari 7800',                     '51-atari-7800'),
        ('Atari Jaguar',                   '17-atari-jaguar'),
        ('Atari Jaguar CD',                '77-atari-jaguar-cd'),
        ('Atari Lynx',                     '13-atari-lynx'),
    ]),
    ('Sega', [
        ('SG-1000',                        '33-sg-1000'),
        ('Master System',                  '11-master-system'),
        ('Genesis/Mega Drive',             '1-genesis-mega-drive'),
        ('Sega CD',                        '9-sega-cd'),
        ('32X',                            '10-32x'),
        ('Saturn',                         '39-saturn'),
        ('Dreamcast',                      '40-dreamcast'),
        ('Game Gear',                      '15-game-gear'),
    ]),
    ('NEC', [
        ('PC Engine/TurboGrafx-16',        '8-pc-engine-turbografx-16'),
        ('PC Engine CD/TurboGrafx-CD',     '76-pc-engine-cd-turbografx-cd'),
        ('PC-8000/8800',                   '47-pc-8000-8800'),
        ('PC-FX',                          '49-pc-fx'),
    ]),
    ('SNK', [
        ('Neo Geo CD',                     '56-neo-geo-cd'),
        ('Neo Geo Pocket',                 '14-neo-geo-pocket'),
    ]),
    ('Others', [
        ('3DO Interactive Multiplayer',    '43-3do-interactive-multiplayer'),
        ('Amstrad CPC',                    '37-amstrad-cpc'),
        ('Apple II',                       '38-apple-ii'),
        ('Arcade',                         '27-arcade'),
        ('Arcadia 2001',                   '73-arcadia-2001'),
        ('Arduboy',                        '71-arduboy'),
        ('ColecoVision',                   '44-colecovision'),
        ('Elektor TV Games Computer',      '75-elektor-tv-games-computer'),
        ('Fairchild Channel F',            '57-fairchild-channel-f'),
        ('Intellivision',                  '45-intellivision'),
        ('Interton VC 4000',               '74-interton-vc-4000'),
        ('Magnavox Odyssey 2',             '23-magnavox-odyssey-2'),
        ('Mega Duck',                      '69-mega-duck'),
        ('MSX',                            '29-msx'),
        ('Standalone',                     '102-standalone'),
        ('Uzebox',                         '80-uzebox'),
        ('Vectrex',                        '46-vectrex'),
        ('WASM-4',                         '72-wasm-4'),
        ('Watara Supervision',             '63-watara-supervision'),
        ('WonderSwan',                     '53-wonderswan'),
    ]),
]
# Flat list for combo: console name -> slug (exact sheet name)
RA_SYSTEM_MAP = {}
RA_SYSTEM_DISPLAY = []
for manufacturer, systems in RA_SYSTEMS:
    for name, slug in systems:
        RA_SYSTEM_MAP[name] = slug
        RA_SYSTEM_DISPLAY.append(name)
RA_SYSTEM_DISPLAY.sort()



def minerva_torrent_url(browse_url: str) -> str | None:
    """Convert a Minerva browse URL or local HTML file to its torrent download URL."""
    browse_url = browse_url.strip()
    base = 'https://minerva-archive.org/assets/'

    # Local HTML file — extract collection name from <title>
    if os.path.isfile(browse_url):
        try:
            with open(browse_url, 'r', encoding='utf-8', errors='replace') as f:
                html = f.read()
            m = re.search(r'<title>[^|]+\|\s*(.+?)\s*</title>', html, re.IGNORECASE)
            if m:
                collection_name = m.group(1).strip().replace(' / ', ' - ')
            else:
                collection_name = os.path.splitext(os.path.basename(browse_url))[0]
        except Exception:
            return None
        torrent_name     = f'Minerva_Myrient - {collection_name}.torrent'
        torrent_name_enc = urllib.parse.quote(torrent_name)
        return f'{base}Minerva_Myrient_v0.3/{torrent_name_enc}'

    # Remote browse URL
    m = re.search(r'/browse/(.+?)/?$', browse_url.rstrip('/'))
    if not m:
        return None
    collection_name  = urllib.parse.unquote(m.group(1)).replace('/', ' - ').strip()
    torrent_name     = f'Minerva_Myrient - {collection_name}.torrent'
    torrent_name_enc = urllib.parse.quote(torrent_name)
    try:
        req = urllib.request.Request(base, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode('utf-8', errors='replace')
        versions = MINERVA_VER_RE.findall(html)
        ver = max(versions, key=lambda v: [int(x) for x in v[1:].split('.')]) if versions else 'v0.3'
    except Exception:
        ver = 'v0.3'
    return f'{base}Minerva_Myrient_{ver}/{torrent_name_enc}'

MINERVA_HEADERS = {
    'User-Agent':                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Accept':                    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language':           'en-US,en;q=0.5',
    'Accept-Encoding':           'gzip, deflate, br',
    'Connection':                'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest':            'document',
    'Sec-Fetch-Mode':            'navigate',
    'Sec-Fetch-Site':            'none',
    'Sec-Fetch-User':            '?1',
}

def fetch_minerva_filenames(url: str) -> tuple[list, str | None]:
    """Fetch file listing from a Minerva browse URL or local HTML file."""
    if os.path.isfile(url.strip()):
        with open(url.strip(), 'r', encoding='utf-8', errors='replace') as f:
            html = f.read()
        page_title = os.path.splitext(os.path.basename(url.strip()))[0]
    else:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode('utf-8', errors='replace')
        m = re.search(r'/browse/[^/]+/([^/]+)/?$', url.rstrip('/'))
        page_title = urllib.parse.unquote(m.group(1)) if m else None
    # Extract filename from anchor text and full path from href for torrent matching.
    # href is like /rom?name=./Collection/filename.ext — anchor text is display name without extension.
    # We store (filename_with_ext, size, torrent_path) where torrent_path is the
    # relative path inside the torrent (e.g. "Collection/filename.ext").
    results = []
    for entry in re.finditer(
            r'data-name="[^"]*".*?<a href="([^"]*?)"[^>]*>([^<]+)</a>\s*<span>([^<]+)</span>',
            html, re.DOTALL):
        href      = entry.group(1)
        disp_name = html_unescape(entry.group(2).strip())
        size_str  = entry.group(3).strip()
        # Extract path from ?name=./path/to/file.ext
        m = re.search(r'[?&]name=\.?/?(.*)', href)
        if m:
            rel_path = html_unescape(unquote(m.group(1)))  # e.g. "Collection/filename.ext"
            fname    = os.path.basename(rel_path)
        else:
            # Fallback: use display name (no extension known)
            fname    = disp_name
            rel_path = disp_name
        if fname:
            results.append((fname, size_str, rel_path))
    return results, page_title

def html_unescape(s: str) -> str:
    return s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")

def parse_torrent_files(torrent_data: bytes) -> tuple[dict, list]:
    """Parse a v1 torrent. Returns (torrent_dict, [(filename, length), ...])."""
    t, _ = bdecode(torrent_data)
    info = t.get(b'info', {})
    files = []
    if b'files' in info:
        for f in info[b'files']:
            path_parts = f[b'path']
            fname = '/'.join(p.decode('utf-8', errors='replace') for p in path_parts)
            length = f.get(b'length', 0)
            # Skip BEP47 pad files
            if fname.startswith('.pad/') or '/.pad/' in fname:
                continue
            files.append((fname, length))
    else:
        # Single-file torrent
        name = info.get(b'name', b'').decode('utf-8', errors='replace')
        length = info.get(b'length', 0)
        files.append((name, length))
    return t, files

def make_subset_torrent(torrent_data: bytes, selected_filenames: set) -> bytes:
    """Create a subset torrent keeping only selected files with correct piece hashes."""
    t, _ = bdecode(torrent_data)
    info = t.get(b'info', {})
    if b'files' not in info:
        return torrent_data  # single file, nothing to subset

    piece_length = info.get(b'piece length', 0)
    pieces       = info.get(b'pieces', b'')  # 20 bytes per piece
    all_files    = info[b'files']

    # Calculate byte offset of each file in the torrent
    offset = 0
    file_ranges = []  # (start_byte, end_byte, file_dict)
    for f in all_files:
        length = f.get(b'length', 0)
        file_ranges.append((offset, offset + length, f))
        offset += length

    # Determine which files to keep
    kept = []
    for start, end, f in file_ranges:
        path_parts = f[b'path']
        fname = '/'.join(p.decode('utf-8', errors='replace') for p in path_parts)
        if fname.startswith('.pad/') or '/.pad/' in fname:
            continue
        if fname in selected_filenames or os.path.basename(fname) in selected_filenames:
            kept.append((start, end, f))

    if not kept:
        return torrent_data

    # Find piece range covering kept files
    # First byte of first kept file, last byte of last kept file
    first_byte = kept[0][0]
    last_byte  = kept[-1][1]

    first_piece = first_byte // piece_length
    last_piece  = (last_byte - 1) // piece_length if last_byte > 0 else 0

    # Slice piece hashes
    new_pieces = pieces[first_piece * 20 : (last_piece + 1) * 20]

    # Adjust file offsets — subtract first_byte so offsets are relative to new start
    new_files = []
    for start, end, f in kept:
        new_files.append(f)

    # Add implicit pad at start if first file doesn't start on piece boundary
    new_info = dict(info)
    new_info[b'files']  = new_files
    new_info[b'pieces'] = new_pieces

    t[b'info'] = new_info
    return bencode(t)


def find_aria2c() -> str | None:
    """Find aria2c.exe — bundled next to the .pyw, or on PATH."""
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aria2c.exe')
    if os.path.exists(bundled):
        return bundled
    import shutil
    return shutil.which('aria2c') or shutil.which('aria2c.exe')

def torrent_file_id_map(torrent_data: bytes) -> dict:
    """Parse v1 torrent. Returns {key: (file_index_1based, full_path, length)}.
    Keys are both basename and full_path so callers can match either way.
    aria2c --select-file uses 1-based indices, skipping pad files."""
    t, _ = bdecode(torrent_data)
    info = t.get(b'info', {})
    result = {}
    if b'files' not in info:
        name = info.get(b'name', b'').decode('utf-8', errors='replace')
        result[name] = (1, name, info.get(b'length', 0))
        return result
    idx = 1  # aria2c 1-based, counts ALL files including pads
    for f in info[b'files']:
        path_parts = f[b'path']
        full_path  = '/'.join(p.decode('utf-8', errors='replace') for p in path_parts)
        length     = f.get(b'length', 0)
        is_pad     = full_path.startswith('.pad/') or '/.pad/' in full_path
        if not is_pad:
            basename = os.path.basename(full_path)
            entry = (idx, full_path, length)
            result[basename]  = entry  # match by filename only
            result[full_path] = entry  # match by full torrent path
        idx += 1
    return result


def get_exact_size(fname: str, url: str, all_hashes: dict, size_str: str) -> int:
    """Return the most accurate file size available.
    archive.org: exact byte count from metadata API.
    lolroms: approximate from listing string (best available).
    """
    if not is_lolroms_url(url):
        api_size = all_hashes.get(fname, {}).get('size', 0)
        if api_size:
            return api_size
    return parse_size_bytes(size_str)


def is_wayback_lolroms_url(url: str) -> bool:
    return 'web.archive.org' in url.lower() and 'lolroms.com' in url.lower()


def fetch_view_archive_filenames(url: str, access: str = None, secret: str = None):
    """Fetch file list from an archive.org view_archive.php ZIP viewer URL."""
    import urllib.parse as _up

    m = re.search(r'archive=(?:/\d+)?/items/([^/&]+)/([^&]+\.zip)', url, re.IGNORECASE)
    if not m:
        raise ValueError(f"Cannot parse view_archive URL: {url}")
    identifier = m.group(1)
    zip_name   = _up.unquote(m.group(2))

    # Fetch the original view_archive.php URL directly — canonical redirect
    # may serve different content
    headers = {**make_headers(access, secret), 'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        html_body = r.read().decode('utf-8', errors='replace')

    # Debug: log first 500 chars of response to help diagnose issues
    import logging as _log
    _snippet = html_body[:500].replace('\n', ' ')

    entries = []
    rows_found = 0
    for row in re.finditer(r'<tr>(.*?)</tr>', html_body, re.DOTALL):
        rows_found += 1
        row_html = row.group(1)
        href_m = re.search(r'<a href="(//archive\.org/download/[^"]+)">', row_html)
        size_m = re.search(r'<td[^>]*id="size"[^>]*>(\d+)', row_html)
        name_m = re.search(r'<a [^>]+>([^<]+)</a>', row_html)
        if href_m and size_m and name_m:
            href  = 'https:' + href_m.group(1)
            fname = html_unescape(name_m.group(1).strip())
            size  = size_m.group(1)
            entries.append((fname, size, href))

    if not entries:
        # Find the archext table section for diagnostics
        tbl_idx = html_body.find('archext')
        snippet = html_body[tbl_idx:tbl_idx+500] if tbl_idx != -1 else html_body[500:1000]
        raise ValueError(
            f'view_archive: 0 files parsed from {len(html_body)} bytes '
            f'({rows_found} rows). archext section: {snippet!r}')

    entries.sort(key=lambda x: x[0])
    return entries, zip_name


# ── Title aliases (known spelling mismatches between ROM sets and metadata) ───
_TITLE_ALIASES = {
    'ookami':      'okami',      # Japanese transliteration vs Western release name
    'einhaender':  'einhander',  # German ae umlaut expansion
    'einhander':   'einhander',
}

# ── Global URL fetch cache ────────────────────────────────────────────────────
_url_fetch_cache: dict = {}  # url+credentials signature → (entries, title)

def _fetch_html_cached(url: str, headers: dict = None) -> str:
    """Fetch a URL and cache the raw HTML/text response by URL."""
    sig = ('html', url)
    if sig in _url_fetch_cache:
        return _url_fetch_cache[sig][0]
    req = urllib.request.Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode('utf-8', errors='replace')
    _url_fetch_cache[sig] = (html, None)
    return html

def fetch_url_cached(url: str, access: str = None, secret: str = None) -> tuple[list, str | None]:
    """Fetch file listing for a URL, using an in-memory cache keyed by URL+credentials."""
    sig = (url, access, secret)
    if sig in _url_fetch_cache:
        return _url_fetch_cache[sig]
    if is_lolroms_url(url):
        result = fetch_lolroms_filenames(url)
    elif is_minerva_url(url):
        result = fetch_minerva_filenames(url)
    elif is_view_archive_url(url):
        result = fetch_view_archive_filenames(url, access, secret)
    else:
        result = fetch_archive_filenames(url, access, secret)
    _url_fetch_cache[sig] = result
    return result

def invalidate_url_cache(url: str = None):
    """Invalidate the fetch cache for a specific URL or all URLs."""
    global _url_fetch_cache
    if url is None:
        _url_fetch_cache = {}
    else:
        _url_fetch_cache = {k: v for k, v in _url_fetch_cache.items() if k[0] != url}


def fetch_lolroms_filenames(url: str) -> tuple[list, str | None]:
    """Fetch file listing from a lolroms.com category page (direct or via Wayback).
    Returns ([(filename, size_str, direct_download_url), ...], page_title | None).
    The third element is the actual lolroms.com download URL regardless of how the
    page was fetched — Wayback only archives HTML, not the files themselves.
    """
    # Strip fragment (#...) — urllib passes it through unlike browsers
    url = url.split('#')[0].rstrip('/')

    wayback = is_wayback_lolroms_url(url)

    headers = {
        'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/124.0.0.0 Safari/537.36',
        'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer':         'https://lolroms.com/',
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        content = r.read().decode('utf-8', errors='replace')

    # Page title from <h1> or derive from URL path
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.IGNORECASE | re.DOTALL)
    if h1:
        page_title = re.sub(r'<[^>]+>', '', h1.group(1)).strip()
    else:
        # Derive from the lolroms path portion of the URL
        lolroms_path = url[url.index('lolroms.com') + len('lolroms.com'):]
        page_title   = html.unescape(unquote(lolroms_path.strip('/')))

    # Extract file-list ul only (skip folder-list).
    # Use a find-from approach so a preceding </ul> (folder-list) doesn't truncate us.
    # File list is the second <ul> inside <main> — find it by position
    main_m = re.search(r'<main[^>]*>(.*)', content, re.DOTALL | re.IGNORECASE)
    main_content = main_m.group(1) if main_m else content
    uls = list(re.finditer(r'<ul[^>]*>', main_content, re.IGNORECASE))
    if len(uls) < 1:
        return [], page_title
    ul_start_m = uls[1] if len(uls) >= 2 else uls[0]
    file_list_block = main_content[ul_start_m.end():]
    ul_end = re.search(r'</ul>', file_list_block, re.IGNORECASE)
    if ul_end:
        file_list_block = file_list_block[:ul_end.start()]

    results = []
    for li in re.findall(r'<li[^>]*class=["\'](?:filei|file-item)["\'][^>]*>(.*?)</li>',
                         file_list_block, re.DOTALL | re.IGNORECASE):
        href_match = re.search(r'\bhref=["\']([^"\']+)["\']', li, re.IGNORECASE)
        if not href_match:
            continue
        href = href_match.group(1).split('#')[0]

        # Wayback rewrites hrefs to /web/TIMESTAMP/https://lolroms.com/...
        if wayback and 'lolroms.com' in href:
            lolroms_href = href[href.index('lolroms.com') + len('lolroms.com'):]
        else:
            lolroms_href = href

        ext = os.path.splitext(unquote(lolroms_href.split('/')[-1]))[1]

        # Filename: prefer span text inside file-link (older structure);
        # current structure has plain text after an <img> inside <a class="file">;
        # fall back to last path component of href if neither is found
        span_m = re.search(r'class=["\']file-link["\'][^>]*>.*?<span>([^<]+)</span>', li, re.DOTALL | re.IGNORECASE)
        if span_m:
            fname = html.unescape(span_m.group(1).strip()) + ext
        else:
            a_m = re.search(r'<a[^>]*class=["\']file["\'][^>]*>(.*?)</a>', li, re.DOTALL | re.IGNORECASE)
            text = html.unescape(re.sub(r'<[^>]+>', '', a_m.group(1))).strip() if a_m else ''
            fname = (text + ext) if text else html.unescape(unquote(lolroms_href.split('/')[-1]))

        # Size: first span inside class="meta" (current), class="file-meta" or
        # class="file-size" span (older structures)
        size_m = re.search(r'class=["\']meta["\'][^>]*>\s*<span>([^<]+)</span>', li, re.DOTALL | re.IGNORECASE)
        if not size_m:
            size_m = re.search(r'class=["\']file-meta["\'][^>]*>.*?<span>([^<]+)</span>', li, re.DOTALL | re.IGNORECASE)
        if not size_m:
            size_m = re.search(r'<span\s+class=["\']file-size["\']>(.*?)</span>', li, re.IGNORECASE)
        size_str = html.unescape(size_m.group(1)).strip() if size_m else ''

        # Build direct URL — href already has correct percent-encoding, just ensure spaces encoded
        direct_url = 'https://lolroms.com' + quote(lolroms_href, safe='/%:@!$&\'()*+,;=')
        if fname:
            results.append((fname, size_str, direct_url))

    return results, page_title


def get_remote_headers(url: str, headers: dict) -> dict:
    try:
        req = urllib.request.Request(url, headers=headers, method='HEAD')
        with urllib.request.urlopen(req) as resp:
            return {k.lower(): v for k, v in resp.headers.items()}
    except Exception:
        return {}



def load_etag_cache(cache_path: str) -> dict:
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '\t' in line:
                    fn, etag = line.split('\t', 1)
                    cache[fn] = etag
    return cache


def save_etag_cache(cache_path: str, cache: dict, lock: threading.Lock):
    with lock:
        with open(cache_path, 'w', encoding='utf-8') as f:
            for fn, etag in cache.items():
                f.write(f"{fn}\t{etag}\n")


SIZE_CACHE_FILE = '.romgogetter_sizes'

# ── Libretro DAT auto-fetch ────────────────────────────────────────────────────

LIBRETRO_DAT_BASE = 'https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/no-intro/'

# Maps keywords found in collection titles → libretro DAT filename (without .dat)
LIBRETRO_DAT_MAP = {
    'nintendo 3ds':          'Nintendo - Nintendo 3DS',
    'new nintendo 3ds':      'Nintendo - New Nintendo 3DS',
    '3ds':                   'Nintendo - Nintendo 3DS',
    'nintendo ds':           'Nintendo - Nintendo DS',
    'nintendo dsi':          'Nintendo - Nintendo DSi',
    'game boy advance':      'Nintendo - Game Boy Advance',
    'gba':                   'Nintendo - Game Boy Advance',
    'game boy color':        'Nintendo - Game Boy Color',
    'game boy':              'Nintendo - Game Boy',
    'nintendo 64':           'Nintendo - Nintendo 64',
    'n64':                   'Nintendo - Nintendo 64',
    'gamecube':              'Nintendo - GameCube',
    'wii':                   'Nintendo - Wii',
    'wii u':                 'Nintendo - Wii U',
    'nes':                   'Nintendo - Nintendo Entertainment System',
    'super nintendo':        'Nintendo - Super Nintendo Entertainment System',
    'snes':                  'Nintendo - Super Nintendo Entertainment System',
    'playstation':           'Sony - PlayStation',
    'playstation 2':         'Sony - PlayStation 2',
    'ps2':                   'Sony - PlayStation 2',
    'playstation portable':  'Sony - PlayStation Portable',
    'psp':                   'Sony - PlayStation Portable',
    'sega genesis':          'Sega - Mega Drive - Genesis',
    'mega drive':            'Sega - Mega Drive - Genesis',
    'sega saturn':           'Sega - Saturn',
    'dreamcast':             'Sega - Dreamcast',
    'game gear':             'Sega - Game Gear',
    'sega master system':    'Sega - Master System - Mark III',
    'atari 2600':            'Atari - 2600',
    'atari 7800':            'Atari - 7800',
    'atari jaguar':          'Atari - Jaguar',
    'neo geo pocket':        'SNK - Neo Geo Pocket Color',
    'turbografx':            'NEC - PC Engine - TurboGrafx-16',
}

def detect_libretro_dat(page_title: str) -> str | None:
    """Detect libretro DAT filename from collection page title."""
    if not page_title:
        return None
    lower = page_title.lower()
    # Try longest match first
    for keyword in sorted(LIBRETRO_DAT_MAP, key=len, reverse=True):
        if keyword in lower:
            return LIBRETRO_DAT_MAP[keyword]
    return None

def fetch_libretro_dat(dat_name: str) -> str | None:
    """Fetch a libretro DAT file from GitHub raw. Returns content or None."""
    from urllib.parse import quote
    url = LIBRETRO_DAT_BASE + quote(dat_name + '.dat')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None

def parse_libretro_dat_serials(content: str) -> dict:
    """Parse clrmamepro DAT content. Returns {filename_no_ext: serial}."""
    serial_map = {}
    # Match game blocks
    game_re  = re.compile(r'game\s*\((.+?)\n\)', re.DOTALL)
    rom_re   = re.compile(r'rom\s*\(\s*name\s+"([^"]+)"')
    serial_re = re.compile(r'serial\s+"([^"]+)"')
    for game_block in game_re.finditer(content):
        block = game_block.group(1)
        serial_m = serial_re.search(block)
        if not serial_m:
            continue
        serial = serial_m.group(1)
        for rom_m in rom_re.finditer(block):
            rom_name = rom_m.group(1)
            # Strip extension for matching
            key = os.path.splitext(rom_name)[0]
            serial_map[key] = serial
    return serial_map  # {filename_no_ext: serial}


# ── GitHub API helpers ───────────────────────────────────────────────────────
_github_token = ''  # set by app at fetch time

def _gh_headers(token=None):
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
         'Accept': 'application/vnd.github.v3+json'}
    t = token or _github_token
    if t:
        h['Authorization'] = f'token {t}'
    return h

# ── Title matching helpers (fuzzy + token, used in compat and exclude matching) ──

from difflib import SequenceMatcher as _SM

def _deaccent(s):
    for a, b in [('ö','o'),('ü','u'),('ä','a'),('ë','e'),('ï','i'),
                 ('Ö','o'),('Ü','u'),('Ä','a'),
                 ('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),
                 ('à','a'),('è','e'),('ì','i'),('ò','o'),('ù','u'),
                 ('â','a'),('ê','e'),('î','i'),('ô','o'),('û','u'),
                 ('ñ','n'),('ç','c'),('š','s'),('ž','z'),('č','c'),
                 ('ō','o'),('ū','u'),('ā','a'),('ē','e'),('ī','i')]:
        s = s.replace(a, b)
    return s

_STOPWORDS_C = {'a','an','the','of','in','on','at','to','for','and','or','with','by','from','is','as','but','up','if','edition','ver','version','complete','definitive','remastered','ea','sports'}
_BRACKET_C   = re.compile(r'(?<=\S)\s*[\[(][^\]\)]*[\]\)]')

def _cstrip(s):
    s = _BRACKET_C.sub('', s)
    s = re.sub(r'^[\[(]([^\]\)]+)[\]\)]$', r'\1', s.strip())
    s = re.sub(r'[:\-]\s*(the|a|an)\s*$', '', s, flags=re.IGNORECASE)
    return re.sub(r'\s{2,}', ' ', s).strip()

def _ctokenize(s):
    s = _deaccent(_cstrip(s)).lower()
    s = re.sub(r'[:\-\u2013\u2014,\'"()!®™]', ' ', s)
    return set(re.findall(r'[a-z0-9]+', s))

def _cnorm(s):
    n = re.sub(r'[^a-z0-9]', '', _deaccent(_cstrip(s)).lower())
    return _TITLE_ALIASES.get(n, n)

def _cscore(rom, compat):
    ta, tb = _ctokenize(rom), _ctokenize(compat)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    na, nb  = _cnorm(rom), _cnorm(compat)
    fuzzy   = _SM(None, na, nb).ratio() if na and nb else 0.0
    base    = 0.5 * jaccard + 0.5 * fuzzy
    ca = ta - _STOPWORDS_C
    cb = tb - _STOPWORDS_C
    if ca and cb:
        shared_words = {t for t in (ca & cb) if not re.match(r'^\d+$', t)}
        nums_a = {t for t in ca if re.match(r'^\d+$', t)}
        nums_b = {t for t in cb if re.match(r'^\d+$', t)}
        words_a = ca - nums_a
        words_b = cb - nums_b
        # Same non-numeric words but different numbers = different entry (e.g. Madden NFL 10 vs 13)
        if words_a and words_a == words_b and nums_a and nums_b and nums_a != nums_b:
            return 0.0
        if not shared_words:
            # Allow if cnorms match exactly (e.g. "Factotum 90" vs "factotum90")
            if na and nb and na == nb:
                return 1.0  # exact cnorm match — treat as perfect
            # Allow pure-number titles (e.g. "140")
            if ca == cb and ca:
                pass  # fall through to subset check
            else:
                return 0.0
        shorter, longer = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
        if shorter <= longer:
            # Allow single meaningful token if it's a real word (len >= 4), not just "2" or "hd"
            tok = next(iter(shorter)) if len(shorter) == 1 else None
            qualifies = len(shorter) >= 2 or (tok and len(tok) >= 4 and not re.match(r'^\d+$', tok))
            # Single-token rom: match if compat has no extra numbers (different sequel)
            extra_nums = (cb - ca) & {t for t in cb if re.match(r'^\d+$', t)}
            # If compat adds a number the rom doesn't have, it's a numbered sequel — block
            if extra_nums and not nums_a:
                return 0.0
            elif qualifies and (len(shorter) >= 2 or (fuzzy >= 0.4 and not extra_nums)):
                return max(base, 0.5 + 0.5 * (len(shorter) / len(longer)))

    return base

def normalize_title(title: str) -> str:
    """Strip leading articles in any language for grouping purposes."""
    articles = (
        # English
        'The ', 'A ', 'An ',
        # French
        "L'", 'Le ', 'La ', 'Les ', 'Un ', 'Une ', 'Des ',
        # German
        'Der ', 'Die ', 'Das ', 'Ein ', 'Eine ',
        # Spanish
        'El ', 'Los ', 'Las ', 'Un ', 'Una ',
        # Italian
        'Il ', 'Lo ', 'Gli ', 'Un ', 'Uno ', 'Una ',
        # Portuguese
        'O ', 'A ', 'Os ', 'As ', 'Um ', 'Uma ',
        # Dutch
        'De ', 'Het ', 'Een ',
    )
    for art in articles:
        if title.startswith(art):
            return title[len(art):]
    return title


def has_non_english_article(title: str) -> bool:
    """Return True if title starts with a non-English language article."""
    articles = (
        # French
        "L'", "Le ", "La ", "Les ", "Un ", "Une ", "Des ",
        # German
        "Der ", "Die ", "Das ", "Ein ", "Eine ", "Des ", "Dem ",
        # Spanish
        "El ", "Los ", "Las ", "Un ", "Una ", "Unos ", "Unas ",
        # Italian
        "Il ", "Lo ", "Gli ", "Un ", "Uno ", "Una ",
        # Portuguese
        "O ", "A ", "Os ", "As ", "Um ", "Uma ",
        # Dutch
        "De ", "Het ", "Een ",
    )
    for art in articles:
        if title.startswith(art):
            return True
    return False


def load_size_cache(dest_dir: str) -> dict:
    """Load filename→exact_bytes mapping from local dot file."""
    path = os.path.join(dest_dir, SIZE_CACHE_FILE)
    cache = {}
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if '\t' in line:
                        fn, size = line.split('\t', 1)
                        cache[fn] = int(size)
    except Exception:
        pass
    return cache


def save_size_cache(dest_dir: str, cache: dict, lock: threading.Lock):
    path = os.path.join(dest_dir, SIZE_CACHE_FILE)
    with lock:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for fn, size in cache.items():
                    f.write(f"{fn}\t{size}\n")
        except Exception:
            pass



def fetch_file_hashes(base_url: str, headers: dict) -> dict:
    identifier = base_url.rstrip('/').split('/')[-1]
    api_url    = f"https://archive.org/metadata/{identifier}"
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception:
        return {}
    hashes = {}
    for f in data.get('files', []):
        name = f.get('name', '')
        if name:
            hashes[name] = {
                'md5':  f.get('md5',  ''),
                'size': int(f.get('size', 0) or 0),
            }
    return hashes


def compute_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def verify_file(path: str, expected: dict) -> tuple[bool, str]:
    local_size = os.path.getsize(path)
    exp_size   = expected.get('size', 0)
    if exp_size and local_size != exp_size:
        return False, f"size mismatch (local {local_size} != expected {exp_size})"
    if expected.get('md5'):
        if compute_md5(path) != expected['md5']:
            return False, "MD5 mismatch"
        return True, 'md5 ok'
    return True, 'size ok'


# ── Compatibility sources ──────────────────────────────────────────────────────

def _compat_fetch_rpcs3() -> dict:
    """Fetch RPCS3 PS3 compatibility. Returns {normalized_title: (status, color)}."""
    import json as _json
    STATUS_COLORS = {
        'Playable': GREEN, 'Ingame': YELLOW, 'Intro': '#ff8c00',
        'Loadable': RED,   'Nothing': RED,
    }
    # 1. Fetch title ID mapping
    req = urllib.request.Request(
        'https://raw.githubusercontent.com/aldostools/Resources/refs/heads/main/titleid.txt',
        headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode('utf-8', errors='replace')
    id_to_title = {}
    for line in txt.splitlines():
        parts = line.strip().split('\t')
        if len(parts) < 2:
            parts = line.strip().split(' ', 1)
        if len(parts) >= 2:
            id_to_title[parts[0].strip()] = parts[1].strip()
    print(f'[RPCS3] titleid: {len(id_to_title)} entries, sample: {list(id_to_title.items())[:2]}')

    # 2. Fetch compat — key is "results" not "return"
    req2 = urllib.request.Request('https://rpcs3.net/compatibility?api=v1&export',
                                  headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req2, timeout=30) as r:
        data = _json.loads(r.read())
    ret = data.get('results', data.get('return', {}))
    print(f'[RPCS3] compat: {len(ret)} entries, first: {next(iter(ret.items()), None)}')

    # 3. Join - keep best status per title, prefer clean titles over variants
    STATUS_RANK = {'Playable': 0, 'Ingame': 1, 'Intro': 2, 'Loadable': 3, 'Nothing': 4}
    VARIANT_WORDS = re.compile(r'\\b(move|demo|trial|sample|network|online|soundtrack|beta|promo)\\b', re.IGNORECASE)
    statuses = {}
    # Sort by title length ascending so clean titles are processed first
    sorted_items = sorted(ret.items(), key=lambda x: len(id_to_title.get(x[0], '')))
    for game_id, info in sorted_items:
        status = info.get('status', '')
        if status not in STATUS_COLORS:
            continue
        # Title is nested in patchsets or directly on info; fall back to id_to_title
        title = ''
        try:
            title = info['patchsets'][0]['packages'][0]['titles'][0]['title']
        except (KeyError, IndexError, TypeError):
            pass
        if not title:
            title = info.get('title', '') or id_to_title.get(game_id, '')
        if not title:
            continue
        norm = normalize_title(title).lower()
        norm_clean = re.sub(r'[^a-z0-9]', '', norm)
        # If this title has variant words and a clean version exists, skip
        if VARIANT_WORDS.search(title):
            # Strip both (...) and [...] variant groups, then check for plain title
            base_norm = re.sub(r'\\s*\\([^)]*\\)', '', norm)
            base_norm = re.sub(r'\\s*\\[[^\\]]*\\]', '', base_norm).strip()
            base_norm = re.sub(r'\s+', ' ', base_norm).strip()
            if base_norm in statuses:
                continue
        if norm not in statuses or STATUS_RANK.get(status, 99) < STATUS_RANK.get(statuses[norm][0], 99):
            statuses[norm] = (status, STATUS_COLORS[status])
    return statuses


def _compat_fetch_eden(*, progress_cb=None) -> dict:
    """Fetch Eden Switch compatibility from EmuReady (paginated batch tRPC)."""
    import json as _json, urllib.parse as _up
    RANK_MAP = {
        1: ('Perfect',  '#4a9eff'),
        2: ('Playable', GREEN),
        3: ('Ingame',   YELLOW),
        4: ('Intro',    '#ff8c00'),
        5: ('Nothing',  RED),
    }
    EMULATOR_ID = '43bfc023-ec22-422d-8324-048a8ec9f28f'
    BASE = ('https://www.emuready.com/api/trpc/users.me,systems.get,devices.get,'
            'socs.get,emulators.get,listings.performanceScales,listings.get')
    HEADERS = {
        'accept': '*/*',
        'content-type': 'application/json',
        'referer': 'https://www.emuready.com/listings?emulatorIds=%5B%2243bfc023-ec22-422d-8324-048a8ec9f28f%22%5D&page=1',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    }
    try:
        import cloudscraper as _cs
        scraper = _cs.create_scraper()
        def _get(url): return scraper.get(url, headers=HEADERS, timeout=30)
    except ImportError:
        def _get(url):
            req = urllib.request.Request(url, headers=HEADERS)
            class _R:
                def __init__(self, r): self.status_code = r.status; self._d = r.read()
                def json(self): return _json.loads(self._d)
            return _R(urllib.request.urlopen(req, timeout=30))
    statuses = {}
    page = 1
    while True:
        payload = {
            '0': {'json': None, 'meta': {'values': ['undefined']}},
            '1': {'json': None, 'meta': {'values': ['undefined']}},
            '2': {'json': {'limit': 10000}},
            '3': {'json': {'limit': 10000}},
            '4': {'json': {'limit': 100}},
            '5': {'json': None, 'meta': {'values': ['undefined']}},
            '6': {'json': {'page': page, 'limit': 100, 'emulatorIds': [EMULATOR_ID]}},
        }
        url = f'{BASE}?batch=1&input={_up.quote(_json.dumps(payload))}'
        if progress_cb: progress_cb(f'EmuReady page {page}...')
        r = _get(url)
        if r.status_code != 200:
            break
        listings = r.json()[6].get('result', {}).get('data', {}).get('json', {}).get('listings', [])
        if not listings:
            break
        for item in listings:
            if item.get('emulatorId') != EMULATOR_ID:
                continue
            title = item.get('game', {}).get('title', '')
            rank  = item.get('performance', {}).get('rank', 99)
            if not title:
                continue
            status, color = RANK_MAP.get(min(rank, 5), ('Unknown', FG2))
            norm = normalize_title(title)
            # Keep best rank (lowest number) across multiple device reports
            if norm not in statuses or rank < statuses[norm][2]:
                statuses[norm] = (status, color, rank)
        if len(listings) < 100:
            break
        page += 1
    return {k: v[:2] for k, v in statuses.items()}


def _compat_fetch_azahar() -> dict:
    """Fetch Azahar 3DS compatibility from GitHub JSON file."""
    import json as _json
    STATUS_MAP = {
        0: ('Perfect',  '#4a9eff'),
        1: ('Playable', GREEN),
        2: ('Ingame',   YELLOW),
        3: ('Ingame -', YELLOW),
        4: ('Intro',    '#ff8c00'),
        5: ('Nothing',  RED),
    }
    url = ('https://raw.githubusercontent.com/azahar-emu/compatibility-list'
           '/master/compatibility_list.json')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = _json.loads(r.read())
    statuses = {}
    for entry in data:
        rating = entry.get('compatibility', 99)
        title  = entry.get('title', '').strip()
        if not title:
            continue
        if rating == 99:
            status, color = 'Unknown', '#9b59b6'
        elif rating not in STATUS_MAP:
            continue
        else:
            status, color = STATUS_MAP[rating]
        norm = _deaccent(normalize_title(title)).lower()
        if norm not in statuses:
            statuses[norm] = (status, color)
    return statuses


def _compat_fetch_pcsx2() -> dict:
    """Fetch PCSX2 PS2 compatibility from GameIndex.yaml via GitHub API."""
    import json as _json
    # compat: 0=Unknown, 1=Nothing, 2=Intro, 3=Menu, 4=Ingame, 5=Playable, 6=Perfect
    STATUS_MAP = {
        6: ('Perfect',    '#4a9eff'),
        5: ('Playable',   GREEN),
        4: ('Ingame',     YELLOW),
        3: ('Menu',       '#ff8c00'),
        2: ('Intro',      '#ff8c00'),
        1: ('Nothing',    RED),
        0: ('Unknown',    '#9b59b6'),
    }
    # Fetch GameIndex.yaml directly from raw GitHub (no API, no rate limit, no size limit)
    url = 'https://raw.githubusercontent.com/PCSX2/pcsx2/master/bin/resources/GameIndex.yaml'
    yaml_text = _fetch_html_cached(url, {'User-Agent': 'Mozilla/5.0'})
    statuses = {}
    # Parse YAML manually — each entry: "SERIAL-12345:\n  name: \"Game Title\"\n  compat: N"
    # GameIndex.yaml omits compat: for entries that are implicitly Playable (5).
    # We default current_compat to 5 at the start of each serial block so those
    # entries are correctly captured instead of silently dropped.
    current_name = None
    current_compat = 5  # implicit default: Playable
    for line in yaml_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('name:') and not stripped.startswith('name-'):
            val = stripped[5:].strip().strip('"').strip("'")
            current_name = val
        elif stripped.startswith('compat:'):
            try:
                current_compat = int(stripped[7:].strip())
            except ValueError:
                current_compat = 5
        elif stripped == '' or (not line.startswith(' ') and not line.startswith('\t') and stripped.endswith(':')):
            # New serial block or blank line — store previous entry
            if current_name and current_compat in STATUS_MAP:
                norm = normalize_title(current_name).lower()
                if norm not in statuses or STATUS_MAP[current_compat][0] != 'Unknown':
                    statuses[norm] = STATUS_MAP[current_compat]
            if stripped.endswith(':'):
                current_name = None
                current_compat = 5  # reset to implicit default for next block
    # Store last entry
    if current_name and current_compat in STATUS_MAP:
        norm = normalize_title(current_name).lower()
        if norm not in statuses:
            statuses[norm] = STATUS_MAP[current_compat]
    return statuses


def _compat_fetch_cemu() -> dict:
    """Fetch CEMU Wii U compatibility from compat.cemu.info."""
    import html as _html
    STATUS_COLORS = {
        'Perfect': '#4a9eff', 'Playable': GREEN, 'Runs': YELLOW,
        'Loads': '#ff8c00', 'Unplayable': RED,
    }
    req = urllib.request.Request('https://compat.cemu.info/',
                                 headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        html_body = r.read().decode('utf-8', errors='replace')
    statuses = {}
    # Status is an image: smiley-5=Perfect, smiley-4=Playable, smiley-3=Runs,
    #                      smiley-2=Loads, smiley-1=Unplayable
    IMG_STATUS = {
        'smiley-5': ('Perfect',    '#4a9eff'),
        'smiley-4': ('Playable',   GREEN),
        'smiley-3': ('Runs',       YELLOW),
        'smiley-2': ('Loads',      '#ff8c00'),
        'smiley-1': ('Unplayable', RED),
        'unknown':  ('Unknown',    '#9b59b6'),
    }
    table_m = re.search(r'<table[^>]*>(.*?)</table>', html_body, re.DOTALL)
    if table_m:
        for row in re.finditer(r'<tr[^>]*>(.*?)</tr>', table_m.group(1), re.DOTALL):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row.group(1), re.DOTALL)
            if len(cells) < 5:
                continue
            # td[1]: title link
            a_m = re.search(r'<a[^>]+>([^<]+)</a>', cells[0])
            if not a_m:
                continue
            title = _html.unescape(a_m.group(1)).strip()
            # td[5]: smiley image — extract key from src e.g. "smiley-4.png"
            img_m = re.search(r'(smiley-\d+|unknown)', cells[4])
            if not img_m:
                continue
            status, color = IMG_STATUS.get(img_m.group(1), (None, None))
            if title and status:
                norm = normalize_title(title).lower()
                if norm not in statuses:
                    statuses[norm] = (status, color)
    return statuses


def _compat_fetch_xenia() -> dict:
    """Fetch Xenia Xbox 360 compatibility via GitHub issues API."""
    import json as _json
    # Xenia canary uses state-* prefixed labels
    LABEL_MAP = {
        'state-playable':  ('Playable',  GREEN),
        'state-gameplay':  ('Gameplay',  YELLOW),
        'state-intro':     ('Intro',     '#ff8c00'),
        'state-starts':    ('Starts',    '#ff8c00'),
        'state-nothing':   ('Nothing',   RED),
    }
    statuses = {}
    page = 1
    while True:
        url = (f'https://api.github.com/repos/xenia-canary/game-compatibility'
               f'/issues?state={"all" if _github_token else "open"}&per_page=100&page={page}')
        req = urllib.request.Request(url, headers=_gh_headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                issues = _json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError('Github limit reached. Enter github token:')
            if e.code == 422:
                if not statuses:
                    raise RuntimeError('Github limit reached. Enter github token:')
                break
            raise
        if not issues:
            break
        for issue in issues:
            title  = issue.get('title', '')
            labels = [l['name'] for l in issue.get('labels', [])]
            # Match state-* label
            matched = next((LABEL_MAP[l] for l in labels if l in LABEL_MAP), None)
            if title and matched:
                status, color = matched
                # Strip game ID prefix e.g. "5553083B - Assassin's Creed II"
                clean = re.sub(r'^[0-9A-Fa-f]{8}\s*-\s*', '', title).strip()
                norm  = normalize_title(clean).lower()
                if norm not in statuses:
                    statuses[norm] = (status, color)
        if len(issues) < 100:
            break
        page += 1
    return statuses


def _compat_fetch_teknoparrot() -> dict:
    """Fetch TeknoParrot arcade compatibility from teknoparrot.com."""
    STATUS_COLORS = {
        'Perfect':   GREEN,
        'Great':     GREEN,
        'Issues':    YELLOW,
        'Unplayable': RED,
        'Unknown':   FG2,
    }
    req = urllib.request.Request(
        'https://teknoparrot.com/en/Compatibility/Index',
        headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode('utf-8', errors='replace')
    # Parse rows: each row has two <td> with same game name, then status, genre, system
    statuses = {}
    for m in re.finditer(
            r'<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(.*?)</td>.*?'
            r'<td[^>]*>(.*?)</td>',
            html, re.DOTALL):
        name   = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        status = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if name and status in STATUS_COLORS:
            norm = normalize_title(name).lower()
            if norm not in statuses:
                mapped_status = 'Playable' if status == 'Great' else status
                statuses[norm] = (mapped_status, STATUS_COLORS[status])
    return statuses


def _compat_fetch_vita3k() -> dict:
    """Fetch Vita3K PS Vita compatibility via GitHub Issues API (state=open)."""
    import json as _json
    LABEL_MAP = {
        'Playable':  ('Playable',  GREEN),
        'Ingame +':  ('Ingame +',  GREEN),
        'Ingame -':  ('Ingame -',  YELLOW),
        'Menu':      ('Menu',      '#ff8c00'),
        'Intro':     ('Intro',     '#ff8c00'),
        'Bootable':  ('Bootable',  RED),
        'Nothing':   ('Nothing',   RED),
    }
    statuses = {}
    page = 1
    while True:
        url = ('https://api.github.com/repos/Vita3K/compatibility'
               f'/issues?state={"all" if _github_token else "open"}&per_page=100&page={page}')
        req = urllib.request.Request(url, headers=_gh_headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                remaining = int(r.headers.get('X-RateLimit-Remaining', 999))
                issues = _json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError(
                    'Github limit reached. Enter github token:')
            if e.code == 422:
                if not statuses:
                    raise RuntimeError('Github limit reached. Enter github token:')
                break
        if not issues:
            break
        for issue in issues:
            raw_title = issue.get('title', '')
            labels    = [l['name'] for l in issue.get('labels', [])]
            matched   = next((LABEL_MAP[l] for l in labels if l in LABEL_MAP), None)
            if raw_title and matched:
                status, color = matched
                # Strip title ID suffix: "Persona 4 Golden [PCSE00120]"
                clean = re.sub(r'\s*[\[(][A-Z]{4}\d{5}[\])]\s*$', '', raw_title).strip()
                clean = re.sub(r'\s+', ' ', clean).strip()
                norm  = normalize_title(clean).lower()
                if norm not in statuses:
                    statuses[norm] = (status, color)
        if len(issues) < 100:
            break
        page += 1
    return statuses



def _compat_fetch_ppsspp(progress_cb=None) -> dict:
    """Fetch PPSSPP PSP compatibility from report.ppsspp.org paginated HTML."""
    import html as _html

    STATUS_COLOR = {
        'Perfect':      '#4a9eff',
        'Playable':     GREEN,
        'Ingame':       YELLOW,
        'Menu':         '#ff8c00',
        'Intro':        '#ff8c00',
        'Broken':       RED,
        'Unknown':      '#9b59b6',
        'Unreported':   '#9b59b6',
    }

    _ROW_RE  = re.compile(
        r'<tr class="games">.*?<a href="[^"]*" class="title">(.*?)</a>.*?'
        r'<span class="label[^"]*">([^<]+)</span>',
        re.DOTALL)
    _PAGE_RE = re.compile(r'\?page=(\d+)')

    statuses = {}
    page = 1
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    max_page = None
    while True:
        url = f'https://report.ppsspp.org/games?page={page}'
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                html_text = r.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            if page == 1:
                raise RuntimeError(f'PPSSPP report site unavailable: {e.code}')
            break

        if max_page is None:
            pages_found = [int(p) for p in _PAGE_RE.findall(html_text)]
            max_page = max(pages_found) if pages_found else 1

        rows = _ROW_RE.findall(html_text)
        if not rows:
            break

        if progress_cb:
            _pg, _mx = page, max_page
            progress_cb(f'Fetching page {_pg}/{_mx}...')

        for raw_title, status_text in rows:
            title = _html.unescape(raw_title).strip()
            status = _html.unescape(status_text).strip()
            if status == 'Unreported':
                status = 'Unknown'
            color = STATUS_COLOR.get(status, '#9b59b6')
            if not title or not status:
                continue
            norm = normalize_title(title).lower()
            if norm not in statuses:
                statuses[norm] = (status, color)

        if page >= max_page:
            break
        page += 1

    return statuses


COMPAT_SOURCES = {
    'RPCS3 (PS3)':       {'fetch': _compat_fetch_rpcs3,  'platform': 'Sony PlayStation 3'},
    'Eden (Switch)':     {'fetch': _compat_fetch_eden,    'platform': 'Nintendo Switch'},
    'PCSX2 (PS2)':      {'fetch': _compat_fetch_pcsx2,   'platform': 'Sony PlayStation 2'},
    'Azahar (3DS)':     {'fetch': _compat_fetch_azahar,  'platform': 'Nintendo 3DS'},
    'CEMU (Wii U)':      {'fetch': _compat_fetch_cemu,    'platform': 'Nintendo Wii U'},
    'Xenia (Xbox 360)':  {'fetch': _compat_fetch_xenia,   'platform': 'Microsoft Xbox 360'},
    'TeknoParrot (Arcade)': {'fetch': _compat_fetch_teknoparrot, 'platform': 'Arcade'},
    'Vita3K (PS Vita)':  {'fetch': _compat_fetch_vita3k,  'platform': 'Sony PlayStation Vita'},
    'PPSSPP (PSP)':      {'fetch': _compat_fetch_ppsspp,  'platform': 'Sony PlayStation Portable'},
}

# ── Main App ──────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.settings = load_settings()

        self.root = tk.Tk()
        self.root.title(f'{APP_NAME}  {APP_VER}')
        self.root.configure(bg=BG)
        self.root.geometry(self.settings.get('geometry', '1500x1000'))
        self.root.resizable(True, True)
        _init_fonts(self.settings.get('font_size', 10))

        self._apply_styles()

        self.rom_dict        = {}
        self.summary         = {}
        self.page_title      = None
        self.dat_mode        = False
        self.raw_file_entries = []
        self._all_tree_items  = {}
        self._cycle_pos       = {}
        self._fetch_cancel    = threading.Event()
        self.serial_map       = {}

        self.access      = tk.StringVar(value=self.settings.get('access',       ''))
        self.secret      = tk.StringVar(value=self.settings.get('secret',       ''))
        self.dest_dir    = tk.StringVar(value=self.settings.get('dest_dir',     ''))
        self.local_source  = tk.StringVar(value=self.settings.get('local_source', ''))
        self.local_source.trace_add('write', lambda *_: setattr(self, '_local_source_cache', None))
        self.exclude_dir   = tk.StringVar(value=self.settings.get('exclude_dir', ''))
        self.github_token  = tk.StringVar(value=self.settings.get('github_token', ''))
        self.parallel    = tk.IntVar(   value=self.settings.get('parallel',     MAX_PARALLEL))
        self.retries     = tk.IntVar(   value=self.settings.get('retries',      MAX_RETRIES))
        self.stuck       = tk.IntVar(   value=self.settings.get('stuck',        STUCK_TIMEOUT))
        self.aria2_split = tk.IntVar(   value=self.settings.get('aria2_split',  5))
        self.aria2_speed = tk.StringVar(value=self.settings.get('aria2_speed',  '0'))
        self.verify_mode = tk.StringVar(value=self.settings.get('verify_mode',  'Hash'))
        self.mode        = tk.StringVar(value=self.settings.get('mode', '1G1R English only'))
        self.ra_top_n        = tk.IntVar(   value=self.settings.get('ra_top_n',   100))
        self.ra_min_players  = tk.IntVar(   value=self.settings.get('ra_min_players', 1000))
        self.ra_filter_mode  = tk.StringVar(value=self.settings.get('ra_filter_mode', 'top_n'))
        self.ra_system   = tk.StringVar(value=self.settings.get('ra_system',  ''))
        self.igdb_platform_id  = tk.IntVar(   value=self.settings.get('igdb_platform_id', 0))
        self.igdb_platform_name= tk.StringVar(value=self.settings.get('igdb_platform_name', ''))
        self.igdb_top_n        = tk.IntVar(   value=self.settings.get('igdb_top_n', 100))
        self._igdb_token       = None   # cached OAuth token
        self._igdb_platforms   = []     # [(id, name), ...] populated on first fetch
        self.moby_url          = tk.StringVar(value=self.settings.get('moby_url', ''))
        self.moby_top_n        = tk.IntVar(   value=self.settings.get('moby_top_n', 100))
        self.moby_min_score    = tk.DoubleVar(value=self.settings.get('moby_min_score', 7.0))
        self.top_n_max_size_gb = tk.DoubleVar(value=self.settings.get('top_n_max_size_gb', 10.0))
        self.moby_filter_mode  = tk.StringVar(value=self.settings.get('moby_filter_mode', 'top_n'))
        self.igdb_min_score    = tk.DoubleVar(value=self.settings.get('igdb_min_score', 70.0))
        self.igdb_filter_mode  = tk.StringVar(value=self.settings.get('igdb_filter_mode', 'top_n'))
        self._moby_platforms   = []     # [(slug, name), ...]
        self.top_n_source      = tk.StringVar(value=self.settings.get('top_n_source', 'RetroAchievements'))
        self.ss_platform_id    = tk.IntVar(   value=self.settings.get('ss_platform_id', 0))
        self.ss_platform_name  = tk.StringVar(value=self.settings.get('ss_platform_name', ''))
        self.ss_platform_name.trace_add('write', lambda *_: self._auto_set_compat_emulator(self.ss_platform_name.get()))
        self.ss_top_n          = tk.IntVar(   value=self.settings.get('ss_top_n', 100))
        self.ss_min_rating     = tk.DoubleVar(value=self.settings.get('ss_min_rating', 0.0))
        self.ss_filter_mode    = tk.StringVar(value=self.settings.get('ss_filter_mode', 'top_n'))
        self.ss_sort_by        = tk.StringVar(value=self.settings.get('ss_sort_by', 'scrapes'))
        self.ss_english_only   = tk.BooleanVar(value=self.settings.get('ss_english_only', True))
        self._ss_platforms     = []     # [(id, name), ...]
        self._ss_genres        = self.settings.get('ss_genres', [])
        self._ss_genre_id_map  = self.settings.get('ss_genre_id_map', {})
        self._ss_genre_parent_map = self.settings.get('ss_genre_parent_map', {})
        self.ss_genre_filter   = tk.StringVar(value=self.settings.get('ss_genre_filter', 'All'))
        self.dat_path    = ''
        self.url_groups: dict     = load_groups()
        self.dat_groups: dict     = load_dat_groups()
        self._dat_group_cache: dict = {}  # name -> merged parsed DAT dict

        self.nb = ttk.Notebook(self.root)

        self.tab_setup    = tk.Frame(self.nb, bg=BG)
        self.tab_analysis = tk.Frame(self.nb, bg=BG)
        self.tab_compat   = tk.Frame(self.nb, bg=BG)
        self.tab_download = tk.Frame(self.nb, bg=BG)

        self.nb.add(self.tab_setup,    text='  Setup  ')
        self.nb.add(self.tab_analysis, text='  Selection  ')
        self.nb.add(self.tab_compat,   text='  Compatibility  ')
        self.nb.add(self.tab_download, text='  Download  ')

        # ── Persistent debug log — pack BEFORE notebook so it anchors to bottom ─
        debug_frame = tk.LabelFrame(self.root, text=' Debug Log ', bg=BG, fg=FG2,
                                    font=FONT_SM, padx=8, pady=4)
        debug_frame.pack(side='bottom', fill='x', padx=8, pady=(4, 8))
        debug_top = tk.Frame(debug_frame, bg=BG)
        debug_top.pack(fill='x')
        tk.Button(debug_top, text='Clear', bg=BG3, fg=FG2, font=FONT_SM,
                  relief='flat', padx=6,
                  command=lambda: self.debug_log.delete('1.0', 'end')
                  ).pack(side='right')
        self.log_autotail = tk.BooleanVar(value=True)
        tk.Checkbutton(debug_top, text='Auto-tail', variable=self.log_autotail,
                       bg=BG, fg=FG2, selectcolor=BG3, activebackground=BG,
                       activeforeground=FG, font=FONT_SM, relief='flat',
                       command=lambda: self.debug_log.see('end') if self.log_autotail.get() else None
                       ).pack(side='right', padx=(4, 8))
        tk.Label(debug_top, text='Ctrl+A / Ctrl+C to copy', bg=BG, fg='#555555',
                 font=FONT_SM).pack(side='left')
        debug_sb = tk.Scrollbar(debug_frame)
        debug_sb.pack(side='right', fill='y')
        self.debug_log = tk.Text(
            debug_frame, bg=BG2, fg=FG2, font=FONT_SM,
            height=10, wrap='word', relief='flat', borderwidth=0,
            yscrollcommand=debug_sb.set, state='normal',
        )
        self.debug_log.pack(fill='x')
        debug_sb.config(command=self.debug_log.yview)
        # Read-only but allow copy / select-all shortcuts through
        _COPY_KEYS = {'c', 'a', '/'}
        def _log_key(e):
            if e.state & 0x4 and e.keysym.lower() in _COPY_KEYS:
                return  # let Ctrl+C / Ctrl+A / Ctrl+/ pass through
            return 'break'
        self.debug_log.bind('<Key>', _log_key)
        self.debug_log.bind('<BackSpace>', lambda e: 'break')

        # Redirect stdout/stderr to debug log so print() and tracebacks show up
        import sys as _sys
        class _DebugRedirect:
            def __init__(self, app): self.app = app
            def write(self, s):
                if s.strip(): self.app._debug(s.rstrip())
            def flush(self): pass
        _redir = _DebugRedirect(self)
        _sys.stdout = _redir
        _sys.stderr = _redir

        # Notebook fills the rest
        self.nb.pack(fill='both', expand=True, padx=8, pady=(8, 0))

        # Font size buttons overlaid on the notebook tab bar
        def _place_font_btns(e=None):
            nb_x = self.nb.winfo_x()
            nb_y = self.nb.winfo_y()
            nb_w = self.nb.winfo_width()
            self._font_btn_frame.place(x=nb_x + nb_w - 2, y=nb_y + 2, anchor='ne')

        self._font_btn_frame = tk.Frame(self.root, bg=BG)
        tk.Button(self._font_btn_frame, text='A-', bg=BG2, fg=FG2, font=('Consolas', 9),
                  relief='flat', padx=5, pady=2,
                  command=lambda: self._change_font_size(-1)).pack(side='left')
        tk.Button(self._font_btn_frame, text='A+', bg=BG2, fg=FG2, font=('Consolas', 9),
                  relief='flat', padx=5, pady=2,
                  command=lambda: self._change_font_size(1)).pack(side='left', padx=(2, 0))
        self.root.bind('<Configure>', _place_font_btns)
        self.root.after(100, _place_font_btns)

        def _make_scrollable(tab):
            """Wrap a tab in a scrollable canvas. Returns the inner frame."""
            canvas = tk.Canvas(tab, bg=BG, highlightthickness=0)
            sb = ttk.Scrollbar(tab, orient='vertical', command=canvas.yview)
            canvas.configure(yscrollcommand=sb.set)
            sb.pack(side='right', fill='y')
            canvas.pack(side='left', fill='both', expand=True)
            inner = tk.Frame(canvas, bg=BG)
            win_id = canvas.create_window((0, 0), window=inner, anchor='nw')
            def _on_resize(e):
                canvas.itemconfig(win_id, width=e.width)
            canvas.bind('<Configure>', _on_resize)
            def _on_frame_resize(e):
                canvas.configure(scrollregion=canvas.bbox('all'))
            inner.bind('<Configure>', _on_frame_resize)
            def _on_mousewheel(e):
                canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')
            canvas.bind_all('<MouseWheel>', _on_mousewheel)
            return inner

        # Save original tab frames for nb.select() before _make_scrollable overwrites them
        self._nb_tab_setup    = self.tab_setup
        self._nb_tab_analysis = self.tab_analysis
        self._nb_tab_compat   = self.tab_compat
        self._nb_tab_download = self.tab_download
        self.tab_setup    = _make_scrollable(self.tab_setup)
        # Analysis tab must NOT be wrapped in a scrollable canvas — the treeview
        # needs fill/expand to work, which canvas inner frames cannot provide.
        # The treeview has its own scrollbar already.
        self.tab_download = _make_scrollable(self.tab_download)

        self._build_setup()
        self._build_analysis()
        self._build_compat()
        self._build_download()

        # Show the correct mode panel (RA Top / DAT) for the saved mode on startup
        self._on_mode_change()
        self._init_done = True  # allow _save_settings in subsequent _on_mode_change calls

        # Default to Setup tab (Analysis is empty until GoGet is run)
        self.nb.select(0)

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        saved_urls = self.settings.get('urls', '')
        saved_group = self.settings.get('url_group', '')
        if saved_group and saved_group in self.url_groups:
            # Load group URLs — they're the authoritative source
            self.url_text.insert('1.0', self.url_groups[saved_group])
        elif saved_urls:
            self.url_text.insert('1.0', saved_urls)
        self._refresh_group_combo()
        if saved_group and saved_group in self.url_groups:
            self.group_var.set(saved_group)

        # Restore DAT group selection and URLs
        saved_dat_group = self.settings.get('dat_group', '')
        if saved_dat_group and hasattr(self, 'dat_group_var'):
            self.dat_group_var.set(saved_dat_group)
            self._refresh_dat_group_combo()
            # Load that group's URLs into the text box
            if saved_dat_group in self.dat_groups:
                self.dat_group_text.delete('1.0', 'end')
                self.dat_group_text.insert('1.0', self.dat_groups[saved_dat_group])
        elif hasattr(self, 'dat_group_text'):
            saved_dat_urls = self.settings.get('dat_group_urls', '')
            if saved_dat_urls:
                self.dat_group_text.delete('1.0', 'end')
                self.dat_group_text.insert('1.0', saved_dat_urls)

    def _change_font_size(self, delta):
        new_size = max(7, min(20, _BASE_FONT_SIZE + delta))
        _init_fonts(new_size)
        # Update ttk styles to match
        style = ttk.Style()
        style.configure('TNotebook.Tab', font=FONT)
        self._save_settings()

    def _apply_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook',     background=BG,  borderwidth=0)
        style.configure('TNotebook.Tab', background=BG2, foreground=FG2,
                        font=FONT, padding=[12, 6])
        style.map('TNotebook.Tab',
                  background=[('selected', BG3)],
                  foreground=[('selected', FG)])
        style.configure('Horizontal.TProgressbar',
                        troughcolor='#3a3a3a', background=ACC, thickness=16)
        style.configure('Paused.Horizontal.TProgressbar',
                        troughcolor='#3a3a3a', background='#888', thickness=16)

    def _save_settings(self):
        save_settings({
            'geometry':     self.root.geometry(),
            'font_size':    _BASE_FONT_SIZE,
            'access':       self.access.get(),
            'secret':       self.secret.get(),
            'dest_dir':     self.dest_dir.get(),
            'local_source': self.local_source.get(),
            'recursive_scan': self.recursive_scan.get(),
            'exclude_dir':   self.exclude_dir.get(),
            'github_token':  self.github_token.get(),
            'parallel':     self.parallel.get(),
            'retries':      self.retries.get(),
            'stuck':        self.stuck.get(),
            'aria2_split':  self.aria2_split.get(),
            'aria2_speed':  self.aria2_speed.get(),
            'mode':         self.mode.get(),
            'verify_mode':  self.verify_mode.get(),
            'urls':         self.url_text.get('1.0', 'end').strip(),
            'url_group':    getattr(self, 'group_var', tk.StringVar()).get(),
            'ra_top_n':         self.ra_top_n.get(),
            'ra_min_players':   self.ra_min_players.get(),
            'ra_filter_mode':   self.ra_filter_mode.get(),
            'ra_system':    self.ra_system.get(),
            'igdb_platform_id':   self.igdb_platform_id.get(),
            'igdb_platform_name': self.igdb_platform_name.get(),
            'igdb_top_n':         self.igdb_top_n.get(),
            'moby_url':           self.moby_url.get(),
            'top_n_source':       self.top_n_source.get(),
            'top_n_max_size_gb':  self.top_n_max_size_gb.get(),
            'moby_top_n':         self.moby_top_n.get(),
            'moby_min_score':     self.moby_min_score.get(),
            'moby_filter_mode':   self.moby_filter_mode.get(),
            'igdb_min_score':     self.igdb_min_score.get(),
            'igdb_filter_mode':   self.igdb_filter_mode.get(),
            'moby_platform_name': getattr(self, 'moby_platform_name', tk.StringVar()).get(),
            'moby_platform_slug': getattr(self, 'moby_platform_slug', tk.StringVar()).get(),
            'ss_platform_id':     self.ss_platform_id.get(),
            'ss_platform_name':   self.ss_platform_name.get(),
            'ss_top_n':           self.ss_top_n.get(),
            'ss_min_rating':      self.ss_min_rating.get(),
            'ss_filter_mode':     self.ss_filter_mode.get(),
            'ss_sort_by':         self.ss_sort_by.get(),
            'ss_genre_filter':    self.ss_genre_filter.get(),
            'ss_english_only':    self.ss_english_only.get(),
            'ss_genres':          self._ss_genres,
            'ss_genre_id_map':    self._ss_genre_id_map,
            'ss_genre_parent_map': self._ss_genre_parent_map,
            'dat_group':      getattr(self, 'dat_group_var', tk.StringVar()).get(),
            'dat_group_urls': self.dat_group_text.get('1.0', 'end').strip()
                              if hasattr(self, 'dat_group_text') else '',
        })

    # ── Setup tab ─────────────────────────────────────────────────────────────

    def _build_setup(self):
        f   = self.tab_setup
        PAD = 16

        title_row = tk.Frame(f, bg=BG)
        title_row.pack(pady=(PAD, 4), fill='x')
        tk.Button(title_row, text='🩺 Health Check', bg=BG3, fg=FG2,
                  font=FONT_SM, relief='flat', padx=8, pady=2,
                  command=self._health_check).pack(side='right', padx=PAD)
        # Centre the title within the row
        centre = tk.Frame(title_row, bg=BG)
        centre.place(relx=0.5, rely=0.5, anchor='center')
        tk.Label(centre, text=APP_NAME, bg=BG, fg=ACC,
                 font=('Consolas', 20, 'bold')).pack(side='left')
        tk.Label(centre, text='  by Shoko 2026', bg=BG, fg=GREEN,
                 font=FONT_SM).pack(side='left', anchor='s', pady=(0, 4))
        tk.Label(f, text=f'1G1R ROM downloader for archive.org  |  {APP_VER}',
                 bg=BG, fg=FG2, font=FONT_SM).pack(pady=(0, PAD))

        # ── Source URLs ───────────────────────────────────────────────────────
        url_frame = tk.LabelFrame(f, text=' Source URLs / Local Dirs ', bg=BG, fg=FG,
                                  font=FONT, padx=PAD, pady=PAD)
        url_frame.pack(fill='x', padx=PAD, pady=4)


        grp_row = tk.Frame(url_frame, bg=BG)
        grp_row.pack(fill='x', pady=(0, 4))
        tk.Label(grp_row, text='Group:', bg=BG, fg=FG2, font=FONT_SM).pack(side='left')
        self.group_var   = tk.StringVar()
        self.group_combo = ttk.Combobox(grp_row, textvariable=self.group_var,
                                        font=FONT_SM, width=24)
        self.group_combo.pack(side='left', padx=4)
        self.group_combo.bind('<<ComboboxSelected>>', self._load_url_group)
        tk.Button(grp_row, text='Save', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._save_url_group).pack(side='left', padx=2)
        tk.Button(grp_row, text='Delete', bg=BG3, fg=RED, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._delete_url_group).pack(side='left', padx=2)
        tk.Button(grp_row, text='New', bg=BG3, fg=GREEN, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._new_url_group).pack(side='left', padx=2)
        self.recursive_scan = tk.BooleanVar(value=self.settings.get('recursive_scan', False))
        tk.Checkbutton(grp_row, text='Recursive', variable=self.recursive_scan,
                       bg=BG, fg=FG2, selectcolor=BG2, activebackground=BG,
                       font=FONT_SM, command=self._save_settings).pack(side='left', padx=(12, 0))

        tk.Label(url_frame, text='One archive.org download URL per line:',
                 bg=BG, fg=FG2, font=FONT_SM).pack(anchor='w')
        self.url_text = tk.Text(url_frame, bg=BG2, fg=FG, font=FONT, height=5,
                                insertbackground=FG, relief='flat', borderwidth=4)
        self.url_text.pack(fill='x', pady=4)

        # DAT import row — removed, handled by mode dropdown below

        # ── Internet Archive S3 Keys (packed below destination by _update_donate) ──
        cred_frame = tk.LabelFrame(f, text=' Internet Archive S3 Keys ', bg=BG, fg=FG,
                                   font=FONT, padx=PAD, pady=PAD)
        self.cred_frame = cred_frame  # saved for show/hide
        # not packed here — shown/hidden dynamically after dirs_row
        row = tk.Frame(cred_frame, bg=BG)
        row.pack(fill='x')
        tk.Label(row, text='Access Key:', bg=BG, fg=FG, font=FONT,
                 width=12, anchor='w').pack(side='left')
        tk.Entry(row, textvariable=self.access, bg=BG2, fg=FG, font=FONT,
                 insertbackground=FG, relief='flat',
                 borderwidth=4).pack(side='left', fill='x', expand=True)
        row2 = tk.Frame(cred_frame, bg=BG)
        row2.pack(fill='x', pady=4)
        tk.Label(row2, text='Secret Key:', bg=BG, fg=FG, font=FONT,
                 width=12, anchor='w').pack(side='left')
        tk.Entry(row2, textvariable=self.secret, bg=BG2, fg=FG, font=FONT,
                 insertbackground=FG, relief='flat', borderwidth=4,
                 show='*').pack(side='left', fill='x', expand=True)
        key_link = tk.Label(cred_frame,
                 text='Get keys at: https://archive.org/account/s3.php',
                 bg=BG, fg=ACC, font=FONT_SM, cursor='hand2')
        key_link.pack(anchor='w')
        key_link.bind('<Button-1>', lambda e: __import__('webbrowser').open(
            'https://archive.org/account/s3.php'))
        tk.Label(cred_frame,
                 text='Keys are optional -- only needed for access-restricted collections.',
                 bg=BG, fg=FG2, font=FONT_SM).pack(anchor='w')

        # ── Destination + Additional Local Source (same row) ─────────────────
        dirs_row = tk.Frame(f, bg=BG)
        dirs_row.pack(fill='x', padx=PAD, pady=4)

        dest_frame = tk.LabelFrame(dirs_row, text=' Destination ', bg=BG, fg=FG,
                                   font=FONT, padx=PAD, pady=PAD)
        dest_frame.pack(side='left', fill='x', expand=True, padx=(0, 4))
        row3 = tk.Frame(dest_frame, bg=BG)
        row3.pack(fill='x')
        tk.Entry(row3, textvariable=self.dest_dir, bg=BG2, fg=FG, font=FONT,
                 insertbackground=FG, relief='flat',
                 borderwidth=4).pack(side='left', fill='x', expand=True, padx=(0, 8))
        tk.Button(row3, text='Browse', bg=BG3, fg=FG, font=FONT,
                  relief='flat', padx=8,
                  command=self._browse_dest).pack(side='left')

        excl_frame = tk.LabelFrame(dirs_row, text=' Exclude Directory (already owned) ', bg=BG, fg='#4a9eff',
                                   font=FONT, padx=PAD, pady=PAD)
        excl_frame.pack(side='left', fill='x', expand=True, padx=(4, 0))
        excl_row = tk.Frame(excl_frame, bg=BG)
        excl_row.pack(fill='x')
        tk.Entry(excl_row, textvariable=self.exclude_dir, bg=BG2, fg=FG, font=FONT,
                 insertbackground=FG, relief='flat',
                 borderwidth=4).pack(side='left', fill='x', expand=True, padx=(0, 8))
        tk.Button(excl_row, text='Browse', bg=BG3, fg=FG, font=FONT,
                  relief='flat', padx=8,
                  command=self._browse_exclude_dir).pack(side='left')

        self._cred_frame_anchor = tk.Frame(f, bg=BG, height=0)  # zero-height anchor
        self._cred_frame_anchor.pack(fill='x')

        # ── Options ──────────────────────────────────────────────────────────────
        opt_frame = tk.LabelFrame(f, text=' Options ', bg=BG, fg=FG,
                                  font=FONT, padx=PAD, pady=PAD)
        opt_frame.pack(fill='x', padx=PAD, pady=4)
        # dat_label needed by _browse_dat for filename display (hidden in setup)
        self.dat_label = tk.Label(opt_frame, text='', bg=BG, fg=GREEN, font=FONT_SM)

        self.btn_analyse = tk.Button(f, text='GoGet!', bg=ACC, fg=FG, font=FONT_LG,
                  relief='flat', padx=20, pady=8,
                  command=self._goget_or_reset)
        self.btn_analyse.pack(pady=PAD)

        self.setup_status = tk.Label(f, text='', bg=BG, fg=FG2, font=FONT_SM)
        self.setup_status.pack()

        self.btn_donate = tk.Button(f, text='', bg=BG, fg=GREEN,
                  font=('Consolas', 24, 'bold'),
                  relief='flat', padx=40, pady=10, cursor='hand2')
        self.btn_donate.pack(pady=(0, 0))
        self.lbl_torrent_warning = tk.Label(f,
                 text='⚠ This app does not seed torrents — please use a proper torrent client to give back to the community.',
                 bg=BG, fg=RED, font=('Consolas', 12, 'bold'), wraplength=700)
        # shown/hidden by _update_donate for Minerva sources only
        def _on_url_change(e):
            self._update_donate()
            self.url_text.edit_modified(False)
        self.url_text.bind('<<Modified>>', _on_url_change)
        self.root.after(0, self._update_donate)  # set initial S3 frame visibility

    # ── Setup tab handlers ────────────────────────────────────────────────────

    def _browse_dest(self):
        d = filedialog.askdirectory(title='Select destination folder')
        if d:
            self.dest_dir.set(d)

    def _browse_local_source(self):
        d = filedialog.askdirectory(title='Select local source folder')
        if d:
            self.local_source.set(d)
            self._local_source_cache = None  # invalidate cache

    def _browse_exclude_dir(self):
        d = filedialog.askdirectory(title='Select exclude directory (already owned ROMs)')
        if d:
            self.exclude_dir.set(d)

    def _safe_after(self, fn):
        """Schedule fn via root.after(0), swallowing RuntimeError from background threads."""
        try:
            self.root.after(0, fn)
        except RuntimeError:
            pass

    def _debug(self, msg: str):
        def _append():
            self.debug_log.insert('end', f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            if getattr(self, 'log_autotail', None) and self.log_autotail.get():
                self.debug_log.see('end')
        self.root.after(0, _append)

    def _new_url_group(self):
        self.group_var.set('')
        self.url_text.delete('1.0', 'end')

    def _refresh_group_combo(self):
        names = sorted(self.url_groups.keys())
        self.group_combo['values'] = names

    def _save_url_group(self):
        name = self.group_var.get().strip()
        if not name:
            name = simpledialog.askstring(
                'Save Group', 'Enter a name for this URL group:',
                parent=self.root)
            if not name or not name.strip():
                return
            name = name.strip()
        urls = self.url_text.get('1.0', 'end').strip()
        if not urls:
            messagebox.showerror('Error', 'No URLs to save.')
            return
        self.url_groups[name] = urls
        self._refresh_group_combo()
        self.group_var.set(name)
        save_groups(self.url_groups)

    def _load_url_group(self, event=None):
        name = self.group_var.get()
        if name and name in self.url_groups:
            self.url_text.delete('1.0', 'end')
            self.url_text.insert('1.0', self.url_groups[name])
            self._update_donate()

    def _delete_url_group(self):
        name = self.group_var.get().strip()
        if not name or name not in self.url_groups:
            return
        if messagebox.askyesno('Delete Group', f'Delete group "{name}"?'):
            self.url_groups.pop(name, None)
            self.group_var.set('')
            self._refresh_group_combo()
            save_groups(self.url_groups)

    # ── URL / DAT analysis ────────────────────────────────────────────────────

    def _browse_dat(self):
        path = filedialog.askopenfilename(
            title='Add local DAT file',
            filetypes=[('DAT files', '*.dat'), ('XML files', '*.xml'), ('All files', '*.*')],
        )
        if not path:
            return
        current = self.dat_group_text.get('1.0', 'end').strip()
        if current:
            self.dat_group_text.insert('end', f'\n{path}')
        else:
            self.dat_group_text.insert('1.0', path)

    def _on_mode_change(self, event=None):
        mode = self.mode.get()
        # Only save when triggered by user interaction, not on programmatic startup call
        if event is not None or hasattr(self, '_init_done'):
            self._save_settings()

        # Show/hide DAT panel
        if hasattr(self, 'dat_group_frame'):
            if mode == 'DAT':
                self.lbl_dat_group_status.pack(anchor='w', before=self._legend_row)
                self.dat_group_frame.pack(fill='x', pady=(0, 4), before=self._legend_row)
            else:
                self.lbl_dat_group_status.pack_forget()
                self.dat_group_frame.pack_forget()

        # Show/hide Top N frame
        if hasattr(self, 'top_n_frame'):
            if mode == 'Top N':
                self.top_n_frame.pack(fill='x', pady=(0, 4), before=self._legend_row)
                self._on_top_n_source_change()
            else:
                self.top_n_frame.pack_forget()

        if not self.raw_file_entries:
            return

        if mode == 'Top N':
            # User must click Fetch & Apply
            return

        if mode == 'DAT':
            # If we have a cached result, apply it immediately
            if self.raw_file_entries and self._dat_group_cache:
                self._apply_dat_group(self._dat_group_cache)
            elif self.raw_file_entries:
                # No cache yet — show all as unselected until user fetches
                result, summary = self._apply_filter(self.raw_file_entries, 'All files')
                for data in result.values():
                    if data['selected']:
                        data['selected'] = None
                summary['selected_titles'] = 0
                self.rom_dict = result
                self.summary  = summary
                self.dat_mode = False
                self._analysis_done()
            return

        if mode == 'None':
            result, summary = self._apply_filter(self.raw_file_entries, 'All files')
            for data in result.values():
                if data['selected']:
                    data['_prev_selected'] = dict(data['selected'])
                    data['selected'] = None
            summary['selected_titles'] = 0
            self.rom_dict = result
            self.summary  = summary
            self.dat_mode = False
            self._analysis_done()
            return
            result, summary = self._apply_filter(self.raw_file_entries, 'All files')
            for data in result.values():
                if data['selected']:
                    data['_prev_selected'] = dict(data['selected'])
                    data['selected'] = None
            summary['selected_titles'] = 0
            self.rom_dict = result
            self.summary  = summary
            self.dat_mode = False
            self._analysis_done()
            return

        self.rom_dict, self.summary = self._apply_filter(self.raw_file_entries, mode)
        self.dat_mode = False
        self._analysis_done()

    # ── DAT Group methods ─────────────────────────────────────────────────────

    def _refresh_dat_group_combo(self):
        names = sorted(self.dat_groups.keys())
        if hasattr(self, 'dat_group_combo'):
            self.dat_group_combo['values'] = names

    def _save_dat_group(self):
        name = self.dat_group_var.get().strip()
        if not name:
            name = simpledialog.askstring('Save DAT Group', 'Enter a name:', parent=self.root)
            if not name or not name.strip():
                return
            name = name.strip()
        urls = self.dat_group_text.get('1.0', 'end').strip()
        if not urls:
            messagebox.showerror('Error', 'No URLs to save.')
            return
        self.dat_groups[name] = urls
        self._refresh_dat_group_combo()
        self.dat_group_var.set(name)
        save_dat_groups(self.dat_groups)

    def _load_dat_group(self, event=None):
        name = self.dat_group_var.get()
        if name and name in self.dat_groups:
            self.dat_group_text.delete('1.0', 'end')
            self.dat_group_text.insert('1.0', self.dat_groups[name])
            self.lbl_dat_group_status.config(text='')

    def _delete_dat_group(self):
        name = self.dat_group_var.get().strip()
        if not name or name not in self.dat_groups:
            return
        if messagebox.askyesno('Delete DAT Group', f'Delete group "{name}"?'):
            self.dat_groups.pop(name, None)
            self.dat_group_var.set('')
            self._refresh_dat_group_combo()
            save_dat_groups(self.dat_groups)

    def _new_dat_group(self):
        self.dat_group_var.set('')
        self.dat_group_text.delete('1.0', 'end')
        self.lbl_dat_group_status.config(text='')

    def _fetch_dat_group(self):
        urls = [u.strip() for u in self.dat_group_text.get('1.0', 'end').splitlines() if u.strip()]
        if not urls:
            messagebox.showerror('Error', 'No DAT URLs entered.')
            return
        if not self.raw_file_entries:
            messagebox.showerror('Error', 'Run GoGet! first to fetch the file list.')
            return
        self.btn_fetch_dat_group.config(state='disabled')
        self.lbl_dat_group_status.config(text=f'Fetching {len(urls)} DAT(s)...', fg=YELLOW)
        self.root.update()

        def _do():
            try:
                merged = {}
                for i, url in enumerate(urls):
                    self._debug(f"Fetching DAT {i+1}/{len(urls)}: {url}")
                    self.root.after(0, lambda i=i: self.lbl_dat_group_status.config(
                        text=f'Fetching {i+1}/{len(urls)}...', fg=YELLOW))
                    # Local file or URL
                    if os.path.isfile(url):
                        with open(url, 'r', encoding='utf-8', errors='replace') as f:
                            xml_data = f.read()
                        self._debug(f"DAT read local: {len(xml_data):,} chars")
                    else:
                        xml_data = _fetch_html_cached(url, {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
                            'Accept': 'text/plain, application/xml, */*',
                        })
                        self._debug(f"DAT fetched: {len(xml_data):,} chars")
                    # Parse — try game, then machine
                    root_el = ET.fromstring(xml_data)
                    games = root_el.findall('.//game')
                    if not games:
                        games = root_el.findall('.//machine')
                    count = 0
                    for game in games:
                        for rom in game.findall('rom'):
                            fname = rom.get('name', '')
                            size  = rom.get('size', '')
                            if fname:
                                key = os.path.splitext(fname)[0].lower()
                                merged[key] = (fname, size)
                                count += 1
                    self._debug(f"DAT parsed: {count} entries")

                self._dat_group_cache = merged
                self._debug(f"DAT Group total: {len(merged)} entries")
                self.root.after(0, lambda: self._apply_dat_group(merged))
            except Exception:
                import traceback
                tb = traceback.format_exc()
                self._debug(f"DAT Group fetch error:\n{tb}")
                self.root.after(0, lambda: self.lbl_dat_group_status.config(
                    text='Fetch failed — see debug log', fg=RED))
                self.root.after(0, lambda: self.btn_fetch_dat_group.config(state='normal'))

        threading.Thread(target=_do, daemon=True).start()

    def _apply_dat_group(self, merged: dict):
        """Apply merged DAT group — identical logic to _apply_dat_mode."""
        # merged = {stripped_key_lower: (fname, size_str)}
        SKIP_EXTS = {'.bin', '.sub', '.img', '.wav'}
        # Filter track files from DAT — they're packaged inside archives on archive.org
        merged = {k: v for k, v in merged.items()
                  if os.path.splitext(v[0])[1].lower() not in SKIP_EXTS}
        fetched_by_key = {}
        for entry in self.raw_file_entries:
            key = _cnorm(os.path.splitext(entry[0])[0])
            fetched_by_key[key] = entry
        # Also rebuild merged with _cnorm keys
        merged = {_cnorm(k): v for k, v in merged.items()}

        result      = {}
        found_count = 0
        miss_count  = 0

        # All fetched files — green if in DAT, grey if not
        for key, entry in fetched_by_key.items():
            fname    = entry[0]
            size_str = entry[1]
            url      = entry[2] if len(entry) > 2 else None
            in_dat   = key in merged
            if in_dat:
                result[fname] = {
                    'selected':       {'filename': fname, 'size': size_str, 'direct_url': url},
                    'non_english':    False,
                    'instances':      [],
                    '_dat_missing':   False,
                }
                found_count += 1
            else:
                result[fname] = {
                    'selected':       None,
                    'non_english':    False,
                    'instances':      [],
                    '_dat_missing':   False,
                    '_dat_unselected': True,
                }

        # DAT entries missing from fetch — show as red ✗
        for key, (dat_fname, dat_size) in merged.items():
            if key not in fetched_by_key:
                miss_count += 1
                result[f'__missing__{dat_fname}'] = {
                    'selected':     None,
                    'non_english':  False,
                    'instances':    [],
                    '_dat_missing': True,
                    '_dat_fname':   dat_fname,
                    '_dat_size':    dat_size,
                }

        self.rom_dict = result
        self.dat_mode = True
        self._analysis_done()
        self.lbl_dat_group_status.config(
            text=f'{len(merged)} entries — {found_count} matched, {miss_count} missing',
            fg=GREEN)
        self.btn_fetch_dat_group.config(state='normal')

    def _fetch_ra_top(self):
        if not self.raw_file_entries:
            messagebox.showerror('Error', 'Run GoGet! first to fetch the file list.')
            return
        display = self.ra_system.get()
        if not display or display not in RA_SYSTEM_DISPLAY:
            display = RA_SYSTEM_DISPLAY[0] if RA_SYSTEM_DISPLAY else ''
            self.ra_system.set(display)
        if not display:
            messagebox.showerror('Error', 'Please select a console.')
            return

        self.btn_fetch_top_n.config(state='disabled')
        self.lbl_top_n_status.config(text='Fetching RA data...', fg=YELLOW)
        self.root.update()

        # Snapshot IntVar on main thread before handing off to worker
        _top_n_snapshot      = max(1, self.ra_top_n.get())
        _ra_filter_mode      = self.ra_filter_mode.get()
        _ra_min_players      = self.ra_min_players.get()
        _max_size_bytes      = self.top_n_max_size_gb.get() * 1024**3

        # Source Google Sheet — direct export (sheet must be publicly shared)
        SHEET_ID  = '1Pc8uRu6ovS6n2u8XxHeUaBchEnev7HBLmduv56MsdiY'
        GID       = '463627683'
        CSV_URL   = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}'

        def _normalize(s):
            # Normalize special chars first
            s = s.lower()
            for a, b in [('ä','a'),('ö','o'),('ü','u'),('ë','e'),('ï','i'),
                         ('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),
                         ('à','a'),('è','e'),('ì','i'),('ò','o'),('ù','u'),
                         ('â','a'),('ê','e'),('î','i'),('ô','o'),('û','u'),
                         ('ñ','n'),('ç','c')]:
                s = s.replace(a, b)
            return re.sub(r'[^a-z0-9]', '', s)

        def _do():
            try:
                self._debug(f"Fetching RA sheet: {CSV_URL}")
                csv_data = _fetch_html_cached(CSV_URL, {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'
                })
                self._debug(f"Sheet fetched: {len(csv_data):,} chars")

                # Parse CSV
                import csv, io
                reader = csv.DictReader(io.StringIO(csv_data))
                rows = list(reader)
                cols = list(rows[0].keys()) if rows else []
                self._debug(f"Sheet rows: {len(rows)}, columns: {cols}")
                # Detect column name variants (source sheet may differ from copy)
                def _col(row, *names):
                    for n in names:
                        if n in row: return row[n]
                    return ""

                # Filter by console — exact match against sheet Console column
                console_name = display  # display IS the exact sheet console name
                self._debug(f"RA console: {console_name!r}")
                matched_rows = []
                for row in rows:
                    if _col(row, 'Console', 'System', 'Platform').strip() == console_name:
                        try:
                            players = int(str(_col(row, 'Total Players', 'Players', 'NumPlayers')
                                          ).replace(',', '').strip() or '0')
                        except ValueError:
                            players = 0
                        title = _col(row, 'Title', 'Game', 'Name').strip()
                        if title:
                            matched_rows.append((players, title))
                self._debug(f"RA matched {len(matched_rows)} rows")

                if not matched_rows:
                    self.root.after(0, lambda: self.lbl_top_n_status.config(
                        text=f'No data for {display}', fg=RED))
                    self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))
                    return

                # Remove rows with [...] or ~Hack~/~Homebrew~ etc in title
                matched_rows = [(p, t) for p, t in matched_rows
                                if '[' not in t and not t.startswith('~')]
                matched_rows.sort(key=lambda x: x[0], reverse=True)
                if _ra_filter_mode == 'min_players':
                    top100 = [title for players, title in matched_rows
                              if players >= _ra_min_players]
                    self._debug(f"Min {_ra_min_players} players for {console_name}: {len(top100)} titles")
                elif _ra_filter_mode == 'max_size':
                    top100 = [title for _, title in matched_rows]
                    self._debug(f"Max size mode — using all {len(top100)} titles for {console_name}")
                else:
                    top_n  = _top_n_snapshot
                    top100 = [title for _, title in matched_rows[:top_n]]
                    self._debug(f"Top {top_n} for {console_name}: #1 {top100[0]} ({matched_rows[0][0]} players)")

                # Use English-capable entries as candidates
                english_entries = []
                for e in self.raw_file_entries:
                    parsed = parse_rom_filename(e[0])
                    countries = parsed['countries']
                    languages = parsed['languages']
                    # Include if: English country, has En language tag, or no region info
                    if (countries & ENGLISH_COUNTRIES
                            or 'En' in languages
                            or not countries):
                        english_entries.append(e)
                ra_groups = {t: [] for t in top100}

                # --- v0.11 exact matching (kept for reference) ---
                # ra_normalized = {}
                # for t in top100:
                #     for part in t.split('|'):
                #         part = part.strip()
                #         if not part:
                #             continue
                #         ra_normalized[_normalize(part)] = t
                #         if ' - ' in part:
                #             suffix = part.split(' - ', 1)[1].strip()
                #             ra_normalized[_normalize(suffix)] = t
                # for entry in english_entries:
                #     fname = entry[0]
                #     base  = os.path.splitext(fname)[0]
                #     bare  = re.sub(r'\s*\([^)]*\)', '', base).strip()
                #     bare  = re.sub(r'\s*(Disc|Disk)\s*\d+', '', bare, flags=re.IGNORECASE).strip()
                #     norm  = _normalize(bare)
                #     norm_no_prefix = _normalize(bare.split(' - ', 1)[-1]) if ' - ' in bare else None
                #     for ra_norm, ra_title in ra_normalized.items():
                #         if norm == ra_norm or (norm_no_prefix and norm_no_prefix == ra_norm):
                #             ra_groups[ra_title].append(entry)
                #             break

                # --- v0.12 layered fuzzy matching ---
                try:
                    from rapidfuzz.distance import Indel
                    def _fuzzy(a, b): return Indel.normalized_similarity(a, b)
                except ImportError:
                    from difflib import SequenceMatcher
                    def _fuzzy(a, b): return SequenceMatcher(None, a, b).ratio()
                    self._debug('[WARNING] rapidfuzz not installed — matching will be very slow. Run: pip install rapidfuzz')

                # Build flat list of (ra_norm, ra_title)
                ra_norm_list = []
                for t in top100:
                    for part in t.split('|'):
                        part = part.strip()
                        if part:
                            ra_norm_list.append((_normalize(part), t))
                            # Also index by first colon-separated part (e.g. "Pepsiman" from "Pepsiman: The Running Hero")
                            if ':' in part:
                                prefix = part.split(':')[0].strip()
                                if len(prefix) > 4:  # avoid matching very short prefixes
                                    ra_norm_list.append((_normalize(prefix), t))

                # Non-English fallback pool for titles with no English version
                nonenglish_entries = [e for e in self.raw_file_entries if e not in english_entries]

                THRESHOLDS = [1.0, 0.90, 0.85, 0.80, 0.75, 0.70]

                # Build token index using pre-normalized word tokens
                # _normalize strips all punctuation so we tokenize BEFORE normalizing
                def _norm_roman_ra(s):
                    s = s.lower()
                    for roman, arabic in [('viii','8'),('vii','7'),('vi','6'),('ix','9'),
                                          ('iv','4'),('iii','3'),('ii','2'),('xi','11'),
                                          ('xii','12'),('xiii','13'),('xiv','14'),('xv','15'),
                                          ('xvi','16'),('xvii','17'),('xviii','18'),('xix','19'),
                                          ('xx','20'),('x','10')]:
                        s = re.sub(r'(?<![a-z0-9])' + roman + r'(?![a-z0-9])', arabic, s)
                    return s
                def _word_tokens(s):
                    s = _norm_roman_ra(s)
                    words = re.sub(r'[^a-zA-Z0-9]', ' ', s).split()
                    return {w for w in words if len(w) >= 3 or (w.isdigit() and len(w) >= 2)} - _STOPWORDS_C

                def _ra_word_tokens(ra_norm):
                    # ra_norm is already fully normalized (no spaces), re-split by
                    # checking the original ra_title stored alongside it
                    return set()  # handled below via ra_title

                # Build RA-side token index (small list, indexed once)
                # Then query per ROM to get only relevant candidates
                from collections import defaultdict as _dd
                _ra_tok_idx = _dd(list)  # word -> [(ra_norm, ra_title)]
                for ra_norm, ra_title in ra_norm_list:
                    ra_bare = ra_title.split('|')[0].strip()
                    for tok in _word_tokens(ra_bare):
                        _ra_tok_idx[tok].append((ra_norm, ra_title))

                import time as _time
                _t0 = _time.time()
                _total_cands = 0
                entry_matches = []
                _total_en = len(english_entries)
                for _i, entry in enumerate(english_entries):
                    self.root.after(0, lambda i=_i, t=_total_en: self.lbl_top_n_status.config(
                        text=f'Matching ROMs... {i:,}/{t:,}', fg=YELLOW))
                    fname = entry[0]
                    base  = os.path.splitext(fname)[0]
                    bare  = re.sub(r'\s*\([^)]*\)', '', base).strip()
                    bare  = re.sub(r'\s*(Disc|Disk)\s*\d+', '', bare, flags=re.IGNORECASE).strip()
                    norm  = _normalize(bare)
                    toks  = _word_tokens(bare)
                    candidates = {}
                    for tok in toks:
                        for item in _ra_tok_idx.get(tok, []):
                            candidates[item] = None
                    if not candidates:
                        entry_matches.append((0.0, None, entry))
                        continue
                    _total_cands += len(candidates)
                    best_score, best_title = 0.0, None
                    for ra_norm, ra_title in candidates:
                        score = _fuzzy(norm, ra_norm)
                        if score > best_score:
                            best_score, best_title = score, ra_title
                    entry_matches.append((best_score, best_title, entry))

                # Layer: accept matches at descending thresholds
                matched_titles = set()
                for threshold in THRESHOLDS:
                    for best_score, best_title, entry in entry_matches:
                        if best_title and best_score >= threshold and best_title not in matched_titles:
                            ra_groups[best_title].append(entry)
                    for t in top100:
                        if ra_groups[t]:
                            matched_titles.add(t)
                    self._debug(f"RA threshold {threshold:.2f}: {len(matched_titles)} titles matched")

                # Non-English fallback — for still-unmatched RA titles only
                still_unmatched = set(t for t in top100 if not ra_groups[t])
                if still_unmatched and nonenglish_entries:
                    # RA-side index filtered to still_unmatched titles only
                    _ne_ra_tok_idx = _dd(list)
                    for ra_norm, ra_title in ra_norm_list:
                        if ra_title not in still_unmatched:
                            continue
                        ra_bare = ra_title.split('|')[0].strip()
                        for tok in _word_tokens(ra_bare):
                            _ne_ra_tok_idx[tok].append((ra_norm, ra_title))
                    nonenglish_matches = []
                    for entry in nonenglish_entries:
                        fname = entry[0]
                        base  = os.path.splitext(fname)[0]
                        bare  = re.sub(r'\s*\([^)]*\)', '', base).strip()
                        bare  = re.sub(r'\s*(Disc|Disk)\s*\d+', '', bare, flags=re.IGNORECASE).strip()
                        norm  = _normalize(bare)
                        toks  = _word_tokens(bare)
                        candidates = {}
                        for tok in toks:
                            for item in _ne_ra_tok_idx.get(tok, []):
                                candidates[item] = None
                        if not candidates:
                            nonenglish_matches.append((0.0, None, entry))
                            continue
                        best_score, best_title = 0.0, None
                        for ra_norm, ra_title in candidates:
                            score = _fuzzy(norm, ra_norm)
                            if score > best_score:
                                best_score, best_title = score, ra_title
                        nonenglish_matches.append((best_score, best_title, entry))

                    for threshold in [1.0, 0.90, 0.85, 0.80, 0.75, 0.70]:
                        for best_score, best_title, entry in nonenglish_matches:
                            if best_title and best_score >= threshold and not ra_groups[best_title]:
                                ra_groups[best_title].append(entry)
                        self._debug(f"RA non-English fallback {threshold:.2f}: {len([t for t in top100 if ra_groups[t]])} titles matched")

                unmatched_ra = [t for t in top100 if not ra_groups[t]]
                for i, t in enumerate(sorted(top100), 1):
                    self._debug(f"  #{i:3d}: {t}")
                self._debug(f"RA unmatched ({len(unmatched_ra)}): {sorted(unmatched_ra)}")

                # For each RA title group, apply 1G1R to pick best variant
                # and select ALL discs of that variant
                selected_fnames = set()
                _accum_bytes    = 0
                _fnames_before  = set()
                for ra_title, entries in ra_groups.items():
                    if not entries:
                        continue
                    # Group entries by variant (keep region, only strip disc number)
                    variant_groups = {}
                    for entry in entries:
                        fname  = entry[0]
                        parsed = parse_rom_filename(fname)
                        inst   = {
                            'filename':   fname,
                            'size':       entry[1],
                            'direct_url': entry[2] if len(entry) > 2 else None,
                            'countries':  parsed['countries'],
                            'languages':  parsed['languages'],
                            'attributes': parsed['attributes'],
                        }
                        # Strip only disc parentheses, keep region/language tags
                        key = re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '', os.path.splitext(fname)[0], flags=re.IGNORECASE).strip()
                        variant_groups.setdefault(key, []).append(inst)

                    # Use disc 1 (or first) as representative for select_best
                    representatives = []
                    for key, insts in variant_groups.items():
                        rep = next((i for i in insts if re.search(r'Disc\s*1', i['filename'], re.IGNORECASE)), insts[0])
                        rep['_variant_key'] = key
                        representatives.append(rep)

                    # Filter excluded but fall back if all excluded
                    filtered = [i for i in representatives if not is_excluded(i)]
                    if not filtered:
                        filtered = representatives
                    best = select_best(filtered)
                    if not best:
                        continue

                    # Select ALL discs of the winning variant
                    best_key = best.get('_variant_key') or re.sub(
                        r'\s*\(Disc\s*\d+[^)]*\)', '', os.path.splitext(best['filename'])[0], flags=re.IGNORECASE).strip()
                    all_discs = variant_groups.get(best_key, [best])
                    if _ra_filter_mode == 'max_size':
                        added_bytes = sum(parse_size_bytes(i.get('size', '0')) for i in all_discs)
                        if _accum_bytes + added_bytes > _max_size_bytes:
                            for inst in all_discs:
                                sz = parse_size_bytes(inst.get('size', '0'))
                                self._debug(f"  [RA] OVER LIMIT: {inst['filename']}  {inst.get('size','?')} ({sz:,} B)  would be={format_size(_accum_bytes + added_bytes)}")
                            break
                        _accum_bytes += added_bytes
                    for inst in all_discs:
                        selected_fnames.add(inst['filename'])
                        sz = parse_size_bytes(inst.get('size', '0'))
                        self._debug(f"  [RA] {inst['filename']}  {inst.get('size','?')} ({sz:,} B)  running={format_size(_accum_bytes)}")

                self._debug(f"RA 1G1R: {len(selected_fnames)} files from {len([t for t,e in ra_groups.items() if e])} titles selected")

                # Get All files result as base structure, then select only RA winners
                result, summary = self._apply_filter(self.raw_file_entries, 'All files')
                for title, data in result.items():
                    if data['selected']:
                        fname = data['selected']['filename']
                        if fname not in selected_fnames:
                            data['selected'] = None
                result_fnames = {d['selected']['filename'] for d in result.values() if d['selected']}
                for entry in self.raw_file_entries:
                    if entry[0] in selected_fnames and entry[0] not in result_fnames:
                        result[entry[0]] = {'selected': {'filename': entry[0], 'size': entry[1], 'direct_url': entry[2] if len(entry) > 2 else None}, 'non_english': False, 'instances': []}

                matched_titles = len([t for t, e in ra_groups.items() if e])
                for mt in top100:
                    entries = ra_groups.get(mt, [])
                    if entries and not any(e[0] in selected_fnames for e in entries):
                        result[f'__missing__{mt}'] = {
                            'selected':     None,
                            'non_english':  False,
                            'instances':    [],
                            '_dat_missing': True,
                            '_dat_fname':   mt,
                            '_dat_size':    '',
                        }
                self.rom_dict    = result
                self.summary     = summary
                self.dat_mode    = True
                self._top_n_mode = True
                self.root.after(0, self._analysis_done)
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text=f'Top {top_n} — {matched_titles} titles ({len(selected_fnames)} ROMs) from {len(matched_rows)} {console_name} games',
                    fg=GREEN))
                self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))

            except Exception:
                import traceback
                tb = traceback.format_exc()
                self._debug(f"RA fetch error:\n{tb}")
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Fetch failed — see debug log', fg=RED))
                self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))

        threading.Thread(target=_do, daemon=True).start()

    def _igdb_get_token(self) -> str:
        """Fetch or return cached OAuth2 token for IGDB."""
        if self._igdb_token:
            return self._igdb_token
        url = (f'https://id.twitch.tv/oauth2/token'
               f'?client_id=p66yhx7xnqs08602qb4bxn0az5xa23'
               f'&client_secret=glxj73ulac8yqxgzeuiadwx6zfvi8s'
               f'&grant_type=client_credentials')
        req = urllib.request.Request(url, method='POST')
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        self._igdb_token = data['access_token']
        self._debug(f"IGDB token obtained (expires in {data.get('expires_in', '?')}s)")
        return self._igdb_token

    def _igdb_post(self, endpoint: str, body: str) -> list:
        """POST to IGDB API and return parsed JSON list."""
        token = self._igdb_get_token()
        req = urllib.request.Request(
            f'https://api.igdb.com/v4/{endpoint}',
            data=body.encode('utf-8'),
            headers={
                'Client-ID':     'p66yhx7xnqs08602qb4bxn0az5xa23',
                'Authorization': f'Bearer {token}',
                'Accept':        'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def _fetch_igdb_platforms(self):
        """Fetch platform list from IGDB and populate combo."""
        def _do():
            try:
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Loading platforms...', fg=YELLOW))
                # Fetch all platforms in batches
                platforms = []
                offset = 0
                while True:
                    batch = self._igdb_post('platforms',
                        f'fields id,name; limit 500; offset {offset}; sort name asc;')
                    if not batch:
                        break
                    platforms.extend(batch)
                    if len(batch) < 500:
                        break
                    offset += 500
                platforms.sort(key=lambda p: p.get('name', ''))
                self._igdb_platforms = [(p['id'], p['name']) for p in platforms]
                names = [n for _, n in self._igdb_platforms]
                self._debug(f"IGDB: {len(platforms)} platforms loaded")
                def _update():
                    self._igdb_platform_names = names
                    # Restore saved selection if valid
                    saved = self.igdb_platform_name.get()
                    if saved in names:
                        self.igdb_platform_name.set(saved)
                    elif names:
                        self.igdb_platform_name.set(names[0])
                        self._on_igdb_platform_select()
                    self.lbl_top_n_status.config(
                        text=f'{len(platforms)} platforms loaded', fg=GREEN)
                self.root.after(0, _update)
            except Exception:
                import traceback
                self._debug(f"IGDB platform fetch error:\n{traceback.format_exc()}")
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Failed to load platforms — see debug log', fg=RED))
        threading.Thread(target=_do, daemon=True).start()

    def _on_igdb_platform_select(self, event=None):
        """Update igdb_platform_id when user selects a platform."""
        name = self.igdb_platform_name.get()
        for pid, pname in self._igdb_platforms:
            if pname == name:
                self.igdb_platform_id.set(pid)
                self._save_settings()
                return

    def _fetch_igdb_top(self):
        """Fetch top N games from IGDB by rating for selected platform, apply 1G1R."""
        if not self.raw_file_entries:
            messagebox.showerror('Error', 'Run GoGet! first to fetch the file list.')
            return
        platform_id = self.igdb_platform_id.get()
        if not platform_id:
            messagebox.showerror('Error',
                'Select a platform first.\nClick ↺ to load the platform list.')
            return

        self.btn_fetch_top_n.config(state='disabled')
        self.lbl_top_n_status.config(text='Fetching IGDB data...', fg=YELLOW)
        self.root.update()

        _filter_mode    = self.igdb_filter_mode.get()
        _top_n          = max(1, self.igdb_top_n.get())
        _min_score      = self.igdb_min_score.get()
        _max_size_bytes = self.top_n_max_size_gb.get() * 1024**3

        def _normalize(s):
            s = s.lower()
            for a, b in [('ä','a'),('ö','o'),('ü','u'),('ë','e'),('ï','i'),
                         ('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),
                         ('à','a'),('è','e'),('ì','i'),('ò','o'),('ù','u'),
                         ('â','a'),('ê','e'),('î','i'),('ô','o'),('û','u'),
                         ('ñ','n'),('ç','c')]:
                s = s.replace(a, b)
            return re.sub(r'[^a-z0-9]', '', s)

        def _fuzzy(a, b):
            if a == b: return 1.0
            if not a or not b: return 0.0
            la, lb = len(a), len(b)
            if la > lb: a, b, la, lb = b, a, lb, la
            if la == 0: return 0.0
            if b.startswith(a): return la / lb
            matches = sum(ca == cb for ca, cb in zip(a, b))
            return matches / lb

        def _do():
            try:
                # Fetch games sorted by follows (popularity) — much wider coverage
                # than total_rating which IGDB only has for well-reviewed games.
                titles = []
                offset = 0
                per_page = 500
                while True:
                    self.root.after(0, lambda t=len(titles):
                        self.lbl_top_n_status.config(
                            text=f'Fetching... ({t} titles so far)', fg=YELLOW))
                    body = (f'fields name,aggregated_rating;'
                            f' where platforms = ({platform_id})'
                            f' & aggregated_rating != null;'
                            f' sort aggregated_rating desc;'
                            f' limit {per_page}; offset {offset};')
                    batch = self._igdb_post('games', body)
                    self._debug(f"IGDB batch offset={offset}: {len(batch)} games (platform_id={platform_id})")
                    if not batch:
                        break
                    stop_early = False
                    for g in batch:
                        if _filter_mode == 'min_score':
                            if g.get('aggregated_rating', 0) < _min_score:
                                stop_early = True
                                break
                        titles.append(g['name'])
                        if _filter_mode == 'top_n' and len(titles) >= _top_n:
                            stop_early = True
                            break
                    if stop_early or len(batch) < per_page:
                        break
                    offset += per_page

                if _filter_mode != 'max_size':
                    titles = titles[:_top_n]
                if not titles:
                    self.root.after(0, lambda: self.lbl_top_n_status.config(
                        text='No titles found for this platform', fg=RED))
                    self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))
                    return
                self._debug(f"IGDB top {_top_n}: #1={titles[0]!r} #{len(titles)}={titles[-1]!r}")

                # ── Matching: same Jaccard+fuzzy approach as Moby ────────────────
                from difflib import SequenceMatcher as _SM

                _EDITION_RE_IGDB = re.compile(
                    r'\b(limited edition|collector\'s edition|collectors edition|'
                    r'game of the year edition|goty edition|complete edition|'
                    r'definitive edition|enhanced edition|ultimate edition|'
                    r'platinum edition|director\'s cut|directors cut|'
                    r'deluxe edition|remastered edition|anniversary edition|'
                    r'expanded edition|extended edition|bundle edition|'
                    r'digital edition|digital deluxe edition)\b', re.IGNORECASE)

                _DIACRITICS_IGDB = [
                    ('ä','a'),('ë','e'),('ï','i'),('ö','o'),('ü','u'),
                    ('Ä','a'),('Ë','e'),('Ï','i'),('Ö','o'),('Ü','u'),
                    ('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ý','y'),
                    ('Á','a'),('É','e'),('Í','i'),('Ó','o'),('Ú','u'),('Ý','y'),
                    ('à','a'),('è','e'),('ì','i'),('ò','o'),('ù','u'),
                    ('â','a'),('ê','e'),('î','i'),('ô','o'),('û','u'),
                    ('ā','a'),('ē','e'),('ī','i'),('ō','oo'),('ū','uu'),
                    ('Ā','a'),('Ē','e'),('Ī','i'),('Ō','oo'),('Ū','uu'),
                    ('ñ','n'),('ç','c'),('š','s'),('ž','z'),('č','c'),
                    ('¹','1'),('²','2'),('³','3'),('⁴','4'),('⁵','5'),
                ]

                def _igdb_deaccent(s):
                    for a, b in [('ō','oo'),('Ō','oo'),('ū','uu'),('Ū','uu'),
                                 ('ā','a'),('Ā','a'),('ē','e'),('Ē','e'),
                                 ('ī','i'),('Ī','i')]:
                        s = s.replace(a, b)
                    import unicodedata as _ud
                    s = _ud.normalize('NFKD', s)
                    s = ''.join(c for c in s if not _ud.combining(c))
                    return s.lower()

                def _igdb_strip(s):
                    s = _EDITION_RE_IGDB.sub('', s)
                    s = re.sub(r'[\-:]\s*(the|a|an)\s*$', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'[\s\-:]+$', '', s)
                    return re.sub(r'\s{2,}', ' ', s).strip()

                def _igdb_tokenize(s):
                    s = _igdb_deaccent(_igdb_strip(s))
                    s = re.sub(r'[:\-\u00b7\u2013\u2014,\'\"()!]', ' ', s)
                    # Keep all tokens including single letters (X, Y matter for Pokemon X/Y)
                    return set(re.findall(r'[a-z0-9]+', s))

                def _igdb_norm_str(s):
                    return re.sub(r'[^a-z0-9]', '', _igdb_deaccent(_igdb_strip(s)))

                _STOPWORDS_IGDB = {'a','an','the','of','in','on','at','to','for','and','or'}

                def _igdb_score(a, b):
                    ta, tb = _igdb_tokenize(a), _igdb_tokenize(b)
                    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
                    na, nb  = _igdb_norm_str(a), _igdb_norm_str(b)
                    fuzzy   = _SM(None, na, nb).ratio() if na and nb else 0.0
                    base    = 0.5 * jaccard + 0.5 * fuzzy
                    ca, cb  = ta - _STOPWORDS_IGDB, tb - _STOPWORDS_IGDB
                    if ca and cb:
                        shorter, longer = (ca,cb) if len(ca)<=len(cb) else (cb,ca)
                        if shorter <= longer:
                            tok = next(iter(shorter)) if len(shorter)==1 else None
                            if len(shorter) >= 2 or (tok and len(tok) >= 2):
                                # Only boost if compat doesn't have far more unique tokens than ROM
                                # prevents e.g. "Söldner-X 2: Final Prototype" boosting for "Prototype 2"
                                if len(cb - ca) <= len(ca):
                                    return max(base, 0.5 + 0.5*(len(shorter)/len(longer)))
                    return base

                # Strip editions from IGDB titles for symmetric matching
                titles = list(dict.fromkeys(_igdb_strip(t) for t in titles))
                titles = [t for t in titles if t]

                english_entries, nonenglish_entries = [], []
                for e in self.raw_file_entries:
                    parsed = parse_rom_filename(e[0])
                    if (parsed['countries'] & ENGLISH_COUNTRIES
                            or 'En' in parsed['languages']
                            or not parsed['countries']):
                        english_entries.append(e)
                    else:
                        nonenglish_entries.append(e)

                igdb_groups = {t: [] for t in titles}



                def _norm_roman(s):
                    s = s.lower()
                    for roman, arabic in [('viii','8'),('vii','7'),('vi','6'),('ix','9'),
                                          ('iv','4'),('iii','3'),('ii','2'),('xi','11'),
                                          ('xii','12'),('xiii','13'),('xiv','14'),('xv','15'),
                                          ('xvi','16'),('xvii','17'),('xviii','18'),('xix','19'),
                                          ('xx','20'),('x','10')]:
                        s = re.sub(r'(?<![a-z0-9])' + roman + r'(?![a-z0-9])', arabic, s)
                    return s

                def _build_title_index(title_list):
                    """Build token->titles index for fast candidate lookup."""
                    from collections import defaultdict as _dd
                    idx = _dd(list)
                    for t in title_list:
                        words = re.sub(r'[^a-zA-Z0-9]', ' ', _norm_roman(t)).split()
                        for w in words:
                            if w.isdigit() and len(w) < 2: continue  # skip single digits
                            if (len(w) >= 3 or (w.isdigit() and len(w) >= 2)) and w not in _STOPWORDS_IGDB:
                                idx[w].append(t)
                    return idx

                def _candidates(bare, idx, title_list):
                    words = re.sub(r'[^a-zA-Z0-9]', ' ', _norm_roman(bare)).split()
                    found = {}
                    for w in words:
                        if w.isdigit() and len(w) < 2: continue  # skip single digits
                        if len(w) >= 3 or (w.isdigit() and len(w) >= 2):
                            for t in idx.get(w, []):
                                found[t] = None
                    if not found:
                        return title_list
                    return list(found.keys())

                def _match_entries(entries, title_list=None):
                    if title_list is None: title_list = titles
                    idx = _build_title_index(title_list)
                    scored = []
                    _total = len(entries)
                    for _i, entry in enumerate(entries):
                        self.root.after(0, lambda i=_i, t=_total: self.lbl_top_n_status.config(
                            text=f'Matching ROMs... {i:,}/{t:,}', fg=YELLOW))
                        base_n = os.path.splitext(entry[0])[0]
                        bare   = re.sub(r'\s*\([^)]*\)', '', base_n).strip()
                        bare   = re.sub(r'\s*(Disc|Disk)\s*\d+', '', bare, flags=re.IGNORECASE).strip()
                        best_score, best_title = 0, None
                        for mt in _candidates(bare, idx, title_list):
                            s = _igdb_score(bare, mt)
                            if s > best_score:
                                best_score, best_title = s, mt
                        scored.append((best_score, best_title, entry))
                    return scored

                THRESHOLD = 0.50
                matched_titles = set()
                for score, title, entry in _match_entries(english_entries):
                    if title and score >= THRESHOLD:
                        igdb_groups[title].append(entry)
                        matched_titles.add(title)
                self._debug(f"IGDB matched: {len(matched_titles)}")

                still_unmatched = [t for t in titles if not igdb_groups[t]]
                if still_unmatched and nonenglish_entries:
                    ne_only = still_unmatched
                    for score, title, entry in _match_entries(nonenglish_entries):
                        if title and title in ne_only and score >= THRESHOLD and not igdb_groups[title]:
                            igdb_groups[title].append(entry)

                unmatched = [t for t in titles if not igdb_groups[t]]
                self._debug(f"IGDB unmatched ({len(unmatched)}): {sorted(unmatched)[:20]!r}")

                selected_fnames  = set()
                _accum_bytes     = 0
                _fnames_before   = set()
                for gt, entries in igdb_groups.items():
                    if not entries:
                        continue
                    variant_groups = {}
                    for entry in entries:
                        parsed = parse_rom_filename(entry[0])
                        inst = {
                            'filename':   entry[0],
                            'size':       entry[1],
                            'direct_url': entry[2] if len(entry) > 2 else None,
                            'countries':  parsed['countries'],
                            'languages':  parsed['languages'],
                            'attributes': parsed['attributes'],
                        }
                        # Key = bare title only (strip all parens) for grouping variants
                        key = re.sub(r'\s*\([^)]*\)', '', os.path.splitext(entry[0])[0]).strip()
                        variant_groups.setdefault(key, []).append(inst)
                    # Pick one representative per variant group, run select_best
                    all_insts = [i for insts in variant_groups.values() for i in insts]
                    filtered = [i for i in all_insts if not is_excluded(i)]
                    if not filtered:
                        filtered = all_insts
                    best = select_best(filtered)
                    if not best:
                        continue
                    best_key = re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                      os.path.splitext(best['filename'])[0],
                                      flags=re.IGNORECASE).strip()
                    winning_discs = [i for i in all_insts
                                     if re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                               os.path.splitext(i['filename'])[0],
                                               flags=re.IGNORECASE).strip() == best_key]
                    if _filter_mode == 'max_size':
                        added_bytes = sum(parse_size_bytes(i.get('size', '0')) for i in winning_discs)
                        if _accum_bytes + added_bytes > _max_size_bytes:
                            for inst in winning_discs:
                                sz = parse_size_bytes(inst.get('size', '0'))
                                self._debug(f"  [IGDB] OVER LIMIT: {inst['filename']}  {inst.get('size','?')} ({sz:,} B)  would be={format_size(_accum_bytes + added_bytes)}")
                            break
                        _accum_bytes += added_bytes
                    for inst in winning_discs:
                        selected_fnames.add(inst['filename'])
                        sz = parse_size_bytes(inst.get('size', '0'))
                        self._debug(f"  [IGDB] {inst['filename']}  {inst.get('size','?')} ({sz:,} B)  running={format_size(_accum_bytes)}")

                self._debug(f"IGDB 1G1R: {len(selected_fnames)} files selected")

                result, summary = self._apply_filter(self.raw_file_entries, 'All files')
                for title, data in result.items():
                    if data['selected']:
                        if data['selected']['filename'] not in selected_fnames:
                            data['selected'] = None
                result_fnames = {d['selected']['filename'] for d in result.values() if d['selected']}
                for entry in self.raw_file_entries:
                    if entry[0] in selected_fnames and entry[0] not in result_fnames:
                        result[entry[0]] = {'selected': {'filename': entry[0], 'size': entry[1], 'direct_url': entry[2] if len(entry) > 2 else None}, 'non_english': False, 'instances': []}
                for mt in titles:
                    entries = igdb_groups.get(mt, [])
                    if entries and not any(e[0] in selected_fnames for e in entries):
                        result[f'__missing__{mt}'] = {
                            'selected': None, 'non_english': False,
                            'instances': [], '_dat_missing': True,
                            '_dat_fname': mt, '_dat_size': '',
                        }
                self.rom_dict    = result
                self.summary     = summary
                self.dat_mode    = True
                self._top_n_mode = True
                self.root.after(0, self._analysis_done)
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text=f'{len(selected_fnames)} ROMs from top {len(titles)} titles',
                    fg=GREEN))
                self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))

            except Exception:
                import traceback
                tb = traceback.format_exc()
                self._debug(f"IGDB fetch error:\n{tb}")
                self._igdb_token = None  # reset token in case it expired
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Fetch failed — see debug log', fg=RED))
                self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))

        threading.Thread(target=_do, daemon=True).start()

    def _bind_search_entry(self, entry, get_all_fn, on_select_fn):
        """Attach a ▾ button next to the entry that opens a search popup."""
        # Insert a small dropdown button right after the entry in its parent
        btn = tk.Button(entry.master, text='▾', bg=BG3, fg=FG2, font=FONT_SM,
                        relief='flat', padx=4, cursor='hand2')
        btn.pack(side='left', padx=(0, 8))

        popup = {'win': None}

        def _toggle(event=None):
            if popup['win'] and popup['win'].winfo_exists():
                popup['win'].destroy()
                popup['win'] = None
                return
            all_names = get_all_fn()
            if not all_names:
                return

            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes('-topmost', True)
            win.configure(bg=ACC)
            popup['win'] = win

            entry.update_idletasks()
            x        = entry.winfo_rootx()
            w        = entry.winfo_width() + btn.winfo_width()
            h        = 220
            entry_y  = entry.winfo_rooty()
            entry_h  = entry.winfo_height()
            screen_h = self.root.winfo_screenheight()
            # Open popup with search box over the entry, list below
            # If not enough room below, open upward
            if entry_y + entry_h + h <= screen_h:
                y = entry_y  # search box covers the entry
            else:
                y = entry_y - h + entry_h  # flip upward
            win.geometry(f'{w}x{h}+{x}+{y}')

            inner = tk.Frame(win, bg=BG2)
            inner.pack(fill='both', expand=True, padx=1, pady=(0, 1))

            search_var = tk.StringVar()
            search = tk.Entry(inner, textvariable=search_var,
                              bg=BG2, fg=FG, font=FONT_SM,
                              insertbackground=FG, relief='flat',
                              borderwidth=6, highlightthickness=0)
            search.pack(fill='x')
            tk.Frame(inner, bg=BG3, height=1).pack(fill='x')

            row = tk.Frame(inner, bg=BG2)
            row.pack(fill='both', expand=True)
            sb = tk.Scrollbar(row, width=10, troughcolor=BG2,
                              bg=BG3, activebackground=ACC, relief='flat')
            sb.pack(side='right', fill='y')
            lb = tk.Listbox(row, bg=BG2, fg=FG, font=FONT_SM,
                            selectbackground=ACC, selectforeground=FG,
                            relief='flat', borderwidth=0, highlightthickness=0,
                            yscrollcommand=sb.set, activestyle='none')
            lb.pack(side='left', fill='both', expand=True)
            sb.config(command=lb.yview)

            def _fill(names):
                lb.delete(0, 'end')
                for n in names:
                    lb.insert('end', n)
                cur = entry.get()
                for i, n in enumerate(names):
                    if n == cur:
                        lb.selection_set(i)
                        # Scroll so selected item is at top — it's hidden by search box
                        lb.yview_moveto(i / max(len(names), 1))
                        break

            _fill(all_names)

            def _filter(*_):
                t = search_var.get().lower()
                filtered = [n for n in all_names if t in n.lower()]
                _fill(filtered if filtered else all_names)

            search_var.trace_add('write', _filter)

            def _pick(name):
                entry.delete(0, 'end')
                entry.insert(0, name)
                on_select_fn()
                _close()

            def _close():
                if popup['win'] and popup['win'].winfo_exists():
                    popup['win'].destroy()
                popup['win'] = None

            def _on_search_key(event):
                if event.keysym == 'Return':
                    sel = lb.curselection()
                    _pick(lb.get(sel[0]) if sel else (lb.get(0) if lb.size() else None))
                elif event.keysym == 'Escape':
                    _close()
                elif event.keysym == 'Down':
                    lb.focus_set()
                    lb.selection_set(0)
                    lb.see(0)

            def _on_lb_key(event):
                if event.keysym in ('Return', 'space'):
                    sel = lb.curselection()
                    if sel: _pick(lb.get(sel[0]))
                elif event.keysym == 'Escape':
                    _close()
                elif event.keysym == 'Up':
                    sel = lb.curselection()
                    if sel and sel[0] == 0:
                        search.focus_set()

            lb.bind('<Double-Button-1>', lambda e: _pick(lb.get(lb.curselection()[0]))
                    if lb.curselection() else None)
            lb.bind('<Key>', _on_lb_key)
            search.bind('<Key>', _on_search_key)

            # Close on click outside the popup
            def _on_click_outside(event):
                try:
                    wx, wy = win.winfo_rootx(), win.winfo_rooty()
                    ww, wh = win.winfo_width(), win.winfo_height()
                    if not (wx <= event.x_root <= wx+ww and wy <= event.y_root <= wy+wh):
                        _close()
                except Exception:
                    pass
            win.bind_all('<Button-1>', _on_click_outside)
            win.bind('<Destroy>', lambda e: win.unbind_all('<Button-1>'))

            search.focus_set()

        btn.config(command=_toggle)
        entry.bind('<Return>', _toggle)
        entry.bind('<Button-1>', _toggle)


    def _on_top_n_source_change(self, event=None):
        """Rebuild the dynamic controls area based on selected source."""
        if not hasattr(self, 'top_n_dynamic'):
            return
        for w in self.top_n_dynamic.winfo_children():
            w.destroy()
        src = self.top_n_source.get()
        d = self.top_n_dynamic

        def _filter_combo(var, opts, w=10):
            cb = ttk.Combobox(d, textvariable=var, values=opts,
                              state='readonly', font=FONT_SM, width=w)
            cb.pack(side='left', padx=(0, 4))
            cb.bind('<<ComboboxSelected>>', lambda e: self._save_settings())
            return cb

        def _spinbox(var, from_, to, inc, w=6, fmt=None):
            kw = dict(from_=from_, to=to, increment=inc, width=w,
                      bg=BG2, fg=FG, font=FONT_SM, relief='flat',
                      buttonbackground=BG3, insertbackground=FG)
            if fmt: kw['format'] = fmt
            sb = tk.Spinbox(d, textvariable=var, **kw)
            sb.pack(side='left', padx=(0, 8))
            return sb

        if src == 'RetroAchievements':
            if not self.ra_system.get() or self.ra_system.get() not in RA_SYSTEM_DISPLAY:
                self.ra_system.set(RA_SYSTEM_DISPLAY[0])
            self.ra_system_var = self.ra_system  # keep alias
            ra_entry = tk.Entry(d, textvariable=self.ra_system,
                                bg=BG2, fg=FG, font=FONT_SM, insertbackground=FG,
                                relief='flat', borderwidth=4, width=22)
            ra_entry.pack(side='left', padx=(0, 4))
            self._bind_search_entry(ra_entry,
                                    lambda: RA_SYSTEM_DISPLAY,
                                    lambda: self._save_settings())
            tk.Radiobutton(d, text='Top', variable=self.ra_filter_mode,
                           value='top_n', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left')
            _spinbox(self.ra_top_n, 1, 9999, 10)
            tk.Radiobutton(d, text='Min players', variable=self.ra_filter_mode,
                           value='min_players', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left', padx=(8, 0))
            _spinbox(self.ra_min_players, 0, 999999, 100, w=7)
            tk.Radiobutton(d, text='Max size GB', variable=self.ra_filter_mode,
                           value='max_size', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left', padx=(8, 0))
            _spinbox(self.top_n_max_size_gb, 0.1, 9999, 0.5, w=5, fmt='%.1f')
            self.lbl_top_n_hint.config(text='')

        elif src == 'IGDB':
            if not self._igdb_platforms:
                self._fetch_igdb_platforms()
            self.igdb_platform_entry = tk.Entry(
                d, textvariable=self.igdb_platform_name,
                bg=BG2, fg=FG, font=FONT_SM, insertbackground=FG,
                relief='flat', borderwidth=4, width=20)
            self.igdb_platform_entry.pack(side='left', padx=(0, 4))
            self._bind_search_entry(self.igdb_platform_entry,
                                    lambda: [n for _, n in self._igdb_platforms],
                                    self._on_igdb_platform_select)
            tk.Button(d, text='↺', bg=BG3, fg=FG2, font=FONT_SM,
                      relief='flat', padx=6,
                      command=self._fetch_igdb_platforms).pack(side='left', padx=(0, 8))
            tk.Radiobutton(d, text='Top', variable=self.igdb_filter_mode,
                           value='top_n', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left')
            _spinbox(self.igdb_top_n, 1, 9999, 10)
            tk.Radiobutton(d, text='Min score', variable=self.igdb_filter_mode,
                           value='min_score', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left', padx=(8, 0))
            _spinbox(self.igdb_min_score, 0, 100, 5, fmt='%.0f')
            tk.Radiobutton(d, text='Max size GB', variable=self.igdb_filter_mode,
                           value='max_size', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left', padx=(8, 0))
            _spinbox(self.top_n_max_size_gb, 0.1, 9999, 0.5, w=5, fmt='%.1f')
            self.lbl_top_n_hint.config(text='Click ↺ to load platform list from IGDB')

        elif src == 'MobyGames':
            if not self._moby_platforms:
                self._fetch_moby_platforms()
            self.moby_platform_entry = tk.Entry(
                d, textvariable=self.moby_platform_name,
                bg=BG2, fg=FG, font=FONT_SM, insertbackground=FG,
                relief='flat', borderwidth=4, width=20)
            self.moby_platform_entry.pack(side='left', padx=(0, 4))
            self._bind_search_entry(self.moby_platform_entry,
                                    lambda: [n for _, n in self._moby_platforms],
                                    self._on_moby_platform_select)
            tk.Button(d, text='↺', bg=BG3, fg=FG2, font=FONT_SM,
                      relief='flat', padx=6,
                      command=self._fetch_moby_platforms).pack(side='left', padx=(0, 10))
            tk.Radiobutton(d, text='Top', variable=self.moby_filter_mode,
                           value='top_n', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left')
            _spinbox(self.moby_top_n, 1, 9999, 10)
            tk.Radiobutton(d, text='Min score', variable=self.moby_filter_mode,
                           value='min_score', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left', padx=(8, 0))
            _spinbox(self.moby_min_score, 0, 10, 0.5, w=5, fmt='%.1f')
            tk.Radiobutton(d, text='Max size GB', variable=self.moby_filter_mode,
                           value='max_size', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left', padx=(8, 0))
            _spinbox(self.top_n_max_size_gb, 0.1, 9999, 0.5, w=5, fmt='%.1f')
            self.lbl_top_n_hint.config(
                text='Click ↺ to load platforms  |  requires: pip install cloudscraper')

        elif src == 'Screenscraper':
            if not self._ss_platforms:
                threading.Thread(target=self._fetch_ss_platforms, daemon=True).start()
            self.ss_platform_entry = tk.Entry(
                d, textvariable=self.ss_platform_name,
                bg=BG2, fg=FG, font=FONT_SM, insertbackground=FG,
                relief='flat', borderwidth=4, width=22)
            self.ss_platform_entry.pack(side='left', padx=(0, 4))
            self._bind_search_entry(self.ss_platform_entry,
                                    lambda: [n for _, n in self._ss_platforms],
                                    self._on_ss_platform_select)
            tk.Button(d, text='↺', bg=BG3, fg=FG2, font=FONT_SM,
                      relief='flat', padx=6,
                      command=self._fetch_ss_platforms).pack(side='left', padx=(0, 4))
            tk.Label(d, text='Genre:', bg=BG, fg=FG2, font=FONT_SM).pack(side='left')
            self.ss_genre_combo = ttk.Combobox(d, textvariable=self.ss_genre_filter,
                                               values=['All'] + sorted(self._ss_genres),
                                               state='readonly', font=FONT_SM, width=16)
            self.ss_genre_combo.pack(side='left', padx=(4, 8))
            self.ss_genre_combo.bind('<<ComboboxSelected>>', lambda e: self._save_settings())
            if self.ss_genre_filter.get() not in ['All'] + self._ss_genres:
                self.ss_genre_filter.set('All')
            tk.Checkbutton(d, text='En only', variable=self.ss_english_only,
                           bg=BG, fg=FG2, font=FONT_SM, selectcolor=BG2,
                           activebackground=BG, command=self._save_settings).pack(side='left', padx=(0, 8))
            tk.Radiobutton(d, text='Top', variable=self.ss_filter_mode,
                           value='top_n', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left')
            _spinbox(self.ss_top_n, 1, 9999, 10)
            tk.Radiobutton(d, text='Min rating', variable=self.ss_filter_mode,
                           value='min_rating', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left', padx=(8, 0))
            _spinbox(self.ss_min_rating, 0, 20, 1, w=5, fmt='%.0f')
            tk.Radiobutton(d, text='Max size GB', variable=self.ss_filter_mode,
                           value='max_size', bg=BG, fg=FG2, font=FONT_SM,
                           selectcolor=BG2, activebackground=BG,
                           command=self._save_settings).pack(side='left', padx=(8, 0))
            _spinbox(self.top_n_max_size_gb, 0.1, 9999, 0.5, w=5, fmt='%.1f')
            self.lbl_top_n_hint.config(text='No login required — uses public Screenscraper tables')

        self._save_settings()


    def _fetch_top_n(self):
        """Dispatch to the right fetch method based on selected source."""
        src = self.top_n_source.get()
        if src == 'RetroAchievements':
            self._fetch_ra_top()
        elif src == 'IGDB':
            self._fetch_igdb_top()
        elif src == 'Screenscraper':
            self._fetch_ss_top()
        else:
            self._fetch_moby_top()


    def _health_check(self):
        """Run sanity checks against all scraped sources and show results in a popup."""
        import threading, time

        win = tk.Toplevel(self.root)
        win.title('Health Check')
        win.configure(bg=BG)
        win.resizable(False, False)

        tk.Label(win, text='Validating scrapers against live sources...',
                 bg=BG, fg=FG2, font=FONT_SM).pack(anchor='w', padx=16, pady=(12, 4))

        frame = tk.Frame(win, bg=BG)
        frame.pack(fill='both', padx=16, pady=(0, 12))

        SECTIONS = [
            ('Setup', [
                ('Screenscraper platforms',     'ss_platforms'),
                ('Screenscraper genres',        'ss_genres'),
                ('MobyGames platforms',         'moby_platforms'),
            ]),
            ('Selection', [
                ('RetroAchievements sheet',     'ra_snes'),
                ('archive.org (3DS encrypted)', 'archive_nes'),
                ('Minerva (NDS Decrypted)',      'minerva_snes'),
                ('lolroms (Dreamcast)',          'lolroms'),
            ]),
            ('Compatibility', [
                ('RPCS3 compatibility API',     'rpcs3_compat'),
                ('PCSX2 GameIndex.yaml',        'pcsx2_compat'),
                ('Eden (Switch) GitHub',        'eden_compat'),
                ('CEMU (Wii U) GitHub',         'cemu_compat'),
                ('Vita3K (PS Vita) GitHub',     'vita3k_compat'),
                ('PPSSPP report.ppsspp.org',    'ppsspp_compat'),
                ('Xenia (Xbox 360) GitHub',     'xenia_compat'),
                ('TeknoParrot arcade list',     'tp_compat'),
                ('Azahar (3DS) JSON',           'azahar_compat'),
            ]),
        ]

        rows = {}
        for section_label, checks in SECTIONS:
            tk.Label(frame, text=section_label, bg=BG, fg=FG, font=FONT_SM,
                     pady=4).pack(anchor='w')
            sep = tk.Frame(frame, bg=FG2, height=1)
            sep.pack(fill='x', pady=(0, 4))
            for label, key in checks:
                row = tk.Frame(frame, bg=BG)
                row.pack(fill='x', pady=2)
                dot = tk.Label(row, text='⏳', bg=BG, fg=YELLOW, font=FONT_SM, width=3)
                dot.pack(side='left')
                tk.Label(row, text=f'{label:<32}', bg=BG, fg=FG2, font=FONT_SM).pack(side='left')
                detail = tk.Label(row, text='...', bg=BG, fg=FG2, font=FONT_SM)
                detail.pack(side='left')
                rows[key] = (dot, detail)

        def _update(key, ok, msg):
            dot, detail = rows[key]
            dot.config(text='✓' if ok else '✗', fg=GREEN if ok else RED)
            detail.config(text=msg, fg=GREEN if ok else RED)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
            'Accept-Language': 'en-US,en;q=0.5',
        }

        def _check_ss_platforms():
            try:
                t0 = time.time()
                req = urllib.request.Request(
                    'https://www.screenscraper.fr/gamesinfos.php?plateforme=0&alpha=0&numpage=0',
                    headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
                # Use same regex as _fetch_ss_platforms
                WANTED_SECTIONS = ('Consoles', 'Consoles Portable')
                platforms = {}
                current_section = ''
                for chunk in re.split(r'(<b>[^<]+</b>)', html):
                    hdr = re.fullmatch(r'<b>(.*?)</b>', chunk.strip(), re.IGNORECASE)
                    if hdr:
                        current_section = hdr.group(1).strip()
                        continue
                    if not any(current_section.startswith(s) for s in WANTED_SECTIONS):
                        continue
                    for m in re.finditer(
                            r"systemeinfos\.php\?plateforme=(\d+)[^'\"]*'[^>]*>.*?TITLE=\"([^\"]+)\"",
                            chunk, re.DOTALL):
                        platforms[m.group(1)] = m.group(2).strip()
                sentinel_name = platforms.get('15', '')
                ms = int((time.time() - t0) * 1000)
                if 'Nintendo DS' in sentinel_name:
                    self.root.after(0, lambda: _update('ss_platforms', True,
                        f'{len(platforms)} platforms, ID 15="{sentinel_name}" ✓ ({ms}ms)'))
                else:
                    self.root.after(0, lambda s=sentinel_name, n=len(platforms): _update('ss_platforms', False,
                        f'ID 15="{s}" expected "Nintendo DS" ({n} platforms)'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('ss_platforms', False, str(e)))

        def _check_ss_genres():
            try:
                t0 = time.time()
                req = urllib.request.Request(
                    'https://www.screenscraper.fr/groupes.php?grouptype=1',
                    headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
                # Parse same way as _fetch_ss_platforms genre fetch
                genre_id_map = {}
                chunks = re.split(r'(?=<a name="\d+")', html)
                for chunk in chunks:
                    id_m = re.match(r'<a name="(\d+)"', chunk)
                    if not id_m:
                        continue
                    gid = id_m.group(1)
                    en_m = re.search(r'<tr>\s*<td><img[^>]*en\.png[^>]*></td>\s*<td[^>]*>([^<]+)</td>\s*</tr>', chunk)
                    if en_m:
                        name_en = en_m.group(1).strip()
                        if name_en and len(name_en) < 80:
                            genre_id_map[gid] = name_en
                sentinel = genre_id_map.get('8', '')
                ms = int((time.time() - t0) * 1000)
                if sentinel == 'Role Playing Game':
                    self.root.after(0, lambda: _update('ss_genres', True,
                        f'{len(genre_id_map)} genres, ID 8="{sentinel}" ✓ ({ms}ms)'))
                else:
                    self.root.after(0, lambda s=sentinel: _update('ss_genres', False,
                        f'ID 8="{s}" expected "Role Playing Game"'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('ss_genres', False, str(e)))

        def _check_moby_platforms():
            try:
                t0 = time.time()
                scraper = self._cloudscraper()
                if not scraper:
                    self.root.after(0, lambda: _update('moby_platforms', False, 'cloudscraper not installed'))
                    return
                r = scraper.get('https://www.mobygames.com/platform/', timeout=20)
                import html as _html
                platforms = re.findall(r'<a href="/platform/([^/"]+)/">([^<]+)</a>', r.text)
                names = [_html.unescape(n.strip()) for _, n in platforms]
                sentinel = 'SNES'
                ms = int((time.time() - t0) * 1000)
                found = any(sentinel.lower() in n.lower() for n in names)
                if found:
                    self.root.after(0, lambda: _update('moby_platforms', True,
                        f'{len(names)} platforms, "{sentinel}" found ✓ ({ms}ms)'))
                else:
                    self.root.after(0, lambda: _update('moby_platforms', False,
                        f'"{sentinel}" not found in {len(names)} platforms'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('moby_platforms', False, str(e)))

        def _check_ra_snes():
            try:
                t0 = time.time()
                # RA Top N uses a public Google Sheet — same as _fetch_ra_top
                sheet_url = ('https://docs.google.com/spreadsheets/d/'
                             '1Pc8uRu6ovS6n2u8XxHeUaBchEnev7HBLmduv56MsdiY'
                             '/export?format=csv&gid=463627683')
                req = urllib.request.Request(sheet_url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    csv_data = r.read().decode('utf-8', errors='replace')
                import csv, io
                rows = list(csv.DictReader(io.StringIO(csv_data)))
                sentinel = 'Bubble Bobble'
                ms = int((time.time() - t0) * 1000)
                # Check sentinel exists in any Title column
                found = any(sentinel in str(row.get('Title', '') or row.get('Game', '') or '') for row in rows)
                if found:
                    self.root.after(0, lambda: _update('ra_snes', True,
                        f'{len(rows)} games in sheet, "{sentinel}" found ✓ ({ms}ms)'))
                else:
                    cols = list(rows[0].keys())[:4] if rows else []
                    self.root.after(0, lambda c=cols, n=len(rows): _update('ra_snes', False,
                        f'{n} rows, "{sentinel}" not found, cols: {c}'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('ra_snes', False, str(e)))

        def _check_archive_nes():
            try:
                t0 = time.time()
                access = self.access.get().strip()
                secret = self.secret.get().strip()
                entries, title = fetch_archive_filenames(
                    'https://archive.org/download/3ds-main-encrypted',
                    access or None, secret or None)
                sentinel = 'Atlantic Quest (Europe)'
                ms = int((time.time() - t0) * 1000)
                found = any(sentinel in e[0] for e in entries)
                if found:
                    self.root.after(0, lambda: _update('archive_nes', True,
                        f'{len(entries)} files, "{sentinel}" found ✓ ({ms}ms)'))
                else:
                    self.root.after(0, lambda: _update('archive_nes', False,
                        f'"{sentinel}" not found in {len(entries)} files'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('archive_nes', False, str(e)))

        def _check_minerva_snes():
            try:
                t0 = time.time()
                entries, title = fetch_minerva_filenames(
                    'https://minerva-archive.org/browse/No-Intro/Nintendo%20-%20Nintendo%20DS%20(Decrypted)/')
                sentinel = 'Aprende Con Pokemon - Aventura Entre Las Teclas (Spain)'
                ms = int((time.time() - t0) * 1000)
                found = any(sentinel in e[0] for e in entries)
                if found:
                    self.root.after(0, lambda: _update('minerva_snes', True,
                        f'{len(entries)} files, "{sentinel}" found ✓ ({ms}ms)'))
                else:
                    self.root.after(0, lambda: _update('minerva_snes', False,
                        f'"{sentinel}" not found in {len(entries)} files'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('minerva_snes', False, str(e)))

        def _check_lolroms():
            try:
                t0 = time.time()
                entries, title = fetch_lolroms_filenames(
                    'https://lolroms.com/SEGA/DreamCast')
                sentinel = 'Crazy Taxi (Europe)'
                ms = int((time.time() - t0) * 1000)
                found = any(sentinel in e[0] for e in entries)
                if found:
                    self.root.after(0, lambda: _update('lolroms', True,
                        f'{len(entries)} files, "{sentinel}" found ✓ ({ms}ms)'))
                else:
                    sample = [e[0] for e in entries[:3]]
                    self.root.after(0, lambda s=sample, n=len(entries): _update('lolroms', False,
                        f'"{sentinel}" not found in {n} files, sample: {s}'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('lolroms', False, str(e)))

        def _check_rpcs3_compat():
            try:
                t0 = time.time()
                req = urllib.request.Request(
                    'https://rpcs3.net/compatibility?api=v1&export',
                    headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    import json as _json
                    data = _json.loads(r.read())
                ret = data.get('results', data.get('return', {}))
                sentinel_id = 'BLES00932'  # Uncharted 2
                ms = int((time.time() - t0) * 1000)
                if sentinel_id in ret:
                    status = ret[sentinel_id].get('status', '?')
                    self.root.after(0, lambda: _update('rpcs3_compat', True,
                        f'{len(ret)} entries, {sentinel_id}="{status}" ✓ ({ms}ms)'))
                else:
                    self.root.after(0, lambda: _update('rpcs3_compat', False,
                        f'{len(ret)} entries, sentinel {sentinel_id} not found'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('rpcs3_compat', False, str(e)))

        def _check_tp_compat():
            try:
                t0 = time.time()
                req = urllib.request.Request(
                    'https://teknoparrot.com/en/Compatibility/Index',
                    headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
                n = html.count('<tr')
                ms = int((time.time() - t0) * 1000)
                if n > 10:
                    self.root.after(0, lambda: _update('tp_compat', True,
                        f'~{n-1} games listed ✓ ({ms}ms)'))
                else:
                    self.root.after(0, lambda: _update('tp_compat', False, 'No table rows found'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('tp_compat', False, str(e)))

        def _check_xenia_compat():
            try:
                import json as _json
                t0 = time.time()
                req = urllib.request.Request(
                    'https://api.github.com/repos/xenia-canary/game-compatibility/issues'
                    '?state=open&per_page=1&page=1',
                    headers={**headers, 'Accept': 'application/vnd.github.v3+json'})
                with urllib.request.urlopen(req, timeout=20) as r:
                    issues = _json.loads(r.read())
                    link = r.headers.get('Link', '')
                ms = int((time.time() - t0) * 1000)
                # Parse total from Link header last page
                total = '?'
                m = re.search(r'page=(\d+)>;\s*rel="last"', link)
                if m:
                    total = int(m.group(1)) * 100
                if issues:
                    self.root.after(0, lambda: _update('xenia_compat', True,
                        f'~{total} issues reachable ✓ ({ms}ms)'))
                else:
                    self.root.after(0, lambda: _update('xenia_compat', False, 'No issues returned'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('xenia_compat', False, str(e)))

        def _check_azahar_compat():
            try:
                t0 = time.time()
                req = urllib.request.Request(
                    'https://raw.githubusercontent.com/azahar-emu/compatibility-list/master/compatibility_list.json',
                    headers=headers)
                with urllib.request.urlopen(req, timeout=20) as r:
                    import json as _json
                    data = _json.loads(r.read())
                entries = data if isinstance(data, list) else data.get('games', data.get('entries', []))
                n = len([e for e in entries if e.get('compatibility', 99) != 99])
                ms = int((time.time() - t0) * 1000)
                self.root.after(0, lambda: _update('azahar_compat', True,
                    f'{n} rated entries ✓ ({ms}ms)'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('azahar_compat', False, str(e)))

        def _check_pcsx2_compat():
            try:
                t0 = time.time()
                url = 'https://raw.githubusercontent.com/PCSX2/pcsx2/master/bin/resources/GameIndex.yaml'
                req = urllib.request.Request(url, headers=_gh_headers())
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                count = data.count(b'\n  name:')
                self.root.after(0, lambda: _update('pcsx2_compat', True,
                    f'{count:,} entries  ({time.time()-t0:.1f}s)'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('pcsx2_compat', False, str(e)))

        def _check_eden_compat():
            try:
                t0 = time.time()
                import json as _j, urllib.parse as _up, cloudscraper as _cs
                EMULATOR_ID = '43bfc023-ec22-422d-8324-048a8ec9f28f'
                BASE = ('https://www.emuready.com/api/trpc/users.me,systems.get,devices.get,'
                        'socs.get,emulators.get,listings.performanceScales,listings.get')
                HEADERS = {
                    'accept': '*/*', 'content-type': 'application/json',
                    'referer': 'https://www.emuready.com/listings?emulatorIds=%5B%2243bfc023-ec22-422d-8324-048a8ec9f28f%22%5D&page=1',
                    'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
                }
                scraper = _cs.create_scraper()
                payload = {
                    '0': {'json': None, 'meta': {'values': ['undefined']}},
                    '1': {'json': None, 'meta': {'values': ['undefined']}},
                    '2': {'json': {'limit': 10000}}, '3': {'json': {'limit': 10000}},
                    '4': {'json': {'limit': 100}},
                    '5': {'json': None, 'meta': {'values': ['undefined']}},
                    '6': {'json': {'page': 1, 'limit': 100, 'emulatorIds': [EMULATOR_ID]}},
                }
                url = f'{BASE}?batch=1&input={_up.quote(_j.dumps(payload))}'
                r = scraper.get(url, headers=HEADERS, timeout=20)
                listings = r.json()[6].get('result', {}).get('data', {}).get('json', {}).get('listings', [])
                count = sum(1 for i in listings if i.get('emulatorId') == EMULATOR_ID)
                ms = int((time.time() - t0) * 1000)
                self.root.after(0, lambda: _update('eden_compat', True,
                    f'EmuReady reachable, {count} Eden entries ({ms}ms)'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('eden_compat', False, str(e)))

        def _check_cemu_compat():
            try:
                t0 = time.time()
                import json as _j
                url = 'https://api.github.com/repos/cemu-project/cemu_graphic_packs/contents'
                req = urllib.request.Request(url, headers=_gh_headers())
                with urllib.request.urlopen(req, timeout=30) as r:
                    _j.loads(r.read())
                self.root.after(0, lambda: _update('cemu_compat', True,
                    f'OK  ({time.time()-t0:.1f}s)'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('cemu_compat', False, str(e)))

        def _check_vita3k_compat():
            try:
                t0 = time.time()
                import json as _j
                url = 'https://api.github.com/repos/Vita3K/compatibility/issues?state=open&per_page=1&page=1'
                req = urllib.request.Request(url, headers=_gh_headers())
                with urllib.request.urlopen(req, timeout=30) as r:
                    remaining = int(r.headers.get('X-RateLimit-Remaining', 999))
                    _j.loads(r.read())
                self.root.after(0, lambda: _update('vita3k_compat', True,
                    f'OK  rate-limit remaining: {remaining}  ({time.time()-t0:.1f}s)'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('vita3k_compat', False, str(e)))

        def _check_ppsspp_compat():
            try:
                t0 = time.time()
                req = urllib.request.Request(
                    'https://report.ppsspp.org/games?page=1',
                    headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=20) as r:
                    html_text = r.read().decode('utf-8', errors='replace')
                count = html_text.count('<tr class="games">')
                self.root.after(0, lambda: _update('ppsspp_compat', True,
                    f'{count} rows on page 1  ({time.time()-t0:.1f}s)'))
            except Exception as ex:
                self.root.after(0, lambda e=ex: _update('ppsspp_compat', False, str(e)))

        for fn in [_check_ss_platforms, _check_ss_genres, _check_moby_platforms,
                   _check_ra_snes, _check_archive_nes, _check_minerva_snes, _check_lolroms,
                   _check_rpcs3_compat, _check_pcsx2_compat, _check_eden_compat,
                   _check_cemu_compat, _check_vita3k_compat, _check_ppsspp_compat,
                   _check_xenia_compat, _check_tp_compat, _check_azahar_compat]:
            threading.Thread(target=fn, daemon=True).start()


    def _cloudscraper(self):
        """Return a cloudscraper session, or None with error if not installed."""
        try:
            import cloudscraper as _cs
            return _cs.create_scraper()
        except ImportError:
            self.root.after(0, lambda: messagebox.showerror(
                'cloudscraper not found',
                'Moby Top requires cloudscraper.\n\n'
                'Install it with:\n    pip install cloudscraper\n\n'
                'Then restart RomGoGetter.'))
            return None

    def _fetch_ss_platforms(self):
        """Fetch platform list from Screenscraper public gamesinfos page."""
        def _do():
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
                    'Accept-Language': 'en-US,en;q=0.5',
                }
                try:
                    self.root.after(0, lambda: self.lbl_top_n_status.config(
                        text='Loading Screenscraper platforms...', fg=YELLOW))
                except RuntimeError:
                    pass
                url = 'https://www.screenscraper.fr/gamesinfos.php?plateforme=0&alpha=0&numpage=0'
                html = _fetch_html_cached(url, headers)
                # Links are onclick="document.location='systemeinfos.php?plateforme=ID&...'"
                # Names are in TITLE="Manufacturer : Platform name" on the img inside each cell
                # Only keep platforms in Consoles and Consoles Portable sections
                WANTED_SECTIONS = ('Consoles', 'Consoles Portable')
                platforms = []
                seen = set()
                # Split by section headers
                section_re = re.compile(r'<b>(.*?)</b>', re.IGNORECASE)
                current_section = ''
                # Walk through section headers and platform cells together
                for chunk in re.split(r'(<b>[^<]+</b>)', html):
                    hdr = section_re.fullmatch(chunk.strip())
                    if hdr:
                        current_section = hdr.group(1).strip()
                        continue
                    if not any(current_section.startswith(s) for s in WANTED_SECTIONS):
                        continue
                    for m in re.finditer(
                            r"systemeinfos\.php\?plateforme=(\d+)[^'\"]*'[^>]*>.*?TITLE=\"([^\"]+)\"",
                            chunk, re.DOTALL):
                        pid  = int(m.group(1))
                        name = html_unescape(m.group(2).strip())
                        if pid and name and pid not in seen:
                            seen.add(pid)
                            platforms.append((pid, name))
                platforms.sort(key=lambda x: x[1].lower())
                self._ss_platforms = platforms
                names = [n for _, n in platforms]
                self._debug(f'Screenscraper: {len(platforms)} platforms loaded')

                # Fetch global genre list (always refresh with platform list)
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Fetching genre list...', fg=YELLOW))
                try:
                    genre_url = 'https://www.screenscraper.fr/groupes.php?grouptype=1'
                    genre_html = _fetch_html_cached(genre_url, headers)
                    self._debug(f'SS genre page: {len(genre_html)} bytes')
                    genre_id_map = {}  # group_id_str -> English name
                    chunks = re.split(r'(?=<a name="\d+")', genre_html)
                    for chunk in chunks:
                        id_m = re.match(r'<a name="(\d+)"', chunk)
                        if not id_m:
                            continue
                        gid = id_m.group(1)
                        # Match the full <tr> containing en.png and grab the text td
                        en_m = re.search(
                            r'<tr>\s*<td><img[^>]*en\.png[^>]*></td>\s*<td[^>]*>([^<]+)</td>\s*</tr>',
                            chunk)
                        if en_m:
                            name_en = en_m.group(1).strip()
                            if name_en and len(name_en) < 80:
                                genre_id_map[gid] = name_en
                    self._debug(f'SS genre id map: {len(genre_id_map)} entries')
                    if genre_id_map:
                        self._ss_genre_id_map = genre_id_map
                        self._ss_genres = sorted(set(genre_id_map.values()))
                        # Build parent->children map using page structure
                        # Top-level genres have cssstatsfontbig, subcategories have icon-children.png
                        genre_parent_map = {}  # child_name -> parent_name
                        current_parent = None
                        for chunk in chunks:
                            id_m = re.match(r'<a name="(\d+)"', chunk)
                            if not id_m:
                                continue
                            gid = id_m.group(1)
                            if gid not in genre_id_map:
                                continue
                            name = genre_id_map[gid]
                            if 'cssstatsfontbig' in chunk:
                                current_parent = name
                            elif 'icon-children' in chunk and current_parent:
                                genre_parent_map[name] = current_parent
                        self._ss_genre_parent_map = genre_parent_map
                        self._save_settings()
                        self._debug(f'SS genres loaded: {len(self._ss_genres)}, parent map: {len(genre_parent_map)} children')
                        for gid, name in sorted(genre_id_map.items(), key=lambda x: x[1]):
                            parent = genre_parent_map.get(name, '')
                            self._debug(f'  genre {gid}: {name!r} parent={parent!r}')
                except Exception as ex:
                    self._debug(f'SS genre fetch error: {ex}')
                def _update():
                    saved = self.ss_platform_name.get()
                    if saved not in names and names:
                        self.ss_platform_name.set(names[0])
                        self._on_ss_platform_select()
                    elif saved in names:
                        self._on_ss_platform_select()
                    if hasattr(self, 'ss_genre_combo') and self._ss_genres:
                        self.ss_genre_combo['values'] = ['All'] + self._ss_genres
                        if self.ss_genre_filter.get() not in ['All'] + self._ss_genres:
                            self.ss_genre_filter.set('All')
                    self.lbl_top_n_status.config(
                        text=f'{len(platforms)} platforms loaded', fg=GREEN)
                self.root.after(0, _update)
            except Exception:
                import traceback
                self._debug(f'SS platform fetch error:\n{traceback.format_exc()}')
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Failed to load platforms — see debug log', fg=RED))
        threading.Thread(target=_do, daemon=True).start()

    def _on_ss_platform_select(self, event=None):
        name = self.ss_platform_name.get()
        for pid, pname in self._ss_platforms:
            if pname == name:
                self.ss_platform_id.set(pid)
                self._save_settings()
                return

    def _fetch_ss_top(self):
        """Fetch top games from Screenscraper public tables, apply 1G1R."""
        if not self.raw_file_entries:
            messagebox.showerror('Error', 'Run GoGet! first to fetch the file list.')
            return
        pid = self.ss_platform_id.get()
        if not pid:
            messagebox.showerror('Error', 'Select a platform first.\nClick ↺ to load the platform list.')
            return

        self.btn_fetch_top_n.config(state='disabled')
        self.lbl_top_n_status.config(text='Fetching Screenscraper data...', fg=YELLOW)
        self.root.update()

        _filter_mode    = self.ss_filter_mode.get()
        _top_n          = max(1, self.ss_top_n.get())
        _min_rating     = self.ss_min_rating.get()
        _sort_by        = self.ss_sort_by.get()
        _genre_filter   = re.sub(r'\s*\(\d+\)$', '', self.ss_genre_filter.get())
        _english_only   = self.ss_english_only.get()
        _max_size_bytes = self.top_n_max_size_gb.get() * 1024**3

        def _do():
            try:
                # Ensure genre id map is loaded
                if not self._ss_genre_id_map:
                    self._ss_genre_id_map  = self.settings.get('ss_genre_id_map', {})
                if not self._ss_genre_parent_map:
                    self._ss_genre_parent_map = self.settings.get('ss_genre_parent_map', {})

                # ── Scrape game pages ─────────────────────────────────────────
                titles   = []   # [(name, scrapes, rating), ...]
                numpage  = 0
                headers  = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
                            'Accept-Language': 'en-US,en;q=0.5'}

                # ── Helpers for matching — identical to Moby pipeline ─────────
                _EDITION_RE_SS = re.compile(
                    r'\b('
                    r'limited edition|collector\'s edition|collectors edition|'
                    r'game of the year edition|goty edition|complete edition|'
                    r'definitive edition|enhanced edition|ultimate edition|'
                    r'platinum edition|gold edition|silver edition|premium edition|'
                    r'director\'s cut|directors cut|deluxe edition|remastered edition|'
                    r'anniversary edition|expanded edition|extended edition|'
                    r'bundle edition|digital edition|digital deluxe edition'
                    r')\b', re.IGNORECASE)

                def _deaccent(s):
                    for a, b in [('ō','oo'),('Ō','oo'),('ū','uu'),('Ū','uu'),
                                 ('ā','a'),('Ā','a'),('ē','e'),('Ē','e'),
                                 ('ī','i'),('Ī','i')]:
                        s = s.replace(a, b)
                    import unicodedata as _ud
                    s = _ud.normalize('NFKD', s)
                    s = ''.join(c for c in s if not _ud.combining(c))
                    s = s.lower()
                    # Normalize roman numerals to arabic (longest first to avoid partial matches)
                    for roman, arabic in [('viii','8'),('vii','7'),('vi','6'),('ix','9'),
                                          ('xii','12'),('xi','11'),('x','10'),
                                          ('iv','4'),('iii','3'),('ii','2'),('v','5'),('i','1')]:
                        s = re.sub(r'(?<![a-z0-9])' + roman + r'(?![a-z0-9])', arabic, s)
                    return s
                def _strip_editions(s):
                    s = _EDITION_RE_SS.sub('', s)
                    s = re.sub(r'[\-:]\s*(the|a|an)\s*[\-:]', ':', s, flags=re.IGNORECASE)
                    s = re.sub(r'[\-:]\s*(the|a|an)\s*$', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'[\s\-:]+$', '', s)
                    return re.sub(r'\s{2,}', ' ', s).strip()

                def _tokenize(s):
                    s = _deaccent(_strip_editions(s))
                    s = re.sub(r'[:\-\u00b7\u2013\u2014,\'\"()!]', ' ', s)
                    return set(re.findall(r'[a-z0-9]+', s))

                def _normalize_str(s):
                    n = re.sub(r'[^a-z0-9]', '', _deaccent(_strip_editions(s)))
                    return _TITLE_ALIASES.get(n, n)

                def _jaccard(a, b):
                    if a == b: return 1.0
                    ta, tb = _tokenize(a), _tokenize(b)
                    if not ta or not tb: return 0.0
                    return len(ta & tb) / len(ta | tb)

                def _fuzzy(a, b):
                    if a == b: return 1.0
                    na, nb = _normalize_str(a), _normalize_str(b)
                    if not na or not nb: return 0.0
                    from difflib import SequenceMatcher
                    return SequenceMatcher(None, na, nb).ratio()

                _STOPWORDS = {'a','an','the','of','in','on','at','to',
                              'for','and','or','is','it','vs'}

                def _content_tokens(s):
                    return _tokenize(s) - _STOPWORDS

                def _score(a, b):
                    base = 0.5 * _jaccard(a, b) + 0.5 * _fuzzy(a, b)
                    ta, tb = _content_tokens(a), _content_tokens(b)
                    if ta and tb:
                        shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
                        if shorter <= longer:
                            tok = next(iter(shorter)) if len(shorter) == 1 else None
                            specific = len(shorter) >= 2 or (tok and len(tok) >= 6)
                            if specific:
                                containment = 0.5 + 0.5 * (len(shorter) / len(longer))
                                return max(base, containment)
                    return base

                THRESHOLD = 0.50

                english_entries, nonenglish_entries = [], []
                for e in self.raw_file_entries:
                    parsed = parse_rom_filename(e[0])
                    if (parsed['countries'] & ENGLISH_COUNTRIES
                            or 'En' in parsed['languages']
                            or not parsed['countries']):
                        english_entries.append(e)
                    else:
                        nonenglish_entries.append(e)

                def _bare(fname):
                    base = os.path.splitext(fname)[0]
                    b = re.sub(r'\s*\([^)]*\)', '', base).strip()
                    return re.sub(r'\s*(Disc|Disk)\s*\d+', '', b, flags=re.IGNORECASE).strip()

                english_bare    = [(_bare(e[0]), e) for e in english_entries]
                nonenglish_bare = [(_bare(e[0]), e) for e in nonenglish_entries]



                def _norm_roman(s):
                    s = s.lower()
                    for roman, arabic in [('viii','8'),('vii','7'),('vi','6'),('ix','9'),
                                          ('iv','4'),('iii','3'),('ii','2'),('xi','11'),
                                          ('xii','12'),('xiii','13'),('xiv','14'),('xv','15'),
                                          ('xvi','16'),('xvii','17'),('xviii','18'),('xix','19'),
                                          ('xx','20'),('x','10')]:
                        s = re.sub(r'(?<![a-z0-9])' + roman + r'(?![a-z0-9])', arabic, s)
                    return s

                def _build_title_index(title_list):
                    """Build token->titles index for fast candidate lookup."""
                    from collections import defaultdict as _dd
                    idx = _dd(list)
                    for t in title_list:
                        words = re.sub(r'[^a-zA-Z0-9]', ' ', _norm_roman(t)).split()
                        for w in words:
                            if w.isdigit() and len(w) < 2: continue  # skip single digits
                            if (len(w) >= 3 or (w.isdigit() and len(w) >= 2)) and w not in _STOPWORDS:
                                idx[w].append(t)
                    return idx

                def _candidates(bare, idx, title_list):
                    words = re.sub(r'[^a-zA-Z0-9]', ' ', _norm_roman(bare)).split()
                    found = {}
                    for w in words:
                        if w.isdigit() and len(w) < 2: continue  # skip single digits
                        if len(w) >= 3 or (w.isdigit() and len(w) >= 2):
                            for t in idx.get(w, []):
                                found[t] = None
                    if not found:
                        return title_list
                    return list(found.keys())

                def _ss_full_selection(title_names):
                    """Run full 1G1R over title_names, return (ss_groups, ordered)."""
                    ss_groups = {t: [] for t in title_names}
                    ss_best_score = {t: 0.0 for t in title_names}
                    idx = _build_title_index(title_names)
                    _total_ss = len(english_bare)
                    for _i, (bare, entry) in enumerate(english_bare):
                        self.root.after(0, lambda i=_i, t=_total_ss: self.lbl_top_n_status.config(
                            text=f'Matching ROMs... {i:,}/{t:,}', fg=YELLOW))
                        best_s, best_t = 0, None
                        for mt in _candidates(bare, idx, title_names):
                            s = _score(bare, mt)
                            if s > best_s:
                                best_s, best_t = s, mt
                        if best_t and best_s >= THRESHOLD:
                            ss_groups[best_t].append((best_s, entry))
                            if best_s > ss_best_score[best_t]:
                                ss_best_score[best_t] = best_s
                    for mt in title_names:
                        best = ss_best_score[mt]
                        ss_groups[mt] = [e for s, e in ss_groups[mt] if s >= best - 0.10]
                    still_unmatched = [t for t in title_names if not ss_groups[t]]
                    _ne_matched = set()  # titles matched only via non-English ROMs
                    _ne_fnames_map = {}  # mt -> [fname, ...]
                    if still_unmatched and nonenglish_bare:
                        nb_best = {t: 0.0 for t in still_unmatched}
                        nb_entries = {t: [] for t in still_unmatched}
                        ne_idx = _build_title_index(still_unmatched)
                        for bare, entry in nonenglish_bare:
                            best_s, best_t = 0, None
                            for mt in _candidates(bare, ne_idx, still_unmatched):
                                s = _score(bare, mt)
                                if s > best_s:
                                    best_s, best_t = s, mt
                            if best_t and best_s >= THRESHOLD and not ss_groups[best_t]:
                                nb_entries[best_t].append((best_s, entry))
                                if best_s > nb_best[best_t]:
                                    nb_best[best_t] = best_s
                        for mt in still_unmatched:
                            best = nb_best[mt]
                            ne_group = [e for s, e in nb_entries[mt] if s >= best - 0.10]
                            if ne_group and not _english_only:
                                ss_groups[mt] = ne_group
                            elif ne_group and _english_only:
                                _ne_matched.add(mt)
                                _ne_fnames_map[mt] = [e[0] for e in ne_group]
                    ordered = []
                    for mt in title_names:
                        entries = ss_groups.get(mt, [])
                        if not entries:
                            continue
                        variant_groups = {}
                        for entry in entries:
                            p = parse_rom_filename(entry[0])
                            inst = {'filename': entry[0], 'size': entry[1],
                                    'direct_url': entry[2] if len(entry) > 2 else None,
                                    'countries': p['countries'], 'languages': p['languages'],
                                    'attributes': p['attributes']}
                            key = re.sub(r'\s*\([^)]*\)', '', os.path.splitext(entry[0])[0]).strip()
                            variant_groups.setdefault(key, []).append(inst)
                        all_insts = [i for insts in variant_groups.values() for i in insts]
                        filtered  = [i for i in all_insts if not is_excluded(i)] or all_insts
                        best = select_best(filtered)
                        if not best:
                            continue
                        best_key = re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                          os.path.splitext(best['filename'])[0],
                                          flags=re.IGNORECASE).strip()
                        winning_discs = [i for i in all_insts
                                         if re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                                   os.path.splitext(i['filename'])[0],
                                                   flags=re.IGNORECASE).strip() == best_key]
                        sz = sum(parse_size_bytes(i.get('size', '0')) for i in winning_discs)
                        ordered.append((mt, winning_discs, sz))
                    return ss_groups, ordered, _ne_matched, _ne_fnames_map

                _accum_bytes   = 0
                selected_fnames = set()
                ss_groups_final = {}

                while True:
                    url = f'https://www.screenscraper.fr/gamesinfos.php?action=gamesclassementnote&plateforme={pid}&numpage={numpage}'
                    _cached = _url_fetch_cache.get(url)
                    if _cached:
                        page_html = _cached[0]  # stored as (html, None)
                        self._debug(f'SS page {numpage}: cached')
                    else:
                        self._debug(f'SS fetch page {numpage}: {url}')
                        self.root.after(0, lambda p=numpage:
                            self.lbl_top_n_status.config(
                                text=f'Fetching page {p+1}...', fg=YELLOW))
                        try:
                            req = urllib.request.Request(url, headers=headers)
                            with urllib.request.urlopen(req, timeout=30) as r:
                                page_html = r.read().decode('utf-8', errors='replace')
                            _url_fetch_cache[url] = (page_html, None)
                        except Exception as ex:
                            self._debug(f'SS page {numpage} fetch error: {ex}')
                            break

                    # Game rows contain nested tables so </tr> appears inside them.
                    # Split on <tr name="trNNNN"> openings instead.
                    rows_found = 0
                    chunks = re.split(r'(?=<tr\s[^>]*\bname="tr\d+")', page_html)
                    for chunk in chunks:
                        if not re.match(r'<tr\s[^>]*\bname="tr\d+"', chunk):
                            continue
                        row_html = chunk

                        # Game name: <div id="gamechangenameintNNNN"><a ...><font ...>NAME</font>
                        name_m = re.search(
                            r'<div id="gamechangenameint\d+"[^>]*>'
                            r'(?:<[^>]+>)*'          # skip any opening tags (a, font, etc.)
                            r'([^<\n]+)',            # actual text
                            row_html)
                        if not name_m:
                            continue
                        name = html_unescape(name_m.group(1).strip())
                        if not name:
                            continue

                        # Rating from TITLE="N/20"
                        rating = 0.0
                        rating_m = re.search(r'TITLE="([\d.]+)/20\s*"', row_html)
                        if rating_m:
                            try:
                                rating = float(rating_m.group(1))
                            except ValueError:
                                pass

                        # Genres from <div id="genresNNNN"> — extract all pictoliste group IDs
                        genres = []
                        genres_start = row_html.find('id="genres')
                        if genres_start != -1:
                            # Find the closing </div> after the genres table
                            table_end = row_html.find('</table>', genres_start)
                            genres_end = row_html.find('</div>', table_end) if table_end != -1 else -1
                            genre_block = row_html[genres_start:genres_end] if genres_end != -1 else row_html[genres_start:]
                            for gm in re.finditer(r'groups/(\d+)/pictoliste', genre_block):
                                gid = gm.group(1)
                                eng = self._ss_genre_id_map.get(gid)
                                if eng and eng not in genres:
                                    genres.append(eng)

                        rows_found += 1
                        titles.append((name, 0, rating, genres))

                    self._debug(f'  SS page {numpage}: {rows_found} rows, {len(titles)} games total')

                    if rows_found == 0:
                        break  # no more pages

                    # Pages are pre-sorted by rating desc — stop as soon as we have enough
                    if _filter_mode == 'top_n':
                        if _genre_filter and _genre_filter != 'All':
                            genre_filtered = [t for t in titles if any(
                                g == _genre_filter or g.startswith(_genre_filter + ' /') or self._ss_genre_parent_map.get(g) == _genre_filter for g in t[3])]
                        else:
                            genre_filtered = titles
                        if len(genre_filtered) >= _top_n:
                            self._debug(f'  SS: reached top_n={_top_n} after genre filter, stopping')
                            break
                    if _filter_mode == 'min_rating' and titles and titles[-1][2] < _min_rating:
                        self._debug(f'  SS: rating dropped below {_min_rating}, stopping')
                        break
                    if _filter_mode == 'max_size':
                        # Apply genre filter to current titles before selection
                        cur_titles = titles
                        if _genre_filter and _genre_filter != 'All':
                            cur_titles = [(n, s, r, gs) for n, s, r, gs in titles if any(g == _genre_filter or g.startswith(_genre_filter + " /") or self._ss_genre_parent_map.get(g) == _genre_filter for g in gs)]
                        title_names_cur = [n for n, s, r, gs in cur_titles]
                        prev_count = len(selected_fnames)
                        ss_groups_final, ordered = _ss_full_selection(title_names_cur)
                        total = sum(sz for _, _, sz in ordered)
                        self._debug(f'  After page {numpage}: {len(ordered)} files, {format_size(total)}')
                        if total > _max_size_bytes:
                            # Trim lowest-ranked from end until under budget
                            while ordered and total > _max_size_bytes:
                                mt, discs, sz = ordered.pop()
                                total -= sz
                                self._debug(f'  [SS] TRIM: {mt}  ({sz:,} B)  now={format_size(total)}')
                            selected_fnames = {i['filename'] for _, discs, _ in ordered for i in discs}
                            _accum_bytes = total
                            self._debug(f'  Budget reached after page {numpage}, stopping')
                            break
                        selected_fnames = {i['filename'] for _, discs, _ in ordered for i in discs}
                        _accum_bytes = total
                        if len(selected_fnames) == prev_count and numpage > 0:
                            self._debug(f'  No new files matched on page {numpage}, stopping')
                            break

                    numpage += 1
                    time.sleep(0.5)

                if not titles:
                    self.root.after(0, lambda: self.lbl_top_n_status.config(
                        text='No games found — check platform', fg=RED))
                    self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))
                    return

                # ── Collect genres, save, update combo ───────────────────────
                all_genres = sorted({g for _, _, _, gs in titles for g in gs})
                self._ss_genres = all_genres
                self._save_settings()
                def _update_genre_combo():
                    if hasattr(self, 'ss_genre_combo'):
                        if not _genre_filter or _genre_filter == 'All':
                            # Count titles per genre (including subcategory matching)
                            from collections import Counter
                            genre_counts = Counter()
                            for _, _, _, gs in titles:
                                for g in gs:
                                    genre_counts[g] += 1
                                    parent = self._ss_genre_parent_map.get(g)
                                    if parent:
                                        genre_counts[parent] += 1
                            combo_values = ['All'] + [
                                f'{g} ({genre_counts[g]})' if genre_counts.get(g) else g
                                for g in all_genres
                            ]
                        else:
                            combo_values = ['All'] + all_genres
                        self.ss_genre_combo['values'] = combo_values
                self.root.after(0, _update_genre_combo)

                # ── Genre filter ──────────────────────────────────────────────
                if _genre_filter and _genre_filter != 'All':
                    titles = [(n, s, r, gs) for n, s, r, gs in titles if any(g == _genre_filter or g.startswith(_genre_filter + " /") or self._ss_genre_parent_map.get(g) == _genre_filter for g in gs)]
                    self._debug(f'SS genre filter "{_genre_filter}": {len(titles)} games remain')

                if _filter_mode == 'min_rating':
                    titles = [(n, s, r, gs) for n, s, r, gs in titles if r >= _min_rating]
                elif _filter_mode == 'top_n':
                    titles = titles[:_top_n]  # genre filter already applied above

                if not titles:
                    self.root.after(0, lambda: self.lbl_top_n_status.config(
                        text='No games found — check platform', fg=RED))
                    self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))
                    return

                self._debug(f'SS: {len(titles)} titles after filter. #1={titles[0][0]!r}')
                title_names = [n for n, s, r, gs in titles]

                # ── 1G1R selection ────────────────────────────────────────────
                self.root.after(0, lambda n=len(title_names): self.lbl_top_n_status.config(
                    text=f'Matching {n} titles against {len(self.raw_file_entries):,} ROMs...', fg=YELLOW))
                if _filter_mode == 'max_size':
                    # Already done page-by-page above; selected_fnames and _accum_bytes are set
                    ss_groups = ss_groups_final
                    matched_titles = set(mt for mt in title_names if ss_groups_final.get(mt))
                    unmatched = [t for t in title_names if not ss_groups_final.get(t)]
                    self._debug(f'SS matched: {len(matched_titles)}, unmatched: {len(unmatched)}')
                else:
                    ss_groups, ordered, _ne_matched, _ne_fnames_map = _ss_full_selection(title_names)
                    matched_titles = set(mt for mt in title_names if ss_groups.get(mt))
                    unmatched = [t for t in title_names if not ss_groups.get(t)]
                    self._debug(f'SS matched: {len(matched_titles)}, unmatched: {len(unmatched)}')
                    # For top_n: ordered is already in SS rating order — trim to top_n matched
                    if _filter_mode == 'top_n' and len(ordered) > _top_n:
                        ordered = ordered[:_top_n]
                    selected_fnames = set()
                    _accum_bytes = 0
                    for mt, discs, sz in ordered:
                        for inst in discs:
                            selected_fnames.add(inst['filename'])
                            self._debug(f"  [SS] {inst['filename']}  {inst.get('size','?')} ({sz:,} B)")
                        _accum_bytes += sz

                self._debug(f'SS 1G1R: {len(selected_fnames)} files selected')

                result, summary = self._apply_filter(self.raw_file_entries, 'All files')
                for title, data in result.items():
                    if data['selected']:
                        if data['selected']['filename'] not in selected_fnames:
                            data['selected'] = None
                result_fnames = {d['selected']['filename'] for d in result.values() if d['selected']}
                for entry in self.raw_file_entries:
                    if entry[0] in selected_fnames and entry[0] not in result_fnames:
                        result[entry[0]] = {'selected': {'filename': entry[0], 'size': entry[1], 'direct_url': entry[2] if len(entry) > 2 else None}, 'non_english': False, 'instances': []}
                # Second pass: find titles with only non-English matches (vs truly missing)
                # Mark non-English Top N ROM groups as non_english in result
                _ne_fnames = {fname for fnames in _ne_fnames_map.values() for fname in fnames}
                for rdata in result.values():
                    if any(inst['filename'] in _ne_fnames for inst in rdata.get('instances', [])):
                        rdata['non_english'] = True

                for mt in title_names:
                    entries = ss_groups.get(mt, [])
                    has_selected = entries and any(e[0] in selected_fnames for e in entries)
                    has_ne = mt in _ne_fnames_map
                    if not has_selected and not has_ne:
                        result[f'__missing__{mt}'] = {
                            'selected': None, 'non_english': False,
                            'instances': [], '_dat_missing': True,
                            '_dat_fname': mt, '_dat_size': '',
                        }
                self.rom_dict    = result
                self.summary     = summary
                self.summary['selected_bytes'] = _accum_bytes
                self.summary['selected_size']  = format_size(_accum_bytes)
                self.dat_mode    = True
                self._top_n_mode = True
                self.root.after(0, self._analysis_done)
                n_matched = len(matched_titles)
                self.root.after(0, lambda nm=n_matched, nf=len(selected_fnames), nt=len(title_names):
                    self.lbl_top_n_status.config(
                        text=f'{nf} ROMs selected — {nm}/{nt} titles matched',
                        fg=GREEN))
                self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))

            except Exception:
                import traceback
                tb = traceback.format_exc()
                self._debug(f'SS fetch error:\n{tb}')
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Fetch failed — see debug log', fg=RED))
                self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))

        threading.Thread(target=_do, daemon=True).start()

    def _fetch_moby_platforms(self):
        """Fetch platform list from MobyGames and populate combo."""
        def _do():
            scraper = self._cloudscraper()
            if not scraper:
                return
            try:
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Loading platforms...', fg=YELLOW))
                _moby_plat_url = 'https://www.mobygames.com/platform/'
                _moby_plat_cached = _url_fetch_cache.get(('html', _moby_plat_url))
                if _moby_plat_cached:
                    _plat_text = _moby_plat_cached[0]
                else:
                    r = scraper.get(_moby_plat_url, timeout=20)
                    if r.status_code != 200:
                        raise Exception(f'HTTP {r.status_code}')
                    _plat_text = r.text
                    _url_fetch_cache[('html', _moby_plat_url)] = (_plat_text, None)
                import re as _re, html as _html
                platforms = []
                for m in _re.finditer(r'<a href="/platform/([^/"]+)/">([^<]+)</a>', _plat_text):
                    slug = m.group(1)
                    name = _html.unescape(m.group(2).strip())
                    if name and slug:
                        platforms.append((slug, name))
                seen = set()
                unique = []
                for slug, name in sorted(platforms, key=lambda x: x[1].lower()):
                    if slug not in seen:
                        seen.add(slug)
                        unique.append((slug, name))
                self._moby_platforms = unique
                names = [n for _, n in unique]
                self._debug(f'MobyGames: {len(unique)} platforms loaded')
                def _update():
                    self._moby_platform_names = names
                    saved = self.moby_platform_name.get()
                    if saved in names:
                        self.moby_platform_name.set(saved)
                    elif names:
                        self.moby_platform_name.set(names[0])
                        self._on_moby_platform_select()
                    self.lbl_top_n_status.config(
                        text=f'{len(unique)} platforms loaded', fg=GREEN)
                self.root.after(0, _update)
            except Exception:
                import traceback
                self._debug(f'Moby platform fetch error:\n{traceback.format_exc()}')
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Failed to load platforms — see debug log', fg=RED))
        threading.Thread(target=_do, daemon=True).start()

    def _on_moby_platform_select(self, event=None):
        """Update moby_platform_slug when user selects a platform."""
        name = self.moby_platform_name.get()
        for slug, pname in self._moby_platforms:
            if pname == name:
                self.moby_platform_slug.set(slug)
                self._save_settings()
                return

    def _fetch_moby_top(self):
        """Fetch top N games from MobyGames by MobyScore, apply 1G1R."""
        if not self.raw_file_entries:
            messagebox.showerror('Error', 'Run GoGet! first to fetch the file list.')
            return
        slug = self.moby_platform_slug.get()
        if not slug:
            messagebox.showerror('Error',
                'Select a platform first.\nClick ↺ to load the platform list.')
            return
        scraper = self._cloudscraper()
        if not scraper:
            return

        self.btn_fetch_top_n.config(state='disabled')
        self.lbl_top_n_status.config(text='Fetching MobyGames data...', fg=YELLOW)
        self.root.update()

        _filter_mode    = self.moby_filter_mode.get()
        _top_n          = max(1, self.moby_top_n.get())
        _min_score      = self.moby_min_score.get()
        _max_size_bytes = self.top_n_max_size_gb.get() * 1024**3
        pages_needed    = (_top_n + 49) // 50 if _filter_mode == 'top_n' else 20

        def _do():
            try:
                import re as _re, html as _html

                # ── Jaccard token matching helpers (needed during page loop for max_size) ──
                _EDITION_RE = re.compile(
                    r'\b('
                    r'limited edition|'
                    r'collector\'s edition|collectors edition|'
                    r'game of the year edition|goty edition|'
                    r'complete edition|definitive edition|enhanced edition|'
                    r'ultimate edition|platinum edition|'
                    r'gold edition|silver edition|premium edition|'
                    r'director\'s cut|directors cut|'
                    r'deluxe edition|'
                    r'remastered edition|'
                    r'anniversary edition|'
                    r'expanded edition|extended edition|'
                    r'bundle edition|'
                    r'digital edition|digital deluxe edition'
                    r')\b', re.IGNORECASE)

                def _deaccent(s):
                    for a, b in [('ō','oo'),('Ō','oo'),('ū','uu'),('Ū','uu'),
                                 ('ā','a'),('Ā','a'),('ē','e'),('Ē','e'),
                                 ('ī','i'),('Ī','i')]:
                        s = s.replace(a, b)
                    import unicodedata as _ud
                    s = _ud.normalize('NFKD', s)
                    s = ''.join(c for c in s if not _ud.combining(c))
                    s = s.lower()
                    # Normalize roman numerals to arabic (longest first to avoid partial matches)
                    for roman, arabic in [('viii','8'),('vii','7'),('vi','6'),('ix','9'),
                                          ('xii','12'),('xi','11'),('x','10'),
                                          ('iv','4'),('iii','3'),('ii','2'),('v','5'),('i','1')]:
                        s = re.sub(r'(?<![a-z0-9])' + roman + r'(?![a-z0-9])', arabic, s)
                    return s
                def _strip_editions(s):
                    s = _EDITION_RE.sub('', s)
                    s = re.sub(r'[\-:]\s*(the|a|an)\s*[\-:]', ':', s, flags=re.IGNORECASE)
                    s = re.sub(r'[\-:]\s*(the|a|an)\s*$', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'[\s\-:]+$', '', s)
                    return re.sub(r'\s{2,}', ' ', s).strip()

                def _tokenize(s):
                    s = _deaccent(_strip_editions(s))
                    s = re.sub(r'[:\-\u00b7\u2013\u2014,\'\"()!]', ' ', s)
                    return set(re.findall(r'[a-z0-9]+', s))

                def _normalize_str(s):
                    n = re.sub(r'[^a-z0-9]', '', _deaccent(_strip_editions(s)))
                    return _TITLE_ALIASES.get(n, n)

                def _jaccard(a, b):
                    if a == b: return 1.0
                    ta, tb = _tokenize(a), _tokenize(b)
                    if not ta or not tb: return 0.0
                    return len(ta & tb) / len(ta | tb)

                def _fuzzy(a, b):
                    if a == b: return 1.0
                    na, nb = _normalize_str(a), _normalize_str(b)
                    if not na or not nb: return 0.0
                    from difflib import SequenceMatcher
                    return SequenceMatcher(None, na, nb).ratio()

                _STOPWORDS = {'a','an','the','of','in','on','at','to',
                              'for','and','or','is','it','vs'}

                def _content_tokens(s):
                    return _tokenize(s) - _STOPWORDS

                def _score(a, b):
                    base = 0.5 * _jaccard(a, b) + 0.5 * _fuzzy(a, b)
                    ta, tb = _content_tokens(a), _content_tokens(b)
                    if ta and tb:
                        shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
                        if shorter <= longer:
                            tok = next(iter(shorter)) if len(shorter) == 1 else None
                            specific = len(shorter) >= 2 or (tok and len(tok) >= 6)
                            if specific:
                                containment = 0.5 + 0.5 * (len(shorter) / len(longer))
                                return max(base, containment)
                    return base

                THRESHOLD = 0.50

                # Pre-build English/non-English entry pools once
                english_entries, nonenglish_entries = [], []
                for e in self.raw_file_entries:
                    parsed = parse_rom_filename(e[0])
                    if (parsed['countries'] & ENGLISH_COUNTRIES
                            or 'En' in parsed['languages']
                            or not parsed['countries']):
                        english_entries.append(e)
                    else:
                        nonenglish_entries.append(e)

                # Pre-compute normalised bare name for each entry (avoid re-doing per title)
                def _bare(fname):
                    base = os.path.splitext(fname)[0]
                    b = re.sub(r'\s*\([^)]*\)', '', base).strip()
                    return re.sub(r'\s*(Disc|Disk)\s*\d+', '', b, flags=re.IGNORECASE).strip()

                english_bare  = [(_bare(e[0]), e) for e in english_entries]
                nonenglish_bare = [(_bare(e[0]), e) for e in nonenglish_entries]



                def _norm_roman(s):
                    s = s.lower()
                    for roman, arabic in [('viii','8'),('vii','7'),('vi','6'),('ix','9'),
                                          ('iv','4'),('iii','3'),('ii','2'),('xi','11'),
                                          ('xii','12'),('xiii','13'),('xiv','14'),('xv','15'),
                                          ('xvi','16'),('xvii','17'),('xviii','18'),('xix','19'),
                                          ('xx','20'),('x','10')]:
                        s = re.sub(r'(?<![a-z0-9])' + roman + r'(?![a-z0-9])', arabic, s)
                    return s

                def _build_title_index(title_list):
                    """Build token->titles index for fast candidate lookup."""
                    from collections import defaultdict as _dd
                    idx = _dd(list)
                    for t in title_list:
                        words = re.sub(r'[^a-zA-Z0-9]', ' ', _norm_roman(t)).split()
                        for w in words:
                            if w.isdigit() and len(w) < 2: continue  # skip single digits
                            if (len(w) >= 3 or (w.isdigit() and len(w) >= 2)) and w not in _STOPWORDS:
                                idx[w].append(t)
                    return idx

                def _candidates(bare, idx, title_list):
                    words = re.sub(r'[^a-zA-Z0-9]', ' ', _norm_roman(bare)).split()
                    found = {}
                    for w in words:
                        if w.isdigit() and len(w) < 2: continue  # skip single digits
                        if len(w) >= 3 or (w.isdigit() and len(w) >= 2):
                            for t in idx.get(w, []):
                                found[t] = None
                    if not found:
                        return title_list
                    return list(found.keys())

                def _best_match(bare, title_list, idx=None):
                    if idx is None: idx = _build_title_index(title_list)
                    best_s, best_t = 0, None
                    for mt in _candidates(bare, idx, title_list):
                        s = _score(bare, mt)
                        if s > best_s:
                            best_s, best_t = s, mt
                    return best_s, best_t

                # ── Fetch + match pages ───────────────────────────────────────
                titles        = []           # all titles fetched so far (ordered by score)
                moby_groups   = {}           # title -> [entries]
                selected_fnames = set()
                _accum_bytes  = 0

                def _full_selection():
                    """Full 1G1R over all titles so far.
                    Returns (groups, ordered) where ordered is [(fname, size_bytes), ...]
                    in title-rank order, with no duplicates."""
                    groups = {t: [] for t in titles}
                    idx = _build_title_index(titles)
                    _total_moby = len(english_bare)
                    for _i, (bare, entry) in enumerate(english_bare):
                        self.root.after(0, lambda i=_i, t=_total_moby: self.lbl_top_n_status.config(
                            text=f'Matching ROMs... {i:,}/{t:,}', fg=YELLOW))
                        best_s, best_t = _best_match(bare, titles, idx)
                        if best_t and best_s >= THRESHOLD:
                            groups[best_t].append(entry)
                    still_unmatched = [t for t in titles if not groups[t]]
                    if still_unmatched:
                        ne_idx = _build_title_index(still_unmatched)
                        for t in still_unmatched:
                            for bare, entry in nonenglish_bare:
                                if _score(bare, t) >= THRESHOLD:
                                    groups[t].append(entry)
                                    break
                    ordered = []
                    seen    = set()
                    for mt in titles:
                        entries = groups.get(mt, [])
                        if not entries:
                            continue
                        variant_groups = {}
                        for entry in entries:
                            parsed = parse_rom_filename(entry[0])
                            inst = {
                                'filename':   entry[0],
                                'size':       entry[1],
                                'direct_url': entry[2] if len(entry) > 2 else None,
                                'countries':  parsed['countries'],
                                'languages':  parsed['languages'],
                                'attributes': parsed['attributes'],
                            }
                            key = re.sub(r'\s*\([^)]*\)', '', os.path.splitext(entry[0])[0]).strip()
                            variant_groups.setdefault(key, []).append(inst)
                        all_insts = [i for insts in variant_groups.values() for i in insts]
                        filtered  = [i for i in all_insts if not is_excluded(i)] or all_insts
                        best = select_best(filtered)
                        if not best:
                            continue
                        best_key = re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                          os.path.splitext(best['filename'])[0],
                                          flags=re.IGNORECASE).strip()
                        winning_discs = [i for i in all_insts
                                         if re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                                   os.path.splitext(i['filename'])[0],
                                                   flags=re.IGNORECASE).strip() == best_key]
                        for inst in winning_discs:
                            if inst['filename'] not in seen:
                                seen.add(inst['filename'])
                                ordered.append((inst['filename'],
                                                parse_size_bytes(inst.get('size', '0'))))
                    return groups, ordered

                base_url = f'https://www.mobygames.com/platform/{slug}/'
                for page in range(pages_needed):
                    if _filter_mode == 'top_n' and len(titles) >= _top_n:
                        break
                    url = base_url if page == 0 else f'{base_url}page:{page}/'
                    self._debug(f'Moby fetch page {page+1}: {url}')
                    self.root.after(0, lambda p=page:
                        self.lbl_top_n_status.config(
                            text=f'Fetching page {p+1}...', fg=YELLOW))
                    stop_early = False
                    seen_page  = set()
                    page_titles = []
                    _moby_cached = _url_fetch_cache.get(('html', url))
                    if _moby_cached:
                        page_text = _moby_cached[0]
                        self._debug(f'  Page {page+1}: cached')
                    else:
                        try:
                            r = scraper.get(url, timeout=(15, 30))
                        except Exception as ex:
                            self._debug(f'  Page {page+1} fetch error: {ex}')
                            break
                        if r.status_code != 200:
                            self._debug(f'HTTP {r.status_code} on page {page+1}')
                            break
                        page_text = r.text
                        _url_fetch_cache[('html', url)] = (page_text, None)
                    for row in _re.finditer(r'<tr>(.*?)</tr>', page_text, _re.DOTALL):
                        row_html = row.group(1)
                        t_m = _re.search(r'<a href="(?:https://www\.mobygames\.com)?/game/\d+/[^"]+/">([^<]+)</a>', row_html)
                        if not t_m: continue
                        t = _html.unescape(t_m.group(1).strip())
                        if not t or t in seen_page or t in titles: continue
                        if _filter_mode == 'min_score':
                            s_m = _re.search(r'class="mobyscore"[^>]*>\s*([\d.]+)', row_html)
                            if s_m:
                                score = float(s_m.group(1))
                                if score < _min_score:
                                    stop_early = True
                                    break
                        seen_page.add(t)
                        page_titles.append(t)
                        if _filter_mode == 'top_n' and len(titles) + len(page_titles) >= _top_n:
                            stop_early = True
                            break
                    self._debug(f'  Page {page+1}: {len(seen_page)} parsed, {len(titles)+len(page_titles)} total')

                    # Add new stripped titles (dedup against already-seen)
                    for raw_t in page_titles:
                        stripped = _strip_editions(raw_t)
                        if stripped and stripped not in moby_groups:
                            titles.append(stripped)
                            moby_groups[stripped] = []

                    if _filter_mode == 'max_size':
                        prev_count = len(selected_fnames)
                        moby_groups, ordered = _full_selection()
                        total = sum(sz for _, sz in ordered)
                        self._debug(f'  After page {page+1}: {len(ordered)} files, {format_size(total)}')
                        for fname, sz in ordered:
                            self._debug(f'    [Moby] {fname}  ({sz:,} B)')
                        if total > _max_size_bytes:
                            # Trim lowest-ranked files from end until under budget
                            while ordered and total > _max_size_bytes:
                                fname, sz = ordered.pop()
                                total -= sz
                                self._debug(f'  [Moby] TRIM: {fname}  ({sz:,} B)  now={format_size(total)}')
                            selected_fnames = {fname for fname, _ in ordered}
                            _accum_bytes = total
                            self._debug(f'  Budget reached after page {page+1}, stopping')
                            break
                        selected_fnames = {fname for fname, _ in ordered}
                        _accum_bytes = total
                        if len(selected_fnames) == prev_count and page > 0:
                            self._debug(f'  No new files matched on page {page+1}, stopping')
                            break

                    if not seen_page or stop_early:
                        break
                    time.sleep(1)

                if _filter_mode != 'max_size':
                    titles = titles[:_top_n]
                if not titles:
                    self.root.after(0, lambda: self.lbl_top_n_status.config(
                        text='No titles found — check platform or try again', fg=RED))
                    self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))
                    return
                self._debug(f'Moby: {len(titles)} titles fetched')

                if _filter_mode != 'max_size':
                    # ── Standard (non-max_size) matching ─────────────────────────
                    def _match_entries(entries):
                        scored = []
                        total = len(entries)
                        for i, entry in enumerate(entries):
                            if True:
                                self.root.after(0, lambda i=i, t=total: self.lbl_top_n_status.config(
                                    text=f'Matching ROMs... {i:,}/{t:,}', fg=YELLOW))
                            base_n = os.path.splitext(entry[0])[0]
                            bare = re.sub(r'\s*\([^)]*\)', '', base_n).strip()
                            bare = re.sub(r'\s*(Disc|Disk)\s*\d+', '', bare, flags=re.IGNORECASE).strip()
                            best_score, best_title = 0, None
                            for mt in titles:
                                s = _score(bare, mt)
                                if s > best_score:
                                    best_score, best_title = s, mt
                            scored.append((best_score, best_title, entry))
                        return scored

                    moby_groups = {t: [] for t in titles}
                    matched_titles = set()
                    for score, title, entry in _match_entries(english_entries):
                        if title and score >= THRESHOLD:
                            moby_groups[title].append(entry)
                            matched_titles.add(title)
                    self._debug(f'Moby matched: {len(matched_titles)}')

                    still_unmatched = [t for t in titles if not moby_groups[t]]
                    if still_unmatched and nonenglish_entries:
                        for score, title, entry in _match_entries(nonenglish_entries):
                            if title and title in still_unmatched and score >= THRESHOLD and not moby_groups[title]:
                                moby_groups[title].append(entry)

                    unmatched = [t for t in titles if not moby_groups[t]]
                    self._debug(f'Moby unmatched ({len(unmatched)}): {sorted(unmatched)[:20]!r}')

                    selected_fnames = set()
                    _accum_bytes    = 0
                    for mt, entries in moby_groups.items():
                        if not entries:
                            continue
                        variant_groups = {}
                        for entry in entries:
                            parsed = parse_rom_filename(entry[0])
                            inst = {
                                'filename':   entry[0],
                                'size':       entry[1],
                                'direct_url': entry[2] if len(entry) > 2 else None,
                                'countries':  parsed['countries'],
                                'languages':  parsed['languages'],
                                'attributes': parsed['attributes'],
                            }
                            key = re.sub(r'\s*\([^)]*\)', '', os.path.splitext(entry[0])[0]).strip()
                            variant_groups.setdefault(key, []).append(inst)
                        all_insts = [i for insts in variant_groups.values() for i in insts]
                        filtered = [i for i in all_insts if not is_excluded(i)]
                        if not filtered:
                            filtered = all_insts
                        best = select_best(filtered)
                        if not best:
                            continue
                        best_key = re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                          os.path.splitext(best['filename'])[0],
                                          flags=re.IGNORECASE).strip()
                        winning_discs = [i for i in all_insts
                                         if re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                                   os.path.splitext(i['filename'])[0],
                                                   flags=re.IGNORECASE).strip() == best_key]
                        for inst in winning_discs:
                            selected_fnames.add(inst['filename'])
                            sz = parse_size_bytes(inst.get('size', '0'))
                            _accum_bytes += sz
                            self._debug(f"  [Moby] {inst['filename']}  {inst.get('size','?')} ({sz:,} B)  running={format_size(_accum_bytes)}")
                else:
                    unmatched = [t for t in titles if not moby_groups.get(t)]

                self._debug(f'Moby 1G1R: {len(selected_fnames)} files selected, total={format_size(_accum_bytes)}')

                result, summary = self._apply_filter(self.raw_file_entries, 'All files')
                for title, data in result.items():
                    if data['selected']:
                        if data['selected']['filename'] not in selected_fnames:
                            data['selected'] = None
                # Force correct size for selected files — override whatever _apply_filter picked
                entry_map = {e[0]: e for e in self.raw_file_entries}
                for data in result.values():
                    if data['selected']:
                        fname = data['selected']['filename']
                        if fname in entry_map:
                            data['selected']['size'] = entry_map[fname][1]
                result_fnames = {d['selected']['filename'] for d in result.values() if d['selected']}
                for entry in self.raw_file_entries:
                    if entry[0] in selected_fnames and entry[0] not in result_fnames:
                        result[entry[0]] = {'selected': {'filename': entry[0], 'size': entry[1], 'direct_url': entry[2] if len(entry) > 2 else None}, 'non_english': False, 'instances': []}
                for mt in titles:
                    entries = moby_groups.get(mt, [])
                    if entries and not any(e[0] in selected_fnames for e in entries):
                        best_entry = entries[0]
                        result[f'__missing__{mt}'] = {
                            'selected': None, 'non_english': False,
                            'instances': [], '_dat_missing': True,
                            '_dat_fname': mt, '_dat_size': best_entry[1] if len(best_entry) > 1 else '',
                        }
                self.rom_dict    = result
                self.summary     = summary
                if _filter_mode == 'max_size':
                    self.summary['selected_bytes'] = _accum_bytes
                    self.summary['selected_size']  = format_size(_accum_bytes)
                self.dat_mode    = True
                self._top_n_mode = True
                self.root.after(0, self._analysis_done)
                n_matched  = len(titles) - len(unmatched)
                self.root.after(0, lambda nm=n_matched, nf=len(selected_fnames), nt=len(titles):
                    self.lbl_top_n_status.config(
                        text=f'{nf} ROMs selected — {nm}/{nt} titles matched',
                        fg=GREEN))
                self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))

            except Exception:
                import traceback
                tb = traceback.format_exc()
                self._debug(f'Moby fetch error:\n{tb}')
                self.root.after(0, lambda: self.lbl_top_n_status.config(
                    text='Fetch failed — see debug log', fg=RED))
                self.root.after(0, lambda: self.btn_fetch_top_n.config(state='normal'))

        threading.Thread(target=_do, daemon=True).start()


    def _apply_dat_mode(self):
        """Cross-reference DAT against fetched files using extension-stripped matching.
        Display uses fetched filenames. DAT only used for selection, not verification.
        """
        try:
            entries, dat_name = parse_dat_file(self.dat_path)
        except Exception as ex:
            messagebox.showerror('Error', f'Failed to parse DAT: {ex}')
            return

        # Build DAT lookup keyed by stripped name (no extension, lowercase)
        dat_lookup = {}
        for fname, size_str in entries:
            key = os.path.splitext(fname)[0].lower()
            dat_lookup[key] = (fname, size_str)

        # Build fetched lookup keyed by stripped name
        fetched_by_key = {}
        for entry in self.raw_file_entries:
            key = os.path.splitext(entry[0])[0].lower()
            fetched_by_key[key] = entry

        result      = {}
        total_bytes = 0
        found_count = 0
        found_bytes = 0
        miss_count  = 0
        miss_bytes  = 0

        # All fetched files — green if in DAT, grey if not
        for key, entry in fetched_by_key.items():
            fname    = entry[0]
            size_str = entry[1]
            url      = entry[2] if len(entry) > 2 else None
            in_dat   = key in dat_lookup
            size_b   = parse_size_bytes(size_str)
            total_bytes += size_b
            if in_dat:
                result[fname] = {
                    'selected':     {'filename': fname, 'size': size_str, 'direct_url': url},
                    'non_english':  False,
                    'instances':    [],
                    '_dat_missing': False,
                }
                found_count += 1
                found_bytes += size_b
            else:
                result[fname] = {
                    'selected':     None,
                    'non_english':  False,
                    'instances':    [],
                    '_dat_missing': False,
                    '_dat_unselected': True,
                }

        # DAT entries missing from fetch — show as red
        for key, (dat_fname, dat_size) in dat_lookup.items():
            if key not in fetched_by_key:
                size_b = parse_size_bytes_dat(dat_size)
                miss_count += 1
                miss_bytes += size_b
                result[f'__missing__{dat_fname}'] = {
                    'selected':     None,
                    'non_english':  False,
                    'instances':    [],
                    '_dat_missing': True,
                    '_dat_fname':   dat_fname,
                    '_dat_size':    dat_size,
                }

        self.rom_dict   = result
        self.dat_mode   = True
        self.summary    = {
            'total_titles':           len(fetched_by_key),
            'total_files':            len(fetched_by_key),
            'total_size':             format_size(total_bytes),
            'selected_titles':        found_count,
            'selected_size':          format_size(found_bytes),
            'selected_bytes':         found_bytes,
            'non_english_titles':     0,
            'non_english_size':       '0 B',
            'excluded_files':         miss_count,
            'excluded_size':          format_size(miss_bytes),
            'unselected_other_files': 0,
            'unselected_other_size':  '0 B',
            'unselected_titles':      miss_count,
        }
        self.page_title = dat_name
        self._analysis_done()

    def _apply_filter(self, file_entries: list, mode: str) -> tuple[dict, dict]:
        """Apply 1G1R/All filtering to raw file entries. Returns (rom_dict, summary)."""
        self._debug(f'[_apply_filter] start: {len(file_entries)} entries, mode={mode!r}')
        use_1g1r     = mode in ('1G1R', '1G1R English only')
        english_only = mode == '1G1R English only'

        rom_dict = defaultdict(list)
        for entry in sorted(file_entries, key=lambda x: x[0]):
            filename   = entry[0]
            size_str   = entry[1]
            direct_url = entry[2] if len(entry) > 2 else None
            parsed = parse_rom_filename(filename)
            if use_1g1r and parsed['attributes'] & EXCLUDE_ATTRIBUTES:
                continue
            if use_1g1r and re.search(
                    r'(?i)(\b(demo|cheats?)\b'
                    r'|^action replay\b'
                    r'|^gamepro\b'
                    r'|^gameshark\b'
                    r'|^ps2 kiosk\b'
                    r'|^psi2\b'
                    r'|^kiosk\b'
                    r'|^jampack\b'
                    r'|^play tv\b'
                    r'|^namco transmission\b'
                    r'|^electronic gaming monthly\b'
                    r'|^swap magic\b'
                    r'|^sharkport\b'
                    r'|^codebreaker\b'
                    r'|^codejunkies\b'
                    r'|^max drive\b'
                    r'|^max media\b'
                    r'|^max play\b'
                    r'|^mega memory\b'
                    r'|^memory manager\b'
                    r'|^dvd region\b'
                    r'|^playstation experience\b'
                    r'|^play -\b'
                    r'|^play the best\b'
                    r')', parsed['title']):
                continue
            group_key = normalize_title(parsed['title'])
            rom_dict[group_key].append({
                'filename':   filename,
                'size':       size_str,
                'direct_url': direct_url,
                'countries':  parsed['countries'],
                'languages':  parsed['languages'],
                'attributes': parsed['attributes'],
            })

        self._debug(f'[_apply_filter] grouped into {len(rom_dict)} titles')
        result                 = {}
        total_all_bytes        = 0
        total_all_files        = 0
        selected_bytes         = 0
        selected_count         = 0
        non_english_bytes      = 0
        non_english_count      = 0
        excluded_bytes         = 0
        excluded_files         = 0
        unselected_other_bytes = 0
        unselected_other_count = 0

        _filter_total = len(rom_dict)
        _filter_count = 0
        for title, instances in rom_dict.items():
            _filter_count += 1
            if _filter_count % 100 == 0 or _filter_count == _filter_total:
                self._debug(f'[_apply_filter] {_filter_count}/{_filter_total}: {title!r}')
                self.root.after(0, lambda c=_filter_count, t=_filter_total:
                    self.setup_status.config(
                        text=f'Filtering {c}/{t} titles…', fg=YELLOW))
            for inst in instances:
                total_all_bytes += parse_size_bytes(inst['size'])

            if use_1g1r:
                selected    = select_best(instances)
                non_english = is_non_english(instances)
                is_translated = False
                if english_only and selected:
                    sel_inst = next(
                        (i for i in instances if i['filename'] == selected['filename']), None)
                    if sel_inst:
                        has_en = ('En' in sel_inst['languages'] or
                                  bool(sel_inst['countries'] & ENGLISH_COUNTRIES))
                        if not has_en:
                            selected = None
            else:
                non_english = False
                selected    = None

            if use_1g1r:
                if selected:
                    selected_count += 1
                    selected_bytes += parse_size_bytes(selected['size'])
                if non_english:
                    non_english_count += 1
                    for inst in instances:
                        non_english_bytes += parse_size_bytes(inst['size'])
                else:
                    for inst in instances:
                        if is_excluded(inst):
                            excluded_files += 1
                            excluded_bytes += parse_size_bytes(inst['size'])
                if selected and not non_english:
                    for inst in instances:
                        if inst['filename'] != selected['filename'] and not is_excluded(inst):
                            unselected_other_bytes += parse_size_bytes(inst['size'])
                            unselected_other_count += 1

                # Find direct_url for selected
                sel_entry = None
                if selected:
                    for inst in instances:
                        if inst['filename'] == selected['filename']:
                            sel_entry = {'filename': inst['filename'],
                                         'size':     inst['size'],
                                         'direct_url': inst.get('direct_url')}
                            break
                # Exclude locally-owned files from all automatic mode selection
                if sel_entry and self._is_locally_owned(sel_entry['filename']):
                    self._debug(f'[locally_owned] skipping {sel_entry["filename"]!r}')
                    sel_entry = None
                    if selected_count > 0:
                        selected_count -= 1
                    selected_bytes -= parse_size_bytes(selected.get('size', '0'))
                # If selected via fan translation, mark as translated for blue tag
                if sel_entry:
                    sel_inst = next((i for i in instances
                                     if i['filename'] == sel_entry['filename']), None)
                    if sel_inst and is_english_fan_translation(sel_inst):
                        is_translated = True
                result[title] = {
                    'selected':    sel_entry,
                    'non_english': non_english,
                    'translated':  is_translated,
                    'instances':   instances,
                }
            else:
                for inst in instances:
                    if not is_excluded(inst) and not self._is_locally_owned(inst['filename']):
                        key = inst['filename']
                        result[key] = {
                            'selected':    {'filename':   inst['filename'],
                                            'size':       inst['size'],
                                            'direct_url': inst.get('direct_url')},
                            'non_english': False,
                            'instances':   [inst],
                        }
                        selected_count += 1
                        selected_bytes += parse_size_bytes(inst['size'])
                    else:
                        excluded_files += 1
                        excluded_bytes += parse_size_bytes(inst['size'])

        # ── Post-process: deselect non-English titled entries covered by superset ──
        if use_1g1r:
            self.root.after(0, lambda: self.setup_status.config(
                text='Post-processing language coverage…', fg=YELLOW))
            # Build sel_langs: title -> combined lang+country set (O(1) lookup)
            sel_langs = {}
            for title, data in result.items():
                if data['selected']:
                    inst = next((i for i in data['instances']
                                 if i['filename'] == data['selected']['filename']), None)
                    if inst:
                        sel_langs[title] = inst['languages'] | inst['countries']
            # Union of all selected langs for fast pre-check before inner loop
            all_selected_langs: set = set()
            for langs in sel_langs.values():
                all_selected_langs |= langs

            for title, data in result.items():
                if not data['selected']:
                    continue
                inst = next((i for i in data['instances']
                             if i['filename'] == data['selected']['filename']), None)
                if not inst:
                    continue
                base_title = title.split('(')[0].strip()
                if not has_non_english_article(base_title):
                    continue
                my_langs = inst['languages'] | inst['countries']
                # Fast pre-check: skip inner loop if not a possible subset
                if not my_langs <= all_selected_langs:
                    continue
                for other_title, other_all in sel_langs.items():
                    if other_title == title:
                        continue
                    if my_langs <= other_all:
                        data['selected'] = None
                        data['translated'] = True
                        break

        summary = {
            'total_titles':           len(rom_dict),
            'total_files':            total_all_files,
            'total_size':             format_size(total_all_bytes),
            'selected_titles':        selected_count,
            'selected_size':          format_size(selected_bytes),
            'selected_bytes':         selected_bytes,
            'non_english_titles':     non_english_count,
            'non_english_size':       format_size(non_english_bytes),
            'excluded_files':         excluded_files,
            'excluded_size':          format_size(excluded_bytes),
            'unselected_other_files': unselected_other_count,
            'unselected_other_size':  format_size(unselected_other_bytes),
            'unselected_titles':      len(rom_dict) - selected_count,
        }
        self._debug(f'[_apply_filter] done: {len(result)} result entries')
        return result, summary

    def _refresh_analysis_table(self):
        self._populate_analysis()

    _URL_PLATFORM_KEYWORDS = {
        'playstation-3': 'Sony PlayStation 3', 'ps3': 'Sony PlayStation 3',
        'playstation-2': 'Sony PlayStation 2', 'ps2': 'Sony PlayStation 2',
        'playstation-vita': 'Sony PlayStation Vita', 'psvita': 'Sony PlayStation Vita',
        'nintendo-switch': 'Nintendo Switch', 'switch': 'Nintendo Switch',
        'nintendo-3ds': 'Nintendo 3DS', '3ds': 'Nintendo 3DS',
        'wii-u': 'Nintendo Wii U', 'wiiu': 'Nintendo Wii U',
        'xbox-360': 'Microsoft Xbox 360', 'xbox360': 'Microsoft Xbox 360',
    }

    def _update_donate(self):
        urls = self.url_text.get('1.0', 'end').strip().splitlines()
        first = next((u.strip() for u in urls if u.strip()), '')
        # Auto-detect platform from URL and set compat emulator
        if first:
            url_lower = first.lower()
            for kw, platform in self._URL_PLATFORM_KEYWORDS.items():
                if kw in url_lower:
                    self._auto_set_compat_emulator(platform)
                    break
        is_ia = 'archive.org' in first and not is_lolroms_url(first) and not is_minerva_url(first)
        # Show torrent warning only for Minerva sources (below donate button)
        if hasattr(self, 'lbl_torrent_warning'):
            if is_minerva_url(first):
                self.lbl_torrent_warning.pack(pady=(4, 0))
            else:
                self.lbl_torrent_warning.pack_forget()
        # Show S3 keys only for archive.org sources (below destination frame)
        if hasattr(self, 'cred_frame') and hasattr(self, '_cred_frame_anchor'):
            if is_ia:
                self.cred_frame.pack(fill='x', padx=16, pady=4,
                                     after=self._cred_frame_anchor)
            else:
                self.cred_frame.pack_forget()
        if is_lolroms_url(first):
            text = 'Donate to lolroms.com'
            url  = 'https://www.paypal.com/donate/?hosted_button_id=EG4YN6QGHCB6C'
        elif is_minerva_url(first):
            text = 'Pay Respects to Myrient'
            url  = 'https://minerva-archive.org/memorial/'
        elif is_ia:
            text = 'Donate to the Internet Archive'
            url  = 'https://archive.org/donate'
        else:
            self.btn_donate.config(text='', command=None)
            return
        self.btn_donate.config(text=text,
                               command=lambda: __import__('webbrowser').open(url))



    def _goget_or_reset(self):
        if self.btn_analyse.cget('text') == 'GoGet!':
            self._start_analysis()
        else:
            self._reset()

    def _reset(self):
        """Save settings and restart the Python process from scratch."""
        if self.dl_running:
            if not messagebox.askokcancel('Restart', 'Download in progress. Restart anyway?'):
                return
        self._save_settings()
        # Kill any aria2c processes before restarting
        for proc in list(getattr(self, '_aria2c_procs', [])):
            try: proc.kill()
            except: pass
        import subprocess
        subprocess.Popen([sys.executable] + sys.argv,
                         creationflags=0x08000000 if os.name == 'nt' else 0)
        self.root.destroy()
        os._exit(0)

    def _start_analysis(self):
        # Warm the exclude cache before analysis so _is_locally_owned works in threads
        self._build_exclude_titles()
        # ── URL fetch — always, regardless of mode ────────────────────────────
        _raw_lines = [u.strip() for u in self.url_text.get('1.0', 'end').splitlines() if u.strip()]
        urls      = [l for l in _raw_lines if not os.path.isdir(l)]
        dir_lines = [l for l in _raw_lines if os.path.isdir(l)]
        if not urls and not dir_lines and not self.local_source.get().strip():
            messagebox.showerror('Error', 'Please enter at least one URL or local directory.')
            return
        if not self.dest_dir.get():
            messagebox.showerror('Error', 'Please select a destination folder.')
            return

        access = self.access.get() or None
        secret = self.secret.get() or None

        # Reset mode if any URL needs a fresh fetch, or if running local-only
        if any((url, access, secret) not in _url_fetch_cache for url in urls) or not urls:
            self.mode.set('None')
            self._on_mode_change()
        self._fetch_cancel.clear()
        self._save_settings()
        self.dat_mode    = False
        self.setup_status.config(text='Fetching...', fg=YELLOW)
        self.lbl_analysis_title.config(text='Fetching…', fg=YELLOW)
        self.btn_analyse.config(text='Reset', bg=RED, fg=FG)
        self.root.update()
        mode = self.mode.get()
        # DAT and None modes fetch as All files, then apply their filter after
        effective_mode = 'All files' if mode in ('None', 'DAT file', 'Top N') else mode



        def run():
            try:
                file_entries = []
                page_title   = None
                total_urls   = len(urls)

                # ── Fetch ROM listings (parallel) ─────────────────────────────
                results_by_index = {}
                fetch_lock = threading.Lock()
                completed  = [0]

                def fetch_one(i, url):
                    if self._fetch_cancel.is_set():
                        return
                    self._debug(f"Fetching ({i}/{total_urls}): {url}")
                    for attempt in range(1, 4):
                        try:
                            entries, title = fetch_url_cached(url, access, secret)
                            self._debug(f"OK ({i}/{total_urls}) — {len(entries)} files, title={title!r}")
                            with fetch_lock:
                                results_by_index[i] = (entries, title)
                                completed[0] += 1
                                c = sum(len(r[0]) for r in results_by_index.values())
                                done = completed[0]
                            self.root.after(0, lambda done=done, c=c:
                                self.setup_status.config(
                                    text=f'Done {done}/{total_urls} -- {c} files so far', fg=YELLOW))
                            self.root.after(0, lambda done=done, c=c:
                                self.lbl_analysis_title.config(
                                    text=f'Fetching {done}/{total_urls}  —  {c:,} files…', fg=YELLOW))
                            return
                        except Exception as ex:
                            self._debug(f"Attempt {attempt}/3 FAILED ({i}/{total_urls}): {type(ex).__name__}: {ex}")
                            if attempt == 3:
                                self.root.after(0, lambda u=url, i=i:
                                    self.setup_status.config(
                                        text=f'FAILED: {u}', fg=RED))
                            else:
                                time.sleep(2)

                if total_urls > 0:
                    with ThreadPoolExecutor(max_workers=min(total_urls, 8)) as ex:
                        futures = [ex.submit(fetch_one, i, url) for i, url in enumerate(urls, 1)]
                        for f in as_completed(futures):
                            f.result()

                if self._fetch_cancel.is_set():
                    return

                # Merge results in original URL order
                file_entries = []
                page_title   = None
                for i in range(1, total_urls + 1):
                    if i in results_by_index:
                        entries, title = results_by_index[i]
                        file_entries.extend(entries)
                        if title and page_title is None:
                            page_title = title
                    else:
                        self.root.after(0, lambda i=i: self.setup_status.config(
                            text=f'Fetch failed for URL {i} — check debug log.', fg=RED))
                        self.root.after(0, lambda: self.btn_analyse.config(state='normal'))
                        return


                # ── Merge inline dir_lines from URL input ────────────────
                for _dline in dir_lines:
                    self.root.after(0, lambda d=_dline: self.setup_status.config(
                        text=f'Scanning {d}...', fg=YELLOW))
                    _dline_entries = {}
                    _recursive = self.recursive_scan.get()
                    if _recursive:
                        for _root, _dirs, _files in os.walk(_dline):
                            for _fname in _files:
                                _fpath = os.path.join(_root, _fname)
                                if not os.path.isfile(_fpath):
                                    continue
                                _sz = format_size(os.path.getsize(_fpath))
                                _dline_entries[_fname] = (_fname, _sz, None)
                    else:
                        for _fname in os.listdir(_dline):
                            _fpath = os.path.join(_dline, _fname)
                            if os.path.isfile(_fpath):
                                _sz = format_size(os.path.getsize(_fpath))
                                _dline_entries[_fname] = (_fname, _sz, None)
                    self._debug(f'Dir line {repr(_dline)}: {len(_dline_entries)} files, listdir={os.listdir(_dline)[:5]}')
                    for _fname, _entry in _dline_entries.items():
                        if not any(e[0] == _fname for e in file_entries):
                            file_entries.append(_entry)

                # Store raw entries for live re-filtering on mode change
                # ── Merge local source dir ───────────────────────────────────
                local_source = self.local_source.get().strip()
                if local_source and os.path.isdir(local_source):
                    # Use cached scan if path unchanged
                    _cache = getattr(self, '_local_source_cache', None)
                    if _cache and _cache[0] == local_source:
                        local_entries = _cache[1]
                        self._debug(f"Local source: {len(local_entries)} files (cached)")
                    else:
                        self.root.after(0, lambda: self.setup_status.config(
                            text='Scanning local source dir...', fg=YELLOW))
                        self._debug(f"Scanning local source: {local_source}")
                        local_entries = {}
                        for fname in os.listdir(local_source):
                            fpath = os.path.join(local_source, fname)
                            if os.path.isfile(fpath):
                                size_bytes = os.path.getsize(fpath)
                                local_entries[fname] = (fname, format_size(size_bytes), None, True)
                        # If no files found, scan subdirectories
                        if not local_entries:
                            self._debug(f"No files in root, scanning subdirs of {local_source}")
                            for root, dirs, files in os.walk(local_source):
                                for fname in files:
                                    fpath = os.path.join(root, fname)
                                    if not os.path.isfile(fpath):
                                        continue
                                    size_bytes = os.path.getsize(fpath)
                                    local_entries[fname] = (fname, format_size(size_bytes), None, True)
                        self._local_source_cache = (local_source, local_entries)
                        self._debug(f"Local source: {len(local_entries)} files found")
                    # Merge: local preferred, then remote for anything not in local
                    remote_by_name = {e[0]: e for e in file_entries}
                    merged = []
                    for fname, entry in local_entries.items():
                        merged.append(entry[:3])  # (fname, size_str, None)
                    for e in file_entries:
                        if e[0] not in local_entries:
                            merged.append(e)
                    self._debug(f"Merged: {len(local_entries)} local + {len(merged)-len(local_entries)} remote = {len(merged)} total")
                    file_entries = merged

                # Deduplicate by filename — same file appearing in multiple URLs
                seen = set()
                deduped = []
                for e in file_entries:
                    if e[0] not in seen:
                        seen.add(e[0])
                        deduped.append(e)
                if len(deduped) < len(file_entries):
                    self._debug(f'Deduped {len(file_entries) - len(deduped)} duplicate filenames')
                file_entries = deduped

                # Strip non-game files globally before anything else sees them
                file_entries = [
                    e for e in file_entries
                    if os.path.splitext(e[0])[1].lower() not in NON_GAME_EXTS
                ]
                self.raw_file_entries = file_entries
                self.page_title       = page_title
                self.dat_mode         = False
                self._debug(f'[ANALYSIS] {len(file_entries)} files after dedup, mode={mode!r}, urls={len(urls)}, dir_lines={len(dir_lines)}, local_source={repr(local_source)}')

                if mode == 'DAT' and self.dat_path:
                    self.root.after(0, self._apply_dat_mode)
                elif mode in ('None', 'Top N') and (urls or not (dir_lines or local_source)):
                    # Show all files unselected — user must apply filter manually
                    result, summary = self._apply_filter(file_entries, 'All files')
                    for data in result.values():
                        if data['selected']:
                            data['_prev_selected'] = dict(data['selected'])
                            data['selected'] = None
                    summary['selected_titles'] = 0
                    self.rom_dict  = result
                    self.summary   = summary
                    self.root.after(0, self._analysis_done)
                else:
                    result, summary   = self._apply_filter(file_entries, effective_mode)
                    self.rom_dict     = result
                    self.summary      = summary
                    self.root.after(0, self._analysis_done)

            except Exception:
                import traceback
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._analysis_error(tb))

        threading.Thread(target=run, daemon=True).start()

    def _analysis_error(self, msg: str):
        self.setup_status.config(text='Error -- see popup', fg=RED)
        dlg = tk.Toplevel(self.root)
        dlg.title('Error')
        dlg.configure(bg=BG)
        dlg.resizable(True, True)
        dlg.geometry('700x300')
        tk.Label(dlg, text='An error occurred. You can select and copy the text below:',
                 bg=BG, fg=FG2, font=FONT_SM).pack(anchor='w', padx=12, pady=(10, 4))
        txt = tk.Text(dlg, bg=BG2, fg=RED, font=FONT_SM, wrap='word',
                      relief='flat', borderwidth=4)
        txt.pack(fill='both', expand=True, padx=12, pady=4)
        txt.insert('1.0', msg)
        txt.config(state='normal')
        sb = tk.Scrollbar(txt)
        txt.config(yscrollcommand=sb.set)
        tk.Button(dlg, text='Close', bg=BG3, fg=FG, font=FONT,
                  relief='flat', padx=16, command=dlg.destroy).pack(pady=8)
        dlg.transient(self.root)
        dlg.grab_set()

    def _analysis_done(self):
        self.setup_status.config(text='Building list…', fg=YELLOW)
        mode = self.mode.get()
        total = self.summary.get('total_files', 0)
        self.lbl_analysis_title.config(text='Analysis Results', fg=FG)
        if self.dat_mode:
            self.lbl_list_title.config(text='DAT selection:')
        elif mode == '1G1R English only':
            self.lbl_list_title.config(text='Selected titles (1G1R — English only):')
        elif mode == '1G1R':
            self.lbl_list_title.config(text='Selected titles (1G1R):')
        elif mode == 'None':
            self.lbl_list_title.config(text='No files selected:')
        elif mode == 'Top N':
            src = getattr(self, 'top_n_source', tk.StringVar()).get()
            self.lbl_list_title.config(text=f'Top N — {src} (1G1R):')
        else:
            self.lbl_list_title.config(text='All titles (no filter):')

        # Hash not available for lolroms — force to Size or Name
        has_lolroms = any(
            is_lolroms_url(d['selected'].get('direct_url') or '')
            for d in self.rom_dict.values() if d['selected']
        )
        if has_lolroms:
            if self.verify_mode.get() == 'Hash':
                self.verify_mode.set('Size')
            self.verify_combo.config(values=['Name', 'Size', 'Overwrite'], state='readonly')
        else:
            self.verify_combo.config(values=['Hash', 'Size', 'Name', 'Overwrite'], state='readonly')

        self._populate_analysis()
        self._compat_prepopulate()
        self.nb.select(self._nb_tab_analysis)

        # Switch Download button for Minerva sources
        urls = [u.strip() for u in self.url_text.get('1.0', 'end').splitlines() if u.strip()]
        if any(is_minerva_url(u) for u in urls):
            self.btn_download.config(text='Download', command=self._go_to_download)
        else:
            self.btn_download.config(text='Download', command=self._go_to_download)


    # ── Analysis tab ──────────────────────────────────────────────────────────

    def _build_analysis(self):
        f   = self.tab_analysis
        PAD = 16

        _title_row = tk.Frame(f, bg=BG)
        _title_row.pack(fill='x', padx=PAD, pady=(PAD, 8))
        self.lbl_analysis_title = tk.Label(_title_row, text='Analysis Results', bg=BG, fg=FG,
                 font=FONT_XL)
        self.lbl_analysis_title.pack(side='left')
        tk.Label(_title_row, text='click cards to filter list',
                 bg=BG, fg='#555555', font=FONT_SM).pack(side='right')
        self.card_frame = tk.Frame(f, bg=BG)
        self.card_frame.pack(fill='x', padx=PAD)

        list_frame = tk.Frame(f, bg=BG, padx=PAD, pady=8)
        list_frame.pack(fill='both', expand=True)

        list_hdr = tk.Frame(list_frame, bg=BG)
        list_hdr.pack(fill='x', pady=(0, 2))
        self.lbl_list_title = tk.Label(list_hdr, text='Selected titles (1G1R):',
                                       bg=BG, fg=FG2, font=FONT_SM)
        self.lbl_list_title.pack(side='left', anchor='w')

        # Mode selector + DAT browse in one row
        MODE_OPTIONS = ['1G1R English only', '1G1R', 'All files', 'None', 'DAT', 'Top N']
        self.mode_combo = ttk.Combobox(
            list_hdr, textvariable=self.mode,
            values=MODE_OPTIONS, state='readonly',
            font=FONT_SM, width=18,
        )
        self.mode_combo.pack(side='right', padx=(4, 0))
        tk.Label(list_hdr, text='Mode:', bg=BG, fg=FG,
                 font=FONT_LG).pack(side='right')
        self.mode_combo.bind('<<ComboboxSelected>>', self._on_mode_change)

        # DAT filename label below header
        self.dat_file_label = tk.Label(list_frame, text='', bg=BG, fg=GREEN, font=FONT_SM)
        self.dat_file_label.pack(anchor='e', pady=(0, 2))

        self.lbl_dat_group_status = tk.Label(list_frame, text='', bg=BG, fg=YELLOW, font=FONT_SM)
        # (packed dynamically before dat_group_frame when shown)

        # ── DAT Group panel (shown only in DAT Group mode) ────────────────────
        self.dat_group_frame = tk.LabelFrame(list_frame, text=' DAT Group ', bg=BG, fg=FG2,
                                             font=FONT_SM, padx=8, pady=6)
        dg_inner = tk.Frame(self.dat_group_frame, bg=BG)
        dg_inner.pack(fill='x')

        # Left column — buttons, dropdown, fetch
        dg_left = tk.Frame(dg_inner, bg=BG)
        dg_left.pack(side='left', fill='y', padx=(0, 8))

        dg_btn_row = tk.Frame(dg_left, bg=BG)
        dg_btn_row.pack(anchor='w')
        tk.Button(dg_btn_row, text='Save', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._save_dat_group).pack(side='left', padx=(0, 2))
        tk.Button(dg_btn_row, text='Delete', bg=BG3, fg=RED, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._delete_dat_group).pack(side='left', padx=2)
        tk.Button(dg_btn_row, text='New', bg=BG3, fg=GREEN, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._new_dat_group).pack(side='left', padx=2)

        self.dat_group_var   = tk.StringVar()
        self.dat_group_combo = ttk.Combobox(dg_left, textvariable=self.dat_group_var,
                                            font=FONT_SM, width=20)
        self.dat_group_combo.pack(anchor='w', pady=(4, 0))
        self.dat_group_combo.bind('<<ComboboxSelected>>', self._load_dat_group)

        # Spacer pushes fetch to bottom
        tk.Frame(dg_left, bg=BG).pack(fill='y', expand=True)

        dg_fetch_bottom = tk.Frame(dg_left, bg=BG)
        dg_fetch_bottom.pack(anchor='e', pady=(4, 0))
        self.btn_fetch_dat_group = tk.Button(dg_fetch_bottom, text='Fetch & Apply', bg=ACC, fg=FG,
                                             font=FONT_SM, relief='flat', padx=10,
                                             command=self._fetch_dat_group)
        self.btn_fetch_dat_group.pack(side='left')

        # Right column — text area spans full height
        dg_right = tk.Frame(dg_inner, bg=BG)
        dg_right.pack(side='left', fill='both', expand=True)
        tk.Label(dg_right, text='DAT URL or local file path (one per line):',
                 bg=BG, fg=FG2, font=FONT_SM).pack(anchor='w')
        dg_text_row = tk.Frame(dg_right, bg=BG)
        dg_text_row.pack(fill='both', expand=True)
        self.dat_group_text = tk.Text(dg_text_row, bg=BG2, fg=FG, font=FONT_SM,
                                      height=4, insertbackground=FG, relief='flat', borderwidth=4)
        self.dat_group_text.pack(side='left', fill='both', expand=True)
        tk.Button(dg_text_row, text='Browse', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._browse_dat).pack(side='left', anchor='n', padx=(4, 0))

        self._refresh_dat_group_combo()

        # ── Top N unified panel ──────────────────────────────────────────────
        self.top_n_frame = tk.LabelFrame(list_frame, text=' Top N ',
                                         bg=BG, fg=FG2, font=FONT_SM, padx=8, pady=6)

        # Row 1: source dropdown + dynamic controls
        top_n_row = tk.Frame(self.top_n_frame, bg=BG)
        top_n_row.pack(fill='x')

        ttk.Combobox(top_n_row, textvariable=self.top_n_source,
                     values=['RetroAchievements', 'IGDB', 'MobyGames', 'Screenscraper'],
                     state='readonly', font=FONT_SM, width=16
                     ).pack(side='left', padx=(0, 8))

        # Dynamic area — rebuilt by _on_top_n_source_change
        self.top_n_dynamic = tk.Frame(top_n_row, bg=BG)
        self.top_n_dynamic.pack(side='left')

        # Row 2: status
        self.lbl_top_n_status = tk.Label(self.top_n_frame, text='', bg=BG, fg=YELLOW, font=FONT_SM)
        self.lbl_top_n_status.pack(anchor='w')

        # Row 3: hint + Fetch & Apply button at bottom right
        bottom_row = tk.Frame(self.top_n_frame, bg=BG)
        bottom_row.pack(fill='x')
        self.lbl_top_n_hint = tk.Label(bottom_row, text='', bg=BG, fg='#555555', font=FONT_SM)
        self.lbl_top_n_hint.pack(side='left', anchor='w')
        self.btn_fetch_top_n = tk.Button(bottom_row, text='Fetch & Apply', bg=ACC, fg=FG,
                                         font=FONT_SM, relief='flat', padx=10,
                                         command=self._fetch_top_n)
        self.btn_fetch_top_n.pack(side='right')

        # Bind source change
        self.top_n_source.trace_add('write', lambda *_: self._on_top_n_source_change()
                                    if hasattr(self, 'top_n_dynamic') else None)

        # Pre-create platform vars (needed before _on_top_n_source_change)
        self.moby_platform_name = tk.StringVar(value=self.settings.get('moby_platform_name', ''))
        self.moby_platform_name.trace_add('write', lambda *_: self._auto_set_compat_emulator(self.moby_platform_name.get()))
        self.moby_platform_slug = tk.StringVar(value=self.settings.get('moby_platform_slug', ''))


        legend_row = tk.Frame(list_frame, bg=BG)
        self._legend_row = legend_row  # save ref for dat_group_frame positioning
        legend_row.pack(fill='x', pady=(4, 0))
        tk.Label(legend_row, text='Legend (click to cycle):',
                 bg=BG, fg='#555555', font=FONT_SM).pack(side='left', padx=(0, 6))
        for symbol, label, color, tag in [
            ('●', 'Selected',              GREEN,  'selected'),
            ('○', 'Unselected',            FG2,    'unselected'),
            ('✗', 'Non-English',           RED,    'nonenglish'),
            ('✗', 'Missing',                PURPLE, 'topn_missing'),
            ('⊘', 'Non-Game',              YELLOW, 'excluded'),
        ]:
            lbl = tk.Label(legend_row, text=f' {symbol} {label} ',
                           bg=BG, fg=color, font=FONT_SM, cursor='hand2')
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda e, t=tag: self._cycle_tag(t))
        tk.Label(legend_row, text='Double-click or Space to toggle',
                 bg=BG, fg='#666666', font=FONT_SM).pack(side='right', padx=(0, 4))

        # Search + Type filter on same row, each half width
        sf_row = tk.Frame(list_frame, bg=BG)
        sf_row.pack(fill='x', pady=(4, 4))

        # Search — left half
        search_half = tk.Frame(sf_row, bg=BG)
        search_half.pack(side='left', fill='x', expand=True, padx=(0, 8))
        tk.Label(search_half, text='Search:', bg=BG, fg=FG2,
                 font=FONT_SM).pack(side='left', padx=(0, 6))
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(search_half, textvariable=self.search_var,
                                bg=BG2, fg=FG, font=FONT_SM,
                                insertbackground=FG, relief='flat', borderwidth=4)
        search_entry.pack(side='left', fill='x', expand=True)
        tk.Button(search_half, text='✕', bg=BG3, fg=FG2, font=FONT_SM,
                  relief='flat', padx=6,
                  command=lambda: self.search_var.set('')).pack(side='left', padx=(4, 0))
        tk.Button(search_half, text='🕸', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6, pady=0, height=1,
                  command=self._select_only_visible).pack(side='left', padx=(4, 0))
        tk.Button(search_half, text='+', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=lambda: self._add_remove_visible(select=True)).pack(side='left', padx=(4, 0))
        tk.Button(search_half, text='-', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=lambda: self._add_remove_visible(select=False)).pack(side='left', padx=(4, 0))
        self.search_var.trace_add('write', lambda *_: self._apply_search())

        # Type filter — right half
        filter_half = tk.Frame(sf_row, bg=BG)
        filter_half.pack(side='left', fill='x', expand=True)
        tk.Label(filter_half, text='Type filter (or regex):', bg=BG, fg=FG2,
                 font=FONT_SM).pack(side='left', padx=(0, 6))
        self.filter_var = tk.StringVar()
        self.filter_entry = tk.Entry(filter_half, textvariable=self.filter_var,
                                bg=BG2, fg=FG, font=FONT_SM,
                                insertbackground=FG, relief='flat', borderwidth=4)
        self.filter_entry.pack(side='left', fill='x', expand=True)
        tk.Button(filter_half, text='✕', bg=BG3, fg=FG2, font=FONT_SM,
                  relief='flat', padx=6,
                  command=lambda: self.filter_var.set('')).pack(side='left', padx=(4, 0))
        tk.Button(filter_half, text='Apply', bg=ACC, fg=FG, font=FONT_SM,
                  relief='flat', padx=8,
                  command=self._apply_type_filter).pack(side='left', padx=(4, 0))
        self.filter_var.trace_add('write', lambda *_: self._preview_type_filter())

        # Style the treeview
        style = ttk.Style()
        style.configure('Analysis.Treeview',
                        background=BG2, foreground=FG, fieldbackground=BG2,
                        font=FONT_SM, rowheight=20)
        style.configure('Analysis.Treeview.Heading',
                        background=BG3, foreground=FG, font=FONT_SM)
        style.map('Analysis.Treeview',
                  background=[('selected', ACC)],
                  foreground=[('selected', FG)])

        tree_frame = tk.Frame(list_frame, bg=BG)
        tree_frame.pack(fill='both', expand=True)
        sb = tk.Scrollbar(tree_frame)
        sb.pack(side='right', fill='y')

        self.title_list = ttk.Treeview(
            tree_frame, style='Analysis.Treeview',
            columns=('status', 'filename', 'size'),
            show='headings',
            yscrollcommand=sb.set,
        )
        self.title_list.heading('status',   text='',         anchor='w')
        self.title_list.heading('filename', text='Filename', anchor='w',
                                command=lambda: self._sort_analysis('filename'))
        self.title_list.heading('size',     text='Size',     anchor='w',
                                command=lambda: self._sort_analysis('size'))
        self.title_list.column('status',   width=28,  stretch=False, anchor='w')
        self.title_list.column('filename', width=600, stretch=True,  anchor='w')
        self.title_list.column('size',     width=80,  stretch=False, anchor='e')

        # Tag colours
        self.title_list.tag_configure('selected',    foreground=GREEN)
        self.title_list.tag_configure('deselected',  foreground='#555555')
        self.title_list.tag_configure('unselected',  foreground=FG2)
        self.title_list.tag_configure('nonenglish',  foreground=RED)
        self.title_list.tag_configure('topn_missing', foreground=PURPLE)
        self.title_list.tag_configure('excluded',    foreground=YELLOW)
        self.title_list.tag_configure('filtered',    foreground='#444444')
        self.title_list.tag_configure('translated',    foreground='#4488ff')
        self.title_list.tag_configure('locally_owned', foreground='#4a9eff')

        self.title_list.pack(fill='both', expand=True)
        sb.config(command=self.title_list.yview)
        self.lbl_sel_match_count = tk.Label(f, text='', bg=BG, fg=FG2, font=FONT_SM)
        self.lbl_sel_match_count.pack(anchor='e', padx=PAD)
        self._analysis_sort_col = 'filename'
        self._analysis_sort_rev = False
        self.title_list.bind('<Double-Button-1>', self._on_analysis_click)
        self.title_list.bind('<space>', self._on_analysis_click)

        tk.Label(f, text='Run compatibility check or skip straight to download:',
                 bg=BG, fg='#555555', font=FONT_SM).pack(pady=(PAD, 2))
        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(pady=(0, PAD))
        tk.Button(btn_row, text='Compatibility', bg=ACC, fg=FG, font=FONT_LG,
                  relief='flat', padx=20, pady=8,
                  command=lambda: self.nb.select(self._nb_tab_compat)).pack(side='left', padx=(0, 8))
        self.btn_download = tk.Button(btn_row, text='Download', bg=ACC, fg=FG, font=FONT_LG,
                  relief='flat', padx=20, pady=8,
                  command=self._go_to_download)
        self.btn_download.pack(side='left', padx=(0, 8))
        tk.Button(btn_row, text='Export DAT', bg=BG3, fg=FG, font=FONT_LG,
                  relief='flat', padx=20, pady=8,
                  command=self._export_dat).pack(side='left')

    def _fname_to_romdata(self):
        """Return a dict mapping filename -> (rom_dict_key, data) for fast lookup."""
        mapping = {}
        for key, data in self.rom_dict.items():
            for inst in data.get('instances', []):
                mapping[inst['filename']] = (key, data)
            if key not in mapping:
                mapping[key] = (key, data)
        return mapping

    def _add_remove_visible(self, select: bool):
        """Add (+) or remove (-) visible rows without touching non-visible selection state."""
        if not self.rom_dict:
            return
        fname_map = self._fname_to_romdata()
        for iid in list(self.title_list.get_children()):
            fname, _tag = self._all_tree_items.get(iid, ('', ''))
            if not fname:
                continue
            entry = fname_map.get(fname)
            if entry is None:
                continue
            _key, data = entry
            try:
                vals = list(self.title_list.item(iid, 'values'))
            except Exception:
                continue
            if not vals:
                continue
            size = vals[2] if len(vals) > 2 else ''
            if select:
                inst = next((i for i in data.get('instances', []) if i['filename'] == fname), None)
                data['selected'] = {'filename': fname, 'size': inst['size'] if inst else size, 'direct_url': inst.get('direct_url') if inst else None}
                self.title_list.item(iid, values=('●', fname, size), tags=('selected',))
                self._all_tree_items[iid] = (fname, 'selected')
            else:
                data['selected'] = None
                self.title_list.item(iid, values=('○', fname, size), tags=('deselected',))
                self._all_tree_items[iid] = (fname, 'deselected')
        self._populate_cards()
        self._compat_prepopulate()

    def _select_only_visible(self):
        """(🕸) Select visible rows, deselect everything else."""
        if not self.rom_dict:
            return
        fname_map = self._fname_to_romdata()
        visible = set(self.title_list.get_children())
        for iid, (fname, _tag) in list(self._all_tree_items.items()):
            if not fname:
                continue
            entry = fname_map.get(fname)
            if entry is None:
                continue
            _key, data = entry
            try:
                vals = self.title_list.item(iid, 'values')
            except Exception:
                continue
            if not vals:
                continue
            size = vals[2] if len(vals) > 2 else '?'
            if iid in visible:
                inst = next((i for i in data.get('instances', []) if i['filename'] == fname), None)
                data['selected'] = {'filename': fname, 'size': inst['size'] if inst else size, 'direct_url': inst.get('direct_url') if inst else None}
                self.title_list.item(iid, values=('●', fname, size), tags=('selected',))
                self._all_tree_items[iid] = (fname, 'selected')
            else:
                data['selected'] = None
                self.title_list.item(iid, values=('○', fname, size), tags=('deselected',))
                self._all_tree_items[iid] = (fname, 'deselected')
        self._populate_cards()
        self._compat_prepopulate()

    def _on_analysis_click(self, event):
        """Toggle a file in/out of the download queue on double-click or space."""
        # For keyboard events, use the current selection
        if event.type == tk.EventType.KeyPress:
            sel = self.title_list.selection()
            iid = sel[0] if sel else None
        else:
            region = self.title_list.identify_region(event.x, event.y)
            iid    = self.title_list.identify_row(event.y)
            if region != 'cell' or not iid:
                return
        tags = self.title_list.item(iid, 'tags')
        if not tags:
            return
        fname = self.title_list.set(iid, 'filename')
        size  = self.title_list.set(iid, 'size')

        # Block missing Top N rows (not in collection, can't be downloaded)
        _, cur_tag = self._all_tree_items.get(iid, ('', ''))
        if cur_tag in ('nonenglish', 'topn_missing') and not any(
                inst.get('filename') == fname
                for d in self.rom_dict.values()
                for inst in d.get('instances', [])):
            return

        # Check actual queue state from rom_dict — don't trust the tag
        currently_selected = any(
            d['selected'] and d['selected'].get('filename') == fname
            for d in self.rom_dict.values()
        )

        if currently_selected:
            # Dequeue it
            for data in self.rom_dict.values():
                if data['selected'] and data['selected'].get('filename') == fname:
                    data['_prev_selected'] = dict(data['selected'])
                    data['selected'] = None
                    break
            self.title_list.item(iid, values=('○', fname, size), tags=('deselected',))
            if iid in self._all_tree_items:
                self._all_tree_items[iid] = (fname, 'deselected')
        else:
            # Queue it — find the instance
            for data in self.rom_dict.values():
                matched = False
                for inst in data.get('instances', []):
                    if inst['filename'] == fname:
                        data['selected'] = {
                            'filename':   fname,
                            'size':       inst['size'],
                            'direct_url': inst.get('direct_url'),
                        }
                        matched = True
                        break
                if not matched:
                    prev = data.get('_prev_selected', {})
                    if prev.get('filename') == fname:
                        data['selected'] = prev
                        matched = True
                if matched:
                    break
            self.title_list.item(iid, values=('●', fname, size), tags=('selected',))
            if iid in self._all_tree_items:
                self._all_tree_items[iid] = (fname, 'selected')

        self.summary['selected_titles'] = sum(
            1 for d in self.rom_dict.values() if d['selected'])
        sel_bytes = sum(
            parse_size_bytes(d['selected'].get('size', '0'))
            for d in self.rom_dict.values() if d['selected'])
        self.summary['selected_bytes'] = sel_bytes
        self.summary['selected_size']  = format_size(sel_bytes)
        self._populate_cards()
        self._compat_prepopulate()

    def _cycle_tag(self, tag: str):
        """Jump to next visible row with the given tag, wrapping around."""
        iids = [iid for iid in self.title_list.get_children()
                if tag in self.title_list.item(iid, 'tags')]
        if not iids:
            return
        if not hasattr(self, '_cycle_pos'):
            self._cycle_pos = {}
        pos = self._cycle_pos.get(tag, 0) % len(iids)
        iid = iids[pos]
        self._cycle_pos[tag] = pos + 1
        self.title_list.selection_set(iid)
        self.title_list.see(iid)

    def _filter_tag(self, tag: str):
        """Toggle filter: show only rows with this tag, or restore all."""
        if not hasattr(self, '_active_tag_filter'):
            self._active_tag_filter = None
        if self._active_tag_filter == tag:
            self._active_tag_filter = None
            self._apply_search()
        else:
            self._active_tag_filter = tag
            for iid in self.title_list.get_children():
                if tag in self.title_list.item(iid, 'tags'):
                    self.title_list.reattach(iid, '', 'end')
                else:
                    self.title_list.detach(iid)
            children = self.title_list.get_children()
            if children:
                self.title_list.see(children[0])
            self._update_sel_match_count()

    def _populate_cards(self):
        """Refresh stat cards — selected count/size recalculated live from rom_dict."""
        for w in self.card_frame.winfo_children():
            w.destroy()
        s = self.summary

        # Recalculate selected live from rom_dict
        sel_count = 0
        sel_bytes = 0
        for data in self.rom_dict.values():
            if data['selected']:
                sel_count += 1
                size_str  = data['selected']['size']
                try:
                    sel_bytes += int(size_str)          # DAT mode — raw bytes
                except (ValueError, TypeError):
                    sel_bytes += parse_size_bytes(size_str)  # listing size string

        owned_count = sum(1 for iid, (_, tag) in self._all_tree_items.items() if tag == 'locally_owned')
        excl_dir_set = bool(self.exclude_dir.get().strip())
        self._make_card(self.card_frame, 'Total Titles', str(s['total_titles']),  FG)
        self._make_card(self.card_frame, 'Total Size',   s['total_size'],          FG)
        self._make_card(self.card_frame, 'Selected ROMs', str(sel_count),          GREEN,  command=lambda: self._filter_tag('selected'))
        self._make_card(self.card_frame, 'Selected Size', format_size(sel_bytes),  GREEN,  command=lambda: self._filter_tag('selected'))
        if excl_dir_set:
            owned_bytes = sum(
                parse_size_bytes(self.title_list.set(iid, 'size'))
                for iid, (_, tag) in self._all_tree_items.items()
                if tag == 'locally_owned')
            self._make_card(self.card_frame, 'Locally Owned',      str(owned_count),          '#4a9eff',
                            command=lambda: self._filter_tag('locally_owned'))
            self._make_card(self.card_frame, 'Locally Owned Size', format_size(owned_bytes),  '#4a9eff',
                            command=lambda: self._filter_tag('locally_owned'))
        if not self.dat_mode:
            self._make_card(self.card_frame, 'Non-English',      str(s['non_english_titles']), RED,    command=lambda: self._filter_tag('nonenglish'))
            self._make_card(self.card_frame, 'Non-English Size', s['non_english_size'],        RED,    command=lambda: self._filter_tag('nonenglish'))
            self._make_card(self.card_frame, 'Non-Game',         str(s['excluded_files']),     YELLOW, command=lambda: self._filter_tag('excluded'))
            self._make_card(self.card_frame, 'Non-Game Size',    s['excluded_size'],           YELLOW, command=lambda: self._filter_tag('excluded'))
        else:
            miss_count = sum(1 for d in self.rom_dict.values()
                             if d.get('_dat_missing') and not d.get('non_english'))
            ne_count = sum(1 for iid, (_, tag) in self._all_tree_items.items() if tag == 'nonenglish')
            ne_bytes = sum(parse_size_bytes(self.title_list.set(iid, 'size'))
                           for iid, (_, tag) in self._all_tree_items.items() if tag == 'nonenglish')
            miss_bytes = 0  # missing titles have no size
            self._make_card(self.card_frame, 'Non-English',      str(ne_count),          RED,    command=lambda: self._filter_tag('nonenglish'))
            self._make_card(self.card_frame, 'Non-English Size', format_size(ne_bytes),  RED,    command=lambda: self._filter_tag('nonenglish'))
            self._make_card(self.card_frame, 'Missing',          str(miss_count),        PURPLE, command=lambda: self._filter_tag('topn_missing'))
            self._make_card(self.card_frame, 'Missing Size',     '0 B',                  PURPLE, command=lambda: self._filter_tag('topn_missing'))

    def _get_type_filter_re(self):
        """Build a compiled regex from the filter textbox, or None if empty/invalid."""
        raw = self.filter_var.get().strip()
        if not raw:
            return None
        # Support comma-separated extensions like "chd, zip, 7z" OR raw regex
        if re.search(r'[^a-zA-Z0-9,\s\.]', raw):
            # Treat as raw regex
            try:
                return re.compile(raw, re.IGNORECASE)
            except re.error:
                return None
        else:
            # Treat as comma-separated extensions
            exts = [e.strip().lstrip('.').lower() for e in raw.split(',') if e.strip()]
            if not exts:
                return None
            pattern = r'\.(' + '|'.join(re.escape(e) for e in exts) + r')$'
            return re.compile(pattern, re.IGNORECASE)

    def _preview_type_filter(self):
        """Grey out rows that don't match the type filter, live as you type."""
        rgx = self._get_type_filter_re()
        for iid, (fname, orig_tag) in self._all_tree_items.items():
            try:
                current_tags = list(self.title_list.item(iid, 'tags'))
                if rgx and not rgx.search(fname):
                    vals = list(self.title_list.item(iid, 'values'))
                    if vals:
                        vals[0] = '○'
                        self.title_list.item(iid, values=vals, tags=('filtered',))
                else:
                    if 'filtered' in current_tags:
                        vals = list(self.title_list.item(iid, 'values'))
                        if vals:
                            # Restore dot if this file is selected
                            fname2, _ = self._all_tree_items.get(iid, ('', ''))
                            is_sel = any(
                                d.get('selected') and d['selected'].get('filename') == fname2
                                for d in self.rom_dict.values())
                            vals[0] = '●' if is_sel else '○'
                            self.title_list.item(iid, values=vals, tags=(orig_tag,))
            except tk.TclError:
                pass

    def _retag_row(self, iid, fname):
        """Restore the correct tag for a row from stored original tag."""
        if iid in self._all_tree_items:
            _, orig_tag = self._all_tree_items[iid]
            self.title_list.item(iid, tags=(orig_tag,))

    def _apply_type_filter(self):
        """Deselect all files excluded by the type filter regex."""
        rgx = self._get_type_filter_re()
        if not rgx:
            return
        changed = 0
        for title, data in self.rom_dict.items():
            sel = data.get('selected')
            if sel and not rgx.search(sel.get('filename', '')):
                data['selected'] = None
                changed += 1
        if changed:
            self._preview_type_filter()
            self._populate_cards()
            self._compat_prepopulate()

    def _compile_search(self, q: str):
        """Return a match function (str -> bool) for q.
        Plain text: substring. Only * / ? wildcards: glob. Any other regex char: regex."""
        import fnmatch as _fnmatch
        REGEX_CHARS = set('.+[]()|^${}\\')
        q_lower = q.lower()
        has_glob  = '*' in q or '?' in q
        has_regex = bool(REGEX_CHARS & set(q))
        if has_regex:
            try:
                pat = re.compile(q, re.IGNORECASE)
                return lambda s: bool(pat.search(s))
            except re.error:
                return lambda s: q_lower in s.lower()
        elif has_glob:
            return lambda s: _fnmatch.fnmatch(s.lower(), q_lower)
        else:
            return lambda s: q_lower in s.lower()

    def _update_sel_match_count(self):
        if not hasattr(self, 'lbl_sel_match_count'): return
        try:
            n = len(self.title_list.get_children())
            total = len(self._all_tree_items)
            self.lbl_sel_match_count.config(text=f'{n:,} / {total:,} files')
        except Exception:
            pass

    def _apply_search(self):
        """Show/hide treeview rows based on search text."""
        self._active_tag_filter = None  # clear tag filter on search
        q = self.search_var.get().strip()
        if not q:
            # Restore all rows
            for iid in self._all_tree_items:
                self.title_list.reattach(iid, '', 'end')
            self._update_sel_match_count()
            return
        match = self._compile_search(q)
        # Detach non-matching, reattach matching
        pos = 0
        for iid in self._all_tree_items:
            fname, _ = self._all_tree_items[iid]
            if match(fname):
                self.title_list.reattach(iid, '', pos)
                pos += 1
            else:
                self.title_list.detach(iid)
        self._update_sel_match_count()

    def _sort_analysis(self, col):
        if self._analysis_sort_col == col:
            self._analysis_sort_rev = not self._analysis_sort_rev
        else:
            self._analysis_sort_col = col
            self._analysis_sort_rev = False
        items = [(self.title_list.set(k, col), k)
                 for k in self.title_list.get_children('')]
        items.sort(reverse=self._analysis_sort_rev)
        for i, (_, k) in enumerate(items):
            self.title_list.move(k, '', i)

    def _make_card(self, parent, label: str, value: str, color: str = FG, command=None, dbl_command=None):
        card = tk.Frame(parent, bg=BG2, padx=8, pady=6,
                        cursor='hand2' if (command or dbl_command) else '')
        card.pack(side='left', padx=3, pady=4)
        lbl_val = tk.Label(card, text=value, bg=BG2, fg=color,
                           font=('Consolas', 12, 'bold'), width=12)
        lbl_val.pack()
        lbl_name = tk.Label(card, text=label, bg=BG2, fg=FG2,
                            font=FONT_SM, width=12)
        lbl_name.pack()
        if command or dbl_command:
            _click_id = [None]
            def _on_click(e):
                if dbl_command:
                    # Delay single-click to check if double-click follows
                    if _click_id[0]:
                        self.root.after_cancel(_click_id[0])
                    _click_id[0] = self.root.after(250, command) if command else None
                elif command:
                    command()
            def _on_dbl(e):
                if _click_id[0]:
                    self.root.after_cancel(_click_id[0])
                    _click_id[0] = None
                dbl_command()
            for w in (card, lbl_val, lbl_name):
                if command or dbl_command:
                    w.bind('<Button-1>', _on_click)
                if dbl_command:
                    w.bind('<Double-Button-1>', _on_dbl)

    def _build_exclude_titles(self):
        """Build and cache exclude lookup: norm_stem -> original title, plus a set of cnorms."""
        excl_dir = self.exclude_dir.get().strip()
        if not excl_dir or not os.path.isdir(excl_dir):
            self._excl_titles_cache = []
            self._excl_cnorms = set()
            return []
        titles = []
        cnorms = set()
        for entry in os.scandir(excl_dir):
            if entry.is_file():
                stem = os.path.splitext(entry.name)[0]
            elif entry.is_dir():
                # Strip known emulator suffixes e.g. "Game Title.parrot" (TeknoParrot/RetroBat)
                stem = re.sub(r'\.(?:parrot|sega|model2|model3|lindbergh|taito|namco)$',
                              '', entry.name, flags=re.IGNORECASE).strip()
                # Split camelCase/PascalCase dir names (no spaces) into words
                stem = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', stem)
                stem = re.sub(r'([A-Za-z])([0-9])', r'\1 \2', stem)
                stem = re.sub(r'([0-9])([A-Za-z])', r'\1 \2', stem)
                stem = re.sub(r'\s{2,}', ' ', stem).strip()
            else:
                continue
            clean = re.sub(r'\s*\([^)]*\)', '', stem).strip()
            titles.append(clean)
            cnorms.add(_cnorm(clean))
        self._excl_titles_cache = titles
        self._excl_cnorms       = cnorms
        return titles

    def _is_locally_owned(self, fname):
        """Return True if fname matches any file in the exclude directory."""
        cache = getattr(self, '_excl_titles_cache', None)
        if cache is None:
            self._build_exclude_titles()
            cache = self._excl_titles_cache
        if not cache:
            return False
        rom_title = re.sub(r'\s*\([^)]*\)', '', os.path.splitext(fname)[0]).strip()
        rom_norm  = _cnorm(rom_title)
        # Fast exact-norm check first (O(1))
        if rom_norm in self._excl_cnorms:
            return True
        # Fuzzy fallback only if fast check fails
        return any(_cscore(rom_title, excl) >= 0.75 for excl in cache)

    def _populate_analysis(self):
        # Clear treeview and search index
        for row in self.title_list.get_children():
            self.title_list.delete(row)
        self._all_tree_items = {}
        self._orig_tree_tags = {}

        # ── Build all rows as a list first (fast, no Tkinter calls) ──────────
        rows = []
        if self.dat_mode:
            self._cycle_pos = {}
            for key, data in self.rom_dict.items():
                if data.get('_dat_missing'):
                    tag = 'nonenglish' if data.get('non_english') else 'topn_missing'
                    rows.append(('✗', data['_dat_fname'], data['_dat_size'], tag))
                elif data['selected']:
                    fname = data['selected']['filename']
                    rows.append(('●', fname, data['selected']['size'], 'selected'))
                elif data.get('non_english'):
                    for inst in data.get('instances', []):
                        rows.append(('✗', inst['filename'], inst.get('size', ''), 'nonenglish'))
                else:
                    fname = key
                    size = next((e[1] for e in self.raw_file_entries if e[0] == fname), '')
                    rows.append(('○', fname, size, 'unselected'))
            rows.sort(key=lambda r: r[1].lower())
        else:
            for title, data in sorted(self.rom_dict.items()):
                if data.get('_dat_missing'):
                    # Only truly missing if no instances exist at all
                    tag = 'topn_missing' if not data.get('instances') else 'nonenglish'
                    rows.append(('✗', data['_dat_fname'], '', tag))
                    continue
                selected_fn   = data['selected']['filename'] if data['selected'] else None
                non_english   = data.get('non_english', False)
                is_translated = data.get('translated', False)
                instances     = data.get('instances', [])
                if not instances:
                    if data['selected']:
                        rows.append(('●', data['selected']['filename'],
                                     data['selected']['size'], 'selected'))
                    continue
                for inst in sorted(instances, key=lambda i: i['filename']):
                    fname  = inst['filename']
                    size   = inst['size']
                    is_sel = fname == selected_fn
                    if is_sel:
                        symbol, tag = '●', 'selected'
                    elif is_excluded(inst):
                        symbol, tag = '⊘', 'excluded'
                    elif non_english or (is_translated and not is_sel):
                        symbol, tag = '✗', 'nonenglish'
                    elif os.path.splitext(fname)[1].lower() in NON_GAME_EXTS:
                        symbol, tag = '○', 'non_game'
                    else:
                        symbol, tag = '○', 'unselected'
                    rows.append((symbol, fname, size, tag))

        # Apply locally_owned override
        excl_set = getattr(self, '_excl_cnorms', set())
        for i, (symbol, fname, size, tag) in enumerate(rows):
            if tag not in ('excluded',) and excl_set:
                stem = re.sub(r'\s*\([^)]*\)', '', os.path.splitext(fname)[0]).strip()
                if _cnorm(stem) in excl_set or self._is_locally_owned(fname):
                    rows[i] = (symbol, fname, size, 'locally_owned')

        # ── Insert in batches via after() so UI stays responsive ─────────────
        total = len(rows)
        BATCH = 300

        def _insert_batch(start):
            batch = rows[start:start + BATCH]
            for symbol, fname, size, tag in batch:
                iid = self.title_list.insert('', 'end', values=(symbol, fname, size), tags=(tag,))
                self._all_tree_items[iid] = (fname, tag)
                self._orig_tree_tags[iid] = (fname, tag)
            done = min(start + BATCH, total)
            self.setup_status.config(text=f'Building list… {done}/{total}', fg=YELLOW)
            if done < total:
                self.root.after(1, lambda: _insert_batch(done))
            else:
                self._populate_cards()
                self._compat_prepopulate()
                self.setup_status.config(text='Analysis complete!', fg=GREEN)
                if hasattr(self, 'search_var') and self.search_var.get().strip():
                    self._apply_search()

        if rows:
            _insert_batch(0)
        else:
            self._populate_cards()
            self._compat_prepopulate()
            self.setup_status.config(text='Analysis complete!', fg=GREEN)

    def _get_torrent(self):
        """Download selected Minerva files via aria2c using existing parallel UI."""
        import subprocess, shutil

        # Verify aria2c
        aria2c = find_aria2c()
        if not aria2c:
            messagebox.showerror('aria2c not found',
                'aria2c.exe not found.\nPlace aria2c.exe next to RomGoGetter or install it on PATH.')
            return

        urls = [u.strip() for u in self.url_text.get('1.0', 'end').splitlines() if u.strip()]
        minerva_urls = [u for u in urls if is_minerva_url(u)]
        if not minerva_urls:
            messagebox.showerror('Error', 'No Minerva URL found.')
            return

        dest_dir = self._get_dest_dir()
        if not dest_dir:
            messagebox.showerror('Error', 'Please select a destination folder.')
            return

        # Build selected filenames
        selected_fnames = set()
        for data in self.rom_dict.values():
            if data.get('selected'):
                selected_fnames.add(data['selected']['filename'])
        if not selected_fnames:
            messagebox.showerror('Error', 'No files selected.')
            return

        # Update button immediately
        self.btn_start_dl.config(state='disabled', text='Working...')
        self.root.update()
        self._debug(f"Minerva download: {len(selected_fnames)} files from {len(minerva_urls)} URL(s), aria2c={aria2c}")

        def _start():
            try:
                # Each Minerva URL has its own torrent — fetch all, match files per torrent.
                # to_download entries are 4-tuples: (file_id, fname, size, torrent_tmp)
                to_download = []
                skipped     = 0
                unmatched   = set(selected_fnames)  # track what's still not found
                temp_torrents = []  # temp files to clean up afterward

                for minerva_url in minerva_urls:
                    # Local HTML file — look for torrent in same dir
                    local_torrent = None
                    if os.path.isfile(minerva_url.strip()):
                        html_dir = os.path.dirname(os.path.abspath(minerva_url.strip()))
                        for fn in os.listdir(html_dir):
                            if fn.lower().endswith('.torrent'):
                                local_torrent = os.path.join(html_dir, fn)
                                break

                    if local_torrent:
                        self._debug(f"Using local torrent: {local_torrent}")
                        with open(local_torrent, 'rb') as f:
                            torrent_data = f.read()
                        torrent_tmp = local_torrent
                    else:
                        torrent_url = minerva_torrent_url(minerva_url)
                        if not torrent_url:
                            self._debug(f"Could not determine torrent URL for: {minerva_url}")
                            continue
                        self._debug(f"Torrent URL: {torrent_url}")
                        req = urllib.request.Request(torrent_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'})
                        with urllib.request.urlopen(req, timeout=60) as r:
                            torrent_data = r.read()
                        # Save with index to avoid collision between multiple torrents
                        idx = len(temp_torrents)
                        torrent_tmp = os.path.join(dest_dir, f'romgogetter_minerva_{idx}.torrent')
                        os.makedirs(dest_dir, exist_ok=True)
                        with open(torrent_tmp, 'wb') as f:
                            f.write(torrent_data)
                        temp_torrents.append(torrent_tmp)

                    self._debug(f"Torrent: {len(torrent_data):,} bytes")
                    id_map = torrent_file_id_map(torrent_data)
                    self._debug(f"Torrent has {len(id_map)} files, checking {len(unmatched)} remaining")

                    # Build rel_path lookup from rom_dict for full-path matching
                    rel_path_map = {}
                    for data in self.rom_dict.values():
                        sel = data.get('selected')
                        if sel and sel['filename'] in unmatched:
                            rel = sel.get('direct_url') or ''  # direct_url holds rel_path for Minerva
                            if rel:
                                rel_path_map[sel['filename']] = rel

                    for fname in sorted(list(unmatched)):
                        clean = html.unescape(fname)
                        # Skip if already fully downloaded
                        if os.path.exists(os.path.join(dest_dir, clean)):
                            skipped += 1
                            unmatched.discard(fname)
                            continue
                        rel = rel_path_map.get(fname, '')
                        entry = (id_map.get(rel) or id_map.get(fname) or id_map.get(clean))
                        if entry:
                            file_id, full_path, length = entry
                            has_partial = os.path.exists(
                                os.path.join(dest_dir, f'thread_{file_id}', full_path))
                            if has_partial:
                                self._debug(f"Resuming partial: {clean}")
                            to_download.append((file_id, clean, length, torrent_tmp))
                            unmatched.discard(fname)

                for fname in sorted(unmatched):
                    self._debug(f"Not found in any torrent: {fname!r}")

                if skipped:
                    self._debug(f"Skipped {skipped} already downloaded files")

                if not to_download:
                    self.root.after(0, lambda: self.btn_start_dl.config(state='normal', text='Start'))
                    self.root.after(0, lambda: messagebox.showinfo('Done',
                        'All selected files already downloaded.' if skipped else 'No selected files found in any torrent.'))
                    return

                self._debug(f"Matched {len(to_download)}/{len(selected_fnames)} files across {len(minerva_urls)} torrent(s)")

                # Calculate space
                required_bytes = sum(s for _, _, s, _ in to_download)
                os.makedirs(dest_dir, exist_ok=True)
                free_bytes = shutil.disk_usage(dest_dir).free

                self.root.after(0, lambda: self._confirm_and_start_aria2c(
                    aria2c, temp_torrents, to_download, dest_dir,
                    skipped, required_bytes, free_bytes))

            except Exception:
                import traceback
                tb = traceback.format_exc()
                self._debug(f"Torrent setup error:\n{tb}")
                self.root.after(0, lambda: self.btn_start_dl.config(state='normal', text='Start'))
                self.root.after(0, lambda: messagebox.showerror('Error', f'Torrent setup failed - see debug log'))

        threading.Thread(target=_start, daemon=True).start()

    def _confirm_and_start_aria2c(self, aria2c, temp_torrents, to_download, dest_dir,
                                   skipped, required_bytes, free_bytes):
        """Called on main thread — show confirm/space dialogs then start downloads."""
        import shutil as _shutil

        # Space warning first
        if free_bytes < required_bytes:
            ans = messagebox.askyesno(
                'Low Disk Space',
                f"Not enough free space!\n"
                f"Need: {format_size(required_bytes)}\n"
                f"Free: {format_size(free_bytes)}\n\n"
                f"Continue anyway?"
            )
            if not ans:
                self.btn_start_dl.config(state='normal', text='Start')
                return

        # Confirm dialog
        ans = messagebox.askyesno(
            'Confirm Download',
            f"Files to download: {len(to_download)}\n"
            f"Files to skip:     {skipped}\n"
            f"Required space:    {format_size(required_bytes)}\n"
            f"Free space:        {format_size(free_bytes)}\n\n"
            f"Start?"
        )
        if not ans:
            self.btn_start_dl.config(state='normal', text='Start')
            return

        self.nb.select(self._nb_tab_download)
        threading.Thread(target=self._start_aria2c_downloads,
            args=(aria2c, temp_torrents, to_download, dest_dir, skipped),
            daemon=True).start()

    def _start_aria2c_downloads(self, aria2c, temp_torrents, to_download, dest_dir, skipped=0):
        """Drive aria2c downloads using the existing parallel slot UI."""
        import subprocess, re as _re, shutil
        self._debug(f"_start_aria2c_downloads: {len(to_download)} files")

        # Clean up any leftover thread dirs from previous runs
        import shutil as _shutil
        try:
            for entry in os.scandir(dest_dir):
                if entry.is_dir() and entry.name.startswith('thread_'):
                    try: _shutil.rmtree(entry.path, ignore_errors=True)
                    except: pass
        except Exception:
            pass

        max_par      = self.parallel.get()
        max_ret      = self.retries.get()
        total_files  = len(to_download)
        total_bytes  = sum(s for _, _, s, _ in to_download)

        with self.dl_lock:
            self.dl_completed_files = 0
            self.dl_failed_files    = 0
            self.dl_skipped_files   = skipped
            self.dl_completed_bytes = 0
            self.dl_total_files     = total_files + skipped
            self.dl_total_bytes     = total_bytes
            self.dl_start_time      = time.time()
            self.dl_window          = []
            self.dl_failed_list     = []
            self.dl_slots           = {}

        def _ui_setup():
            self._prepare_download_tab()
            self.nb.select(self._nb_tab_download)
            for slot in range(20):
                if slot < max_par:
                    self.dl_slot_widgets[slot]['frame'].pack(fill='x', pady=2)
                else:
                    self.dl_slot_widgets[slot]['frame'].pack_forget()
            self.btn_start_dl.config(state='disabled', text='Working...')
            n_torrents = len(temp_torrents) if temp_torrents else 1
            self.dl_lbl_verify.config(
                text=f"aria2c — {total_files} files queued across {n_torrents} torrent(s)")
        self.root.after(0, _ui_setup)
        time.sleep(0.3)

        self.dl_running = True
        self.root.after(500, self._dl_tick)
        self._debug("aria2c manager starting")

        ARIA2C_PROG = _re.compile(
            r'\[#\w+\s+([\d.]+[KMGT]?i?B?)/([\d.]+[KMGT]?i?B?)\((\d+)%\)'
            r'.*?DL:([\d.]+[KMGT]?i?B?).*?ETA:([\w:]+)\]'
        )

        def parse_bytes_str(s):
            s = s.strip()
            for suffix, mult in [('GiB',1<<30),('MiB',1<<20),('KiB',1<<10),
                                  ('GB',10**9),('MB',10**6),('KB',10**3),('B',1)]:
                if s.endswith(suffix):
                    try: return int(float(s[:-len(suffix)]) * mult)
                    except: return 0
            try: return int(s)
            except: return 0

        def download_one(slot, file_id, fname, size, torrent_tmp):
            thread_dir = os.path.join(dest_dir, f'thread_{file_id}')
            thread_rel = f'thread_{file_id}'
            os.makedirs(thread_dir, exist_ok=True)
            self.update_slot(slot, fname, 0, size or 1)
            cmd = [
                aria2c, '-c',
                f'--select-file={file_id}',
                '--seed-time=0',
                f'--split={self.aria2_split.get()}',
                f'--max-connection-per-server={self.aria2_split.get()}',
                '--max-concurrent-downloads=1',
                '--console-log-level=notice',
                '--summary-interval=3600',
                '-d', thread_rel,
                '-T', torrent_tmp,
            ]
            speed = self.aria2_speed.get().strip()
            if speed and speed != '0':
                cmd += [f'--max-download-limit={speed}M']

            for attempt in range(1, max_ret + 1):
                self._debug(f"[slot {slot}] attempt {attempt}/{max_ret}: file={file_id} {fname}")
                try:
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        universal_newlines=True, bufsize=1,
                        creationflags=0x08000000 if os.name == 'nt' else 0,
                        cwd=dest_dir
                    )
                    if not hasattr(self, '_aria2c_procs'):
                        self._aria2c_procs = []
                    self._aria2c_procs.append(proc)
                    output_lines = []
                    for line in proc.stdout:
                        line = line.rstrip()
                        output_lines.append(line)
                        m = ARIA2C_PROG.search(line)
                        if m:
                            dl  = parse_bytes_str(m.group(1))
                            tot = parse_bytes_str(m.group(2)) or size or 1
                            self.update_slot(slot, fname, dl, tot)
                    proc.wait()
                    try: self._aria2c_procs.remove(proc)
                    except: pass
                    rc = proc.returncode
                    self._debug(f"[slot {slot}] exit={rc}")
                    if rc != 0:
                        for l in output_lines[-5:]:
                            self._debug(f"  aria2c: {l}")
                except Exception as ex:
                    self._debug(f"[slot {slot}] error: {ex}")
                    rc = -1

                if rc == 0:
                    found = None
                    for root_d, dirs, files in os.walk(thread_dir):
                        for fn in files:
                            if fn == fname and not fn.endswith('.aria2'):
                                found = os.path.join(root_d, fn)
                                break
                    if found:
                        dst = os.path.join(dest_dir, fname)
                        shutil.copy2(found, dst)
                        self.complete_slot(slot, os.path.getsize(dst), fname=fname)
                        self._debug(f"[slot {slot}] done: {fname}")
                        try: shutil.rmtree(thread_dir, ignore_errors=True)
                        except: pass
                        return True, fname
                    else:
                        self._debug(f"[slot {slot}] file not found after download")
                        rc = -1

                # Failed — wipe partial and retry
                if attempt < max_ret:
                    self._debug(f"[slot {slot}] wiping partial, retrying...")
                    try: shutil.rmtree(thread_dir, ignore_errors=True)
                    except: pass
                    os.makedirs(thread_dir, exist_ok=True)
                    self.update_slot(slot, fname, 0, size or 1)

            self.complete_slot(slot, 0, failed=True)
            self.add_issue(f"[failed] {fname}")
            try: shutil.rmtree(thread_dir, ignore_errors=True)
            except: pass
            return False, fname

        import queue as _queue
        from concurrent.futures import ThreadPoolExecutor
        work_queue = _queue.Queue()
        for item in to_download:
            work_queue.put(item)

        active_slots = {}
        mgr_lock     = threading.Lock()
        finished     = [0]

        try:
            with ThreadPoolExecutor(max_workers=20) as executor:

                def submit_slot(slot, file_id, fname, size, torrent_tmp):
                    self.update_slot(slot, fname, 0, size or 1)
                    return executor.submit(download_one, slot, file_id, fname, size, torrent_tmp)

                def manager():
                    draining        = False
                    target_par      = max_par
                    queue_exhausted = False
                    while finished[0] < total_files and self.dl_running:
                        par = self.parallel.get()
                        with mgr_lock:
                            if par < target_par:
                                draining   = True
                                target_par = par
                                for s in range(par, 20):
                                    if s not in active_slots:
                                        self.root.after(0, lambda sl=s:
                                            self.dl_slot_widgets[sl]['frame'].pack_forget())
                            elif par > target_par:
                                draining   = False
                                target_par = par
                                for s in range(par):
                                    self.root.after(0, lambda sl=s:
                                        self.dl_slot_widgets[sl]['frame'].pack(fill='x', pady=2))

                            for slot in list(active_slots.keys()):
                                if not active_slots[slot].done():
                                    continue
                                active_slots.pop(slot)
                                finished[0] += 1
                                if draining:
                                    def _hide_repack(s=slot):
                                        self.dl_slot_widgets[s]['frame'].pack_forget()
                                        visible = [i for i in range(20)
                                                   if self.dl_slot_widgets[i]['frame'].winfo_ismapped()]
                                        for i in visible:
                                            self.dl_slot_widgets[i]['frame'].pack_forget()
                                        for i in visible:
                                            self.dl_slot_widgets[i]['frame'].pack(fill='x', pady=2)
                                        self.slots_canvas.yview_moveto(0)
                                    self.root.after(0, _hide_repack)

                            if draining and len(active_slots) <= target_par:
                                draining = False
                                def _repack(tp=target_par):
                                    for s in range(20):
                                        self.dl_slot_widgets[s]['frame'].pack_forget()
                                    for s in range(tp):
                                        self.dl_slot_widgets[s]['frame'].pack(fill='x', pady=2)
                                    self.slots_canvas.yview_moveto(0)
                                self.root.after(0, _repack)

                            if not draining:
                                for slot in range(target_par):
                                    if slot not in active_slots:
                                        try:
                                            file_id, fname, size, t_tmp = work_queue.get_nowait()
                                            active_slots[slot] = submit_slot(slot, file_id, fname, size, t_tmp)
                                            self.root.after(0, lambda s=slot:
                                                self.dl_slot_widgets[s]['frame'].pack(fill='x', pady=2))
                                        except _queue.Empty:
                                            if not queue_exhausted:
                                                queue_exhausted = True
                                            break
                                if queue_exhausted:
                                    active = sorted(active_slots.keys())
                                    def _repack_active(slots=active):
                                        for s in range(20):
                                            self.dl_slot_widgets[s]['frame'].pack_forget()
                                        for s in slots:
                                            self.dl_slot_widgets[s]['frame'].pack(fill='x', pady=2)
                                    self.root.after(0, _repack_active)
                        time.sleep(0.2)

                    while active_slots:
                        with mgr_lock:
                            for slot in list(active_slots.keys()):
                                if active_slots[slot].done():
                                    active_slots.pop(slot)
                                    finished[0] += 1
                        time.sleep(0.3)

                threading.Thread(target=manager, daemon=True).start()
                while finished[0] < total_files and self.dl_running:
                    time.sleep(0.5)

        except Exception:
            import traceback
            self._debug(f"aria2c manager crash:\n{traceback.format_exc()}")

        for t in (temp_torrents if isinstance(temp_torrents, list) else []):
            try: os.remove(t)
            except: pass

        self.dl_running = False
        self.root.after(0, self._dl_done)

    def _go_to_download(self):
        if not self.rom_dict:
            messagebox.showerror('Error', 'Run analysis first.')
            return
        self._prepare_download_tab()
        self.nb.select(self._nb_tab_download)

    def _ask_export_scope(self, tree_widget=None):
        """Show radio dialog to pick export scope. Returns scope string or None if cancelled."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Export Scope')
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self.root)
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width()  - dlg.winfo_width())  // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f'+{x}+{y}')
        tk.Label(dlg, text='Export which entries?', bg=BG, fg=FG,
                 font=('Consolas', 11, 'bold')).pack(padx=20, pady=(16, 8))
        scope_var = tk.StringVar(value='selected')
        for text, val in [
            ('Selected',          'selected'),
            ('Visible',           'visible'),
            ('Reverse Selected',  'reverse_selected'),
            ('Reverse Visible',   'reverse_visible'),
        ]:
            tk.Radiobutton(dlg, text=text, variable=scope_var, value=val,
                           bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                           font=FONT_LG).pack(anchor='w', padx=24, pady=2)
        result = [None]
        def _ok():
            result[0] = scope_var.get()
            dlg.destroy()
        def _cancel():
            dlg.destroy()
        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=(12, 16))
        tk.Button(btn_row, text='Export', bg=ACC, fg=FG, font=FONT_LG,
                  relief='flat', padx=16, command=_ok).pack(side='left', padx=6)
        tk.Button(btn_row, text='Cancel', bg=BG3, fg=FG, font=FONT_LG,
                  relief='flat', padx=16, command=_cancel).pack(side='left', padx=6)
        self.root.wait_window(dlg)
        return result[0]

    def _collect_export_entries(self, scope, tree_widget=None):
        """Return list of (fname, size_s) for the given scope."""
        if scope == 'selected':
            return [(d['selected']['filename'], d['selected']['size'])
                    for d in self.rom_dict.values() if d.get('selected')]

        if scope == 'reverse_selected':
            # All entries that are NOT currently selected — use their filename from values
            entries = []
            all_iids = list(getattr(self, '_all_tree_items', {}).keys())
            tree = getattr(self, 'title_list', None)
            if tree:
                for iid in all_iids:
                    vals = tree.item(iid, 'values') if iid in set(tree.get_children()) or True else None
                    try:
                        vals = tree.item(iid, 'values')
                        if vals and vals[0] != '●' and len(vals) >= 3:
                            entries.append((vals[1], vals[2]))
                    except Exception:
                        pass
            return entries

        # visible / reverse_visible — read from tree rows
        if tree_widget is None:
            tree_widget = getattr(self, 'title_list', None)
        if tree_widget is None:
            return []
        if scope == 'visible':
            iids = list(tree_widget.get_children())
        else:  # reverse_visible
            visible = set(tree_widget.get_children())
            all_iids = list(getattr(self, '_all_tree_items', {}).keys())
            iids = [i for i in all_iids if i not in visible]
        entries = []
        for iid in iids:
            vals = tree_widget.item(iid, 'values')
            if vals and len(vals) >= 3:
                entries.append((vals[1], vals[2]))
        return entries

    def _export_dat(self, tree_widget=None):
        if not self.rom_dict:
            messagebox.showerror('Error', 'Run analysis first.')
            return
        scope = self._ask_export_scope()
        if not scope:
            return
        entries = self._collect_export_entries(scope, tree_widget)
        if not entries:
            messagebox.showinfo('Export', 'No entries to export for the selected scope.')
            return
        path = filedialog.asksaveasfilename(
            title='Export DAT file',
            defaultextension='.dat',
            filetypes=[('DAT files', '*.dat'), ('XML files', '*.xml'), ('All files', '*.*')],
            initialfile=f"{self.page_title or 'export'}.dat",
        )
        if not path:
            return
        try:
            root_el  = ET.Element('datafile')
            header   = ET.SubElement(root_el, 'header')
            name_el  = ET.SubElement(header, 'name')
            name_el.text = self.page_title or 'Export'
            desc_el  = ET.SubElement(header, 'description')
            desc_el.text = f'Exported by {APP_NAME} {APP_VER}'
            for fname, size_s in sorted(entries, key=lambda x: x[0].lower()):
                if self.dat_mode:
                    size_b = str(parse_size_bytes_dat(size_s))
                else:
                    size_b = str(parse_size_bytes(size_s))
                title = os.path.splitext(fname)[0]
                game  = ET.SubElement(root_el, 'game', name=title)
                ET.SubElement(game, 'rom', name=fname, size=size_b)
            tree = ET.ElementTree(root_el)
            ET.indent(tree, space='  ')
            tree.write(path, encoding='utf-8', xml_declaration=True)
            messagebox.showinfo('Export complete',
                                f'Exported {len(entries)} entries to:\n{path}')
        except Exception:
            import traceback
            messagebox.showerror('Export failed', traceback.format_exc())

    # ── Download tab ──────────────────────────────────────────────────────────

    def _build_download(self):
        f   = self.tab_download
        PAD = 16

        of = tk.Frame(f, bg=BG, padx=PAD, pady=PAD)
        of.pack(fill='x')

        hdr = tk.Frame(of, bg=BG)
        hdr.pack(fill='x')
        tk.Label(hdr, text='Download Progress', bg=BG, fg=FG,
                 font=FONT_XL).pack(side='left')
        self.btn_pause = tk.Button(
            hdr, text='Pause', bg='#444', fg=FG, font=FONT,
            relief='flat', padx=10, pady=2, command=self._toggle_pause,
        )
        self.btn_pause.pack(side='right', padx=4)
        self.btn_start_dl = tk.Button(
            hdr, text='Start', bg=ACC, fg=FG, font=FONT_LG,
            relief='flat', padx=20, pady=6, command=self._start_download,
        )
        self.btn_start_dl.pack(side='right', padx=4)

        # Verification mode
        self.ver_row = tk.Frame(of, bg=BG)
        self.ver_row.pack(fill='x', pady=(4, 0))
        tk.Label(self.ver_row, text='Verify:', bg=BG, fg=FG2, font=FONT_SM).pack(side='left', padx=(0, 6))
        self.verify_combo = ttk.Combobox(
            self.ver_row, textvariable=self.verify_mode,
            values=['Overwrite', 'Name', 'Size', 'Hash'],
            state='readonly', font=FONT_SM, width=12,
        )
        self.verify_combo.pack(side='left')

        self.dl_overall_bar = ttk.Progressbar(of, mode='determinate')
        self.dl_overall_bar.pack(fill='x', pady=4)

        row1 = tk.Frame(of, bg=BG)
        row1.pack(fill='x')
        self.dl_lbl_pct     = tk.Label(row1, text='0.0%',      bg=BG, fg=ACC,  font=FONT_LG, width=8,  anchor='w')
        self.dl_lbl_size    = tk.Label(row1, text='0 B / 0 B', bg=BG, fg=FG,   font=FONT,    width=30, anchor='w')
        self.dl_lbl_speed   = tk.Label(row1, text='-- /s',     bg=BG, fg=FG,   font=FONT,    width=16, anchor='w')
        self.dl_lbl_eta     = tk.Label(row1, text='ETA: --',   bg=BG, fg=FG,   font=FONT,    width=16, anchor='w')
        self.dl_lbl_elapsed = tk.Label(row1, text='0s',        bg=BG, fg=FG2,  font=FONT,    width=14, anchor='w')
        for w in (self.dl_lbl_pct, self.dl_lbl_size, self.dl_lbl_speed,
                  self.dl_lbl_eta, self.dl_lbl_elapsed):
            w.pack(side='left', padx=4)

        # ── Files info + settings on same row ────────────────────────────────
        dl_opts = tk.Frame(f, bg=BG, padx=PAD)
        dl_opts.pack(fill='x', pady=(6, 0))
        self._http_only_cols  = []
        self._aria2c_only_cols = []

        self.dl_lbl_files = tk.Label(dl_opts, text='', bg=BG, fg=FG, font=FONT)
        self.dl_lbl_files.pack(side='left', anchor='w')

        self.dl_lbl_dest = tk.Label(dl_opts, text='', bg=BG, fg=FG2, font=FONT_SM)
        self.dl_lbl_dest.pack(side='left', anchor='w', padx=(12, 0))

        for label, var, mn, mx in [
            ('Parallel',  self.parallel, 1, 20),
            ('Retries',   self.retries,  1, 20),
            ('Idle (s)',  self.stuck,   10, 600),
        ]:
            col = tk.Frame(dl_opts, bg=BG)
            col.pack(side='right', padx=(8, 0))
            tk.Label(col, text=label, bg=BG, fg=FG2, font=FONT_SM).pack(anchor='w')
            tk.Spinbox(col, from_=mn, to=mx, textvariable=var, width=5,
                       bg=BG2, fg=FG, font=FONT, buttonbackground=BG3,
                       relief='flat', borderwidth=4,
                       command=self._on_parallel_change if label == 'Parallel' else None
                       ).pack(anchor='w')

        # Aria2c-only options
        for label, var, widget_type, opts in [
            ('Split',      self.aria2_split, 'spin',  dict(from_=1, to=16, width=5)),
            ('Limit (MB)', self.aria2_speed, 'entry', dict(width=5)),
        ]:
            col = tk.Frame(dl_opts, bg=BG)
            col.pack(side='right', padx=(8, 0))
            tk.Label(col, text=label, bg=BG, fg=FG2, font=FONT_SM).pack(anchor='w')
            if widget_type == 'spin':
                tk.Spinbox(col, textvariable=var, bg=BG2, fg=FG, font=FONT,
                           buttonbackground=BG3, relief='flat', borderwidth=4,
                           **opts).pack(anchor='w')
            else:
                tk.Entry(col, textvariable=var, bg=BG2, fg=FG, font=FONT,
                         insertbackground=FG, relief='flat', borderwidth=4,
                         **opts).pack(anchor='w')
            self._aria2c_only_cols.append(col)

        # Status labels — only visible when non-empty
        status_row = tk.Frame(f, bg=BG, padx=PAD)
        status_row.pack(fill='x')
        self.dl_lbl_checking = tk.Label(status_row, text='', bg=BG, fg=FG2,   font=FONT_SM)
        self.dl_lbl_checking.pack(side='left')
        self.dl_lbl_verify   = tk.Label(status_row, text='', bg=BG, fg=YELLOW, font=FONT_SM)
        self.dl_lbl_verify.pack(side='left', padx=(8, 0))

        tk.Frame(f, bg='#444', height=1).pack(fill='x', padx=PAD, pady=(4, 0))

        sf_outer = tk.Frame(f, bg=BG, padx=PAD, pady=8)
        sf_outer.pack(fill='x')
        sf_hdr = tk.Frame(sf_outer, bg=BG)
        sf_hdr.pack(fill='x', pady=(0, 4))
        tk.Label(sf_hdr, text='Active Downloads', bg=BG, fg=FG,
                 font=FONT_LG).pack(side='left')
        self.lbl_active_threads = tk.Label(sf_hdr, text='', bg=BG, fg=ACC, font=FONT_SM)
        self.lbl_active_threads.pack(side='left', padx=(8, 0))

        # Fixed-height scrollable area for slot bars
        slots_area = tk.Frame(sf_outer, bg=BG, height=450)
        slots_area.pack(fill='x')
        slots_area.pack_propagate(False)  # enforce fixed height

        slots_sb = tk.Scrollbar(slots_area)
        slots_sb.pack(side='right', fill='y')

        self.slots_canvas = slots_canvas = tk.Canvas(slots_area, bg=BG, highlightthickness=0,
                                 yscrollcommand=slots_sb.set)
        slots_canvas.pack(side='left', fill='both', expand=True)
        slots_sb.config(command=slots_canvas.yview)

        sf = tk.Frame(slots_canvas, bg=BG)
        sf_win = slots_canvas.create_window((0, 0), window=sf, anchor='nw')

        def _sf_configure(e):
            slots_canvas.configure(scrollregion=slots_canvas.bbox('all'))
        def _sc_configure(e):
            slots_canvas.itemconfig(sf_win, width=e.width)
        sf.bind('<Configure>', _sf_configure)
        slots_canvas.bind('<Configure>', _sc_configure)
        slots_canvas.bind('<MouseWheel>',
                          lambda e: slots_canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))
        sf.bind('<MouseWheel>',
                lambda e: slots_canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

        self.dl_slot_widgets             = {}
        self._slot_window: dict[int, list] = {}
        for slot in range(20):
            frm = tk.Frame(sf, bg=BG2, padx=8, pady=6)
            frm.pack(fill='x', pady=2)
            hdr2 = tk.Frame(frm, bg=BG2)
            hdr2.pack(fill='x')
            lbl_num  = tk.Label(hdr2, text=f'[{slot+1}]', bg=BG2, fg=ACC,   font=FONT,    width=4,  anchor='w')
            lbl_name = tk.Label(hdr2, text='idle',         bg=BG2, fg=FG,    font=FONT,    anchor='w')
            lbl_rate = tk.Label(hdr2, text='',             bg=BG2, fg=GREEN, font=FONT_SM, width=14, anchor='e')
            lbl_stat = tk.Label(hdr2, text='',             bg=BG2, fg=FG2,   font=FONT_SM, width=36, anchor='e')
            lbl_num.pack(side='left')
            lbl_rate.pack(side='right')
            lbl_stat.pack(side='right')
            lbl_name.pack(side='left', fill='x', expand=True)
            bar = ttk.Progressbar(frm, mode='determinate')
            bar.pack(fill='x', pady=2)
            self.dl_slot_widgets[slot] = {
                'frame': frm, 'lbl_name': lbl_name,
                'lbl_stat': lbl_stat, 'lbl_rate': lbl_rate, 'bar': bar,
            }
            self._slot_window[slot] = []
            frm.pack_forget()

        tk.Frame(f, bg='#444', height=1).pack(fill='x', padx=PAD)

        ff = tk.Frame(f, bg=BG, padx=PAD, pady=4)
        ff.pack(fill='x')
        tk.Label(ff, text='Failed / Verification Issues',
                 bg=BG, fg=RED, font=FONT_LG).pack(anchor='w')
        self.dl_failed_box = tk.Listbox(
            ff, bg=BG2, fg=RED, font=FONT_SM,
            selectbackground='#444', relief='flat', borderwidth=0, height=4,
        )
        self.dl_failed_box.pack(fill='x')

        legend = tk.Frame(ff, bg=BG)
        legend.pack(fill='x', pady=(4, 0))
        tk.Label(legend, text='Log prefix legend:', bg=BG, fg=FG2,
                 font=FONT_SM).pack(anchor='w')
        for prefix, desc, color in [
            ('[failed]',    'Download failed after all retries',                       RED),
            ('[hash fail]', 'File downloaded but MD5 did not match',                   RED),
            ('[re-dl]',     'Existing local file failed verification, re-downloading', YELLOW),
        ]:
            lrow = tk.Frame(legend, bg=BG)
            lrow.pack(anchor='w')
            tk.Label(lrow, text=prefix, bg=BG, fg=color,
                     font=FONT_SM, width=14, anchor='w').pack(side='left')
            tk.Label(lrow, text=desc, bg=BG, fg=FG2,
                     font=FONT_SM, anchor='w').pack(side='left')

        self.dl_lock               = threading.Lock()
        self.dl_slots: dict        = {}
        self.dl_completed_files    = 0
        self.dl_failed_files       = 0
        self.dl_skipped_files      = 0
        self.dl_completed_bytes    = 0
        self.dl_total_files        = 0
        self.dl_total_bytes        = 0
        self.dl_start_time         = 0.0
        self.dl_window: list       = []
        self.dl_failed_list: list  = []
        self.dl_paused             = False
        self.dl_pause_event        = threading.Event()
        self.dl_pause_event.set()
        self.dl_running            = False
        self.dl_slot_last_progress: dict   = {}
        self.dl_slot_stuck_callbacks: dict = {}

    def _on_parallel_change(self):
        """Parallel spinbox changed — manager handles live changes automatically."""
        self._debug(f"Parallel changed to {self.parallel.get()}")
        if not self.dl_running:
            max_par = self.parallel.get()
            for slot in range(20):
                w = self.dl_slot_widgets.get(slot)
                if w:
                    if slot < max_par:
                        w['frame'].pack(fill='x', pady=2)
                    else:
                        w['frame'].pack_forget()

    def _prepare_download_tab(self):
        self.dl_lbl_dest.config(text=f"Destination: {self._get_dest_dir()}")
        sel = sum(1 for d in self.rom_dict.values() if d['selected'])
        self.dl_lbl_files.config(text=f"Ready: {sel} files selected")
        # Show/hide HTTP-only options based on source type
        urls = [u.strip() for u in self.url_text.get('1.0', 'end').splitlines() if u.strip()]
        is_minerva = any(is_minerva_url(u) for u in urls)
        for col in getattr(self, '_http_only_cols', []):
            col.pack(side='right', padx=(8, 0))
        for col in getattr(self, '_aria2c_only_cols', []):
            if is_minerva:
                col.pack(side='right', padx=(8, 0))
            else:
                col.pack_forget()
        if is_minerva:
            self.ver_row.pack_forget()
        else:
            self.ver_row.pack(fill='x', pady=(4, 0))

    def _get_dest_dir(self) -> str:
        return self.dest_dir.get()

    def _toggle_pause(self):
        self.dl_paused = not self.dl_paused
        if self.dl_paused:
            self.dl_pause_event.clear()
            self.btn_pause.config(text='Resume', bg=ACC)
            for w in self.dl_slot_widgets.values():
                w['bar'].configure(style='Paused.Horizontal.TProgressbar')
            # Suspend/resume entire aria2c processes
            if os.name == 'nt':
                import ctypes
                ntdll = ctypes.windll.ntdll
                kernel32 = ctypes.windll.kernel32
                for proc in getattr(self, '_aria2c_procs', []):
                    try:
                        h = kernel32.OpenProcess(0x1F0FFF, False, proc.pid)
                        if h:
                            ntdll.NtSuspendProcess(h)
                            kernel32.CloseHandle(h)
                    except: pass
        else:
            self.dl_pause_event.set()
            self.btn_pause.config(text='Pause', bg='#444')
            for w in self.dl_slot_widgets.values():
                w['bar'].configure(style='Horizontal.TProgressbar')
            # Resume aria2c processes
            if os.name == 'nt':
                import ctypes
                ntdll = ctypes.windll.ntdll
                kernel32 = ctypes.windll.kernel32
                for proc in getattr(self, '_aria2c_procs', []):
                    try:
                        h = kernel32.OpenProcess(0x1F0FFF, False, proc.pid)
                        if h:
                            ntdll.NtResumeProcess(h)
                            kernel32.CloseHandle(h)
                    except: pass

    # ── Download engine ───────────────────────────────────────────────────────

    def update_slot(self, slot: int, filename: str, downloaded: int, total: int):
        with self.dl_lock:
            prev = self.dl_slots.get(slot)
            self.dl_slots[slot] = (filename, downloaded, total)
            if prev is None or downloaded > prev[1]:
                self.dl_slot_last_progress[slot] = time.time()
            # Feed speed window for overall ETA (used by aria2c engine too)
            total_dl = self.dl_completed_bytes + sum(
                dl for _, dl, _ in self.dl_slots.values())
            now = time.time()
            self.dl_window.append((now, total_dl))
            cutoff = now - 10
            self.dl_window = [(t, b) for t, b in self.dl_window if t >= cutoff]

    def complete_slot(self, slot: int, nbytes: int, skipped=False, failed=False, fname=''):
        with self.dl_lock:
            self.dl_slots.pop(slot, None)
            if skipped:
                self.dl_skipped_files += 1
            elif failed:
                self.dl_failed_files += 1
            else:
                self.dl_completed_files += 1
                self.dl_completed_bytes += nbytes
            completed = self.dl_completed_files
            skipped_  = self.dl_skipped_files
            failed_   = self.dl_failed_files
        if fname and not skipped and not failed:
            short = fname if len(fname) <= 40 else '...' + fname[-37:]
            self.root.after(0, lambda f=short, c=completed: self.dl_lbl_verify.config(
                text=f'✓ {f}  ({c} done)', fg=GREEN))

    def register_stuck(self, slot: int, cb: callable):
        with self.dl_lock:
            self.dl_slot_stuck_callbacks[slot] = cb
            self.dl_slot_last_progress[slot]   = time.time()

    def unregister_stuck(self, slot: int):
        with self.dl_lock:
            self.dl_slot_stuck_callbacks.pop(slot, None)
            self.dl_slot_last_progress.pop(slot, None)

    def add_issue(self, msg: str):
        with self.dl_lock:
            self.dl_failed_list.append(msg)

    def _sampler_loop(self):
        while self.dl_running:
            now = time.time()
            with self.dl_lock:
                in_prog = sum(dl for _, dl, _ in self.dl_slots.values())
                total   = self.dl_completed_bytes + in_prog
                self.dl_window.append((now, total))
                cutoff  = now - 60
                self.dl_window = [(t, b) for t, b in self.dl_window if t >= cutoff]
            time.sleep(1.0)

    def _watchdog_loop(self):
        stuck_timeout = self.stuck.get()
        while self.dl_running:
            time.sleep(5)
            if not self.dl_pause_event.is_set():
                with self.dl_lock:
                    now = time.time()
                    for s in self.dl_slot_last_progress:
                        self.dl_slot_last_progress[s] = now
                continue
            now = time.time()
            with self.dl_lock:
                callbacks     = dict(self.dl_slot_stuck_callbacks)
                last_progress = dict(self.dl_slot_last_progress)
                slots         = dict(self.dl_slots)
            for slot, cb in callbacks.items():
                if slot not in slots:
                    continue
                if now - last_progress.get(slot, now) > stuck_timeout:
                    with self.dl_lock:
                        self.dl_slot_last_progress[slot] = now
                    try:
                        cb()
                    except Exception:
                        pass

    def _download_file(self, slot, fname, url, dest_path, headers,
                       expected_size, etag_cache, cache_lock, cache_path,
                       max_retries, all_hashes, local_source='', verify_mode='Hash',
                       size_cache=None, size_lock=None, dest_dir=''):
        tmp_path   = dest_path + '.part'
        bad_path   = dest_path + '.bad'
        resume_pos = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0

        # ── Local source file — copy directly ────────────────────────────────
        if url.startswith('local://'):
            src_path = url[len('local://'):]
            if not os.path.exists(src_path):
                self.add_issue(f"[local missing] {fname}")
                self.complete_slot(slot, 0, failed=True)
                return False, fname
            try:
                src_size = os.path.getsize(src_path)
                self.update_slot(slot, f"[copy] {fname}", 0, src_size)
                self.dl_pause_event.wait()
                shutil.copy2(src_path, dest_path)
                actual_size = os.path.getsize(dest_path)
                if actual_size != src_size:
                    self.add_issue(f"[local copy fail] {fname}: size mismatch after copy")
                    self.complete_slot(slot, 0, failed=True)
                    return False, fname
                self.update_slot(slot, f"[copy] {fname}", src_size, src_size)
                self._debug(f"[slot {slot}] local copy done: {fname}")
                self.complete_slot(slot, src_size)
                return True, fname
            except Exception as ex:
                self._debug(f"[slot {slot}] local copy error: {ex}")
                self.add_issue(f"[local copy fail] {fname}: {ex}")
                self.complete_slot(slot, 0, failed=True)
                return False, fname

        # ── Check local source first ──────────────────────────────────────────
        if local_source and not os.path.exists(dest_path):
            src_path = os.path.join(local_source, fname)
            if os.path.exists(src_path):
                try:
                    ok     = False
                    reason = ''
                    if verify_mode == 'Name':
                        ok     = True
                        reason = 'name'
                    elif verify_mode == 'Size':
                        exact_size = get_exact_size(fname, url, all_hashes, '')
                        src_size   = os.path.getsize(src_path)
                        ok         = bool(exact_size) and src_size == exact_size
                        reason     = 'size ok' if ok else f'size mismatch ({src_size} != {exact_size})'
                    else:  # Hash or Overwrite — always hash-verify local copies
                        expected = all_hashes.get(fname, {})
                        if expected:
                            ok, reason = verify_file(src_path, expected)
                        else:
                            exact_size = get_exact_size(fname, url, all_hashes, '')
                            if exact_size:
                                src_size = os.path.getsize(src_path)
                                ok       = src_size == exact_size
                                reason   = 'size ok' if ok else 'size mismatch'
                            else:
                                ok     = True
                                reason = 'name'
                    if ok:
                        self.dl_pause_event.wait()
                        size = os.path.getsize(src_path)
                        self.update_slot(slot, f"[copy] {fname}", 0, size)
                        shutil.copy2(src_path, dest_path)
                        self.update_slot(slot, f"[copy] {fname}", size, size)
                        # Clean up any leftover .part and .bad files
                        for leftover in (tmp_path, bad_path):
                            if os.path.exists(leftover):
                                os.remove(leftover)
                        self._debug(f"copied [{reason}]: {fname}")
                        self.complete_slot(slot, size)
                        return True, fname
                    else:
                        self._debug(f"local source failed [{reason}]: {fname}")
                except Exception as ex:
                    self._debug(f"local source error [{fname}]: {ex}")

        for attempt in range(1, max_retries + 1):
            cancel_event = threading.Event()
            current_resp = [None]
            self._debug(f"[slot {slot}] attempt {attempt}: {url}")

            def on_stuck():
                cancel_event.set()
                try:
                    if current_resp[0]:
                        current_resp[0].close()
                except Exception:
                    pass

            self.register_stuck(slot, on_stuck)
            try:
                req_headers = dict(headers)
                if is_lolroms_url(url):
                    req_headers.update({
                        'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                                           'Chrome/124.0.0.0 Safari/537.36',
                        'Referer':         'https://lolroms.com/',
                        'Accept':          '*/*',
                    })
                if resume_pos > 0:
                    req_headers['Range'] = f'bytes={resume_pos}-'
                req = urllib.request.Request(url, headers=req_headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    current_resp[0] = resp
                    cl = resp.headers.get('Content-Length')
                    self._debug(f"[slot {slot}] HTTP {resp.status} "
                                f"content-length={cl or '?'}")
                    content_length = int(cl) if cl else 0
                    total      = expected_size or content_length
                    downloaded = resume_pos
                    mode       = 'ab' if resume_pos > 0 else 'wb'
                    with open(tmp_path, mode) as fh:
                        while not cancel_event.is_set():
                            self.dl_pause_event.wait()
                            chunk = resp.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            fh.write(chunk)
                            downloaded += len(chunk)
                            self.update_slot(slot, fname, downloaded, total)

                current_resp[0] = None
                self.unregister_stuck(slot)

                if cancel_event.is_set():
                    raise IOError("Stuck")

                expected = all_hashes.get(fname, {})
                if expected:
                    ok, reason = verify_file(tmp_path, expected)
                    if not ok:
                        os.replace(tmp_path, bad_path)
                        self.add_issue(f"[hash fail] {fname}: {reason}")
                        raise IOError(f"Hash verification failed: {reason}")

                os.replace(tmp_path, dest_path)
                if os.path.exists(bad_path):
                    os.remove(bad_path)

                # Save exact size from Content-Length to size cache (for lolroms)
                if size_cache is not None and size_lock is not None and content_length:
                    with size_lock:
                        size_cache[fname] = content_length
                    save_size_cache(dest_dir, size_cache, size_lock)

                rh   = get_remote_headers(url, headers)
                etag = rh.get('etag')
                if etag:
                    with cache_lock:
                        etag_cache[fname] = etag
                    save_etag_cache(cache_path, etag_cache, cache_lock)

                self.complete_slot(slot, expected_size or downloaded, fname=fname)
                return True, fname

            except Exception as ex:
                self._debug(f"[slot {slot}] ERROR attempt {attempt}: {type(ex).__name__}: {ex}")
                self.unregister_stuck(slot)
                current_resp[0] = None
                resume_pos = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
                if attempt == max_retries:
                    self.complete_slot(slot, 0, failed=True)
                    return False, fname
                # Wait 5 s before retrying, but honour pause and stuck-cancel
                for _ in range(10):
                    self.dl_pause_event.wait()
                    if cancel_event.is_set():
                        break
                    time.sleep(0.5)

        return False, fname

    def _start_download(self):
        if self.dl_running:
            return
        if not self.rom_dict:
            messagebox.showerror('Error', 'Run analysis first.')
            return

        # Route Minerva sources to aria2c engine
        urls = [u.strip() for u in self.url_text.get('1.0', 'end').splitlines() if u.strip()]
        if any(is_minerva_url(u) for u in urls):
            self._get_torrent()
            return

        self._save_settings()

        _raw_dl_lines = [u.strip() for u in self.url_text.get('1.0', 'end').splitlines() if u.strip()]
        urls          = [l for l in _raw_dl_lines if not os.path.isdir(l)]
        dl_dir_lines  = [l for l in _raw_dl_lines if os.path.isdir(l)]
        dest_dir = self._get_dest_dir()
        access   = self.access.get() or None
        secret   = self.secret.get() or None
        max_par  = self.parallel.get()
        max_ret  = self.retries.get()

        local_source = self.local_source.get().strip()

        os.makedirs(dest_dir, exist_ok=True)
        cache_path  = os.path.join(dest_dir, '.etag_cache')
        cache_lock  = threading.Lock()
        etag_cache  = load_etag_cache(cache_path)
        size_cache  = load_size_cache(dest_dir)
        size_lock   = threading.Lock()
        headers     = make_headers(access, secret)

        for slot in range(20):
            if slot < max_par:
                self.dl_slot_widgets[slot]['frame'].pack(fill='x', pady=2)
            else:
                self.dl_slot_widgets[slot]['frame'].pack_forget()

        self.btn_start_dl.config(state='disabled', text='Working...')
        self.dl_lbl_verify.config(text='')
        self.root.update()

        def check_and_run():
            all_hashes   = {}
            verify_mode_now = self.verify_mode.get()
            archive_urls = [u for u in urls if not is_lolroms_url(u) and not is_minerva_url(u)]
            if archive_urls and verify_mode_now in ('Hash', 'Size'):
                # Collect direct_urls for all selected files
                selected_direct_urls = {}  # fname -> direct_url
                for data in self.rom_dict.values():
                    sel = data.get('selected')
                    if not sel:
                        continue
                    fname = sel['filename']
                    direct = sel.get('direct_url', '') or ''
                    if direct and 'archive.org/download/' in direct:
                        selected_direct_urls[fname] = direct

                if selected_direct_urls:
                    # Fetch per-file metadata directly — only for selected files
                    self.root.after(0, lambda n=len(selected_direct_urls): self.dl_lbl_verify.config(
                        text=f'Fetching metadata for {n} selected file(s)...'
                    ))
                    for fname, direct in selected_direct_urls.items():
                        # Extract identifier and filename from direct URL
                        # e.g. https://archive.org/download/sony_ps3_d/Dante%27s...iso
                        parts = direct.split('archive.org/download/')
                        if len(parts) > 1:
                            rest = parts[1]
                            identifier = rest.split('/')[0]
                            # Use per-file metadata endpoint
                            api_url = f"https://archive.org/metadata/{identifier}/files/{quote(fname)}"
                            try:
                                req = urllib.request.Request(api_url, headers=headers)
                                with urllib.request.urlopen(req, timeout=15) as resp:
                                    fdata = json.loads(resp.read().decode('utf-8'))
                                    result_data = fdata.get('result', fdata)
                                    if result_data.get('name') or result_data.get('md5'):
                                        all_hashes[fname] = {
                                            'md5':  result_data.get('md5', ''),
                                            'size': int(result_data.get('size', 0) or 0),
                                        }
                            except Exception:
                                pass
                    self.root.after(0, lambda n=len(all_hashes): self.dl_lbl_verify.config(
                        text=f'Metadata: {n} file(s) loaded'
                    ))
                else:
                    # No direct_urls available — fall back to collection metadata
                    needed_identifiers = set()
                    for base_url in archive_urls:
                        needed_identifiers.add(base_url.rstrip('/').split('/')[-1])
                    self.root.after(0, lambda n=len(needed_identifiers): self.dl_lbl_verify.config(
                        text=f'Fetching metadata from {n} collection(s)...'
                    ))
                    for base_url in archive_urls:
                        all_hashes.update(fetch_file_hashes(base_url, headers))
                self.root.after(0, lambda: self.dl_lbl_verify.config(
                    text=f"Metadata: {len(all_hashes)} files loaded"
                ))
            elif archive_urls and verify_mode_now in ('Name', 'Overwrite'):
                self.root.after(0, lambda: self.dl_lbl_verify.config(
                    text=f'Verify: {verify_mode_now} — skipping metadata fetch'
                ))
            elif not urls:
                self.root.after(0, lambda: self.dl_lbl_verify.config(
                    text='Local source only — skipping metadata fetch'
                ))
            else:
                self.root.after(0, lambda: self.dl_lbl_verify.config(
                    text='lolroms source — skipping metadata fetch'
                ))

            url_map   = {}
            local_map = {}  # fname -> absolute path, built from local_source + any dir_lines
            _recursive = self.recursive_scan.get()
            _scan_dirs = []
            if local_source and os.path.isdir(local_source):
                _scan_dirs.append(local_source)
            _scan_dirs.extend(dl_dir_lines)
            for _dirpath in _scan_dirs:
                if _recursive:
                    for _root, _dirs, _files in os.walk(_dirpath):
                        for _fname in _files:
                            _fpath = os.path.join(_root, _fname)
                            if _fname not in local_map and os.path.isfile(_fpath):
                                local_map[_fname] = _fpath
                else:
                    for _fname in os.listdir(_dirpath):
                        _fpath = os.path.join(_dirpath, _fname)
                        if os.path.isfile(_fpath) and _fname not in local_map:
                            local_map[_fname] = _fpath
            for base_url in urls:
                base_url_stripped = base_url.split('#')[0].rstrip('/')
                for data in self.rom_dict.values():
                    if data['selected']:
                        fname      = data['selected']['filename']
                        direct_url = data['selected'].get('direct_url')
                        if fname not in url_map:
                            if fname in local_map:
                                url_map[fname] = f'local://{local_map[fname]}'
                            elif direct_url:
                                url_map[fname] = direct_url
                            else:
                                url_map[fname] = f"{base_url_stripped}/{quote(fname, safe='')}"
            # Files only in local_source (no URL source) also need entries
            for data in self.rom_dict.values():
                if data['selected']:
                    fname = data['selected']['filename']
                    if fname not in url_map and fname in local_map:
                        url_map[fname] = f'local://{local_map[fname]}'

            to_download = []
            to_skip     = []
            check_lock  = threading.Lock()
            verify_mode = self.verify_mode.get()

            def skip_file(fname, dest_path, reason=''):
                """Mark file as skip, clean up .part, log it."""
                part_path = dest_path + '.part'
                if os.path.exists(part_path):
                    os.remove(part_path)
                    self._debug(f"removed .part: {fname}")
                if reason:
                    self._debug(f"skip [{reason}]: {fname}")
                with check_lock:
                    to_skip.append(fname)

            def check_file(data):
                if not data['selected']:
                    return
                fname     = data['selected']['filename']
                size_str  = data['selected']['size']
                dest_path = os.path.join(dest_dir, fname)
                bad_path  = dest_path + '.bad'
                part_path = dest_path + '.part'
                url       = url_map.get(fname)
                if not url:
                    return

                # ── Local source file — copy with size verification ───────────
                if url.startswith('local://'):
                    src_path = url[len('local://'):]
                    src_size = os.path.getsize(src_path) if os.path.exists(src_path) else 0
                    if os.path.exists(dest_path):
                        dest_size = os.path.getsize(dest_path)
                        if dest_size == src_size:
                            skip_file(fname, dest_path, 'local size ok')
                            return
                        else:
                            self._debug(f"[local] size mismatch dest={dest_size} src={src_size}, re-copying: {fname}")
                    with check_lock:
                        to_download.append((fname, url, src_size))
                    return

                size_b = get_exact_size(fname, url, all_hashes, size_str)

                # Overwrite — always re-download
                if verify_mode == 'Overwrite':
                    with check_lock:
                        to_download.append((fname, url, size_b))
                    return

                # Check .bad file first — verify and recover if it passes
                if not os.path.exists(dest_path) and os.path.exists(bad_path):
                    expected = all_hashes.get(fname, {})
                    if expected:
                        ok, reason = verify_file(bad_path, expected)
                        if ok:
                            if os.path.exists(part_path):
                                os.remove(part_path)
                            os.rename(bad_path, dest_path)
                            self._debug(f"recovered .bad → good: {fname}")
                            skip_file(fname, dest_path)
                            return
                        else:
                            self._debug(f".bad failed [{reason}]: {fname}")

                # File doesn't exist — queue for download
                if not os.path.exists(dest_path):
                    with check_lock:
                        to_download.append((fname, url, size_b))
                    return

                # Name — skip if file exists
                if verify_mode == 'Name':
                    skip_file(fname, dest_path, 'name')
                    return

                # Size — skip if local size matches
                if verify_mode == 'Size':
                    if is_lolroms_url(url):
                        cached_size = size_cache.get(fname)
                        if cached_size:
                            local_size = os.path.getsize(dest_path)
                            if local_size == cached_size:
                                skip_file(fname, dest_path, 'size ok (cached)')
                                return
                            else:
                                os.replace(dest_path, bad_path)
                                self.add_issue(f"[re-dl] {fname}: size mismatch "
                                               f"(local {local_size} != {cached_size})")
                                with check_lock:
                                    to_download.append((fname, url, cached_size))
                                return
                        else:
                            # No cached size yet — fall back to name
                            skip_file(fname, dest_path, 'name (no cached size yet)')
                            return
                    local_size = os.path.getsize(dest_path)
                    if size_b and local_size == size_b:
                        skip_file(fname, dest_path, 'size ok')
                        return
                    elif size_b:
                        os.replace(dest_path, bad_path)
                        self.add_issue(f"[re-dl] {fname}: size mismatch "
                                       f"(local {local_size} != {size_b})")
                        with check_lock:
                            to_download.append((fname, url, size_b))
                    else:
                        skip_file(fname, dest_path, 'size unknown — skipping')
                    return

                # Hash — full verification
                expected = all_hashes.get(fname, {})
                if expected:
                    ok, reason = verify_file(dest_path, expected)
                    if ok:
                        skip_file(fname, dest_path, reason)
                        return
                    os.replace(dest_path, bad_path)
                    self.add_issue(f"[re-dl] {fname}: {reason}")
                elif is_lolroms_url(url):
                    # lolroms has no hash and only rounded listing sizes —
                    # can't reliably verify, so skip by name to avoid false .bad files
                    skip_file(fname, dest_path, 'name (no hash available for lolroms)')
                    return
                else:
                    local_size = os.path.getsize(dest_path)
                    if size_b and local_size == size_b:
                        skip_file(fname, dest_path, f'size ok ({size_b}B)')
                        return
                    elif size_b and local_size != size_b:
                        os.replace(dest_path, bad_path)
                        self.add_issue(f"[re-dl] {fname}: size mismatch "
                                       f"(local {local_size} != {size_b})")
                    else:
                        skip_file(fname, dest_path, 'name')
                        return

                with check_lock:
                    to_download.append((fname, url, size_b))

            all_data    = list(self.rom_dict.values())
            total_check = len(all_data)
            with ThreadPoolExecutor(max_workers=max_par * 4) as ex:
                futures = {ex.submit(check_file, d): d for d in all_data}
                for n, future in enumerate(as_completed(futures), 1):
                    d = futures[future]
                    future.result()
                    fname_check = d['selected']['filename'] if d['selected'] else ''
                    short = fname_check[:80] + '...' if len(fname_check) > 80 else fname_check
                    self.root.after(0, lambda n=n, s=short: (
                        self.dl_lbl_files.config(text=f"Checking {n}/{total_check}"),
                        self.dl_lbl_checking.config(text=s)
                    ))
            self.root.after(0, lambda: self.dl_lbl_checking.config(text=''))

            required_bytes = sum(s for _, _, s in to_download)
            free_bytes     = shutil.disk_usage(dest_dir).free

            if free_bytes < required_bytes:
                proceed = self.root.after(0, lambda: None)  # dummy
                warning_done = threading.Event()
                def ask_space():
                    ans = messagebox.askyesno(
                        'Low Disk Space',
                        f"Not enough free space!\n"
                        f"Need: {format_size(required_bytes)}\n"
                        f"Free: {format_size(free_bytes)}\n\n"
                        f"Continue anyway?"
                    )
                    if not ans:
                        self.btn_start_dl.config(state='normal', text='Start')
                        warning_done.set()
                        return
                    warning_done.set()
                self.root.after(0, ask_space)
                warning_done.wait()
                if not warning_done.is_set():
                    return

            if not to_download:
                self.root.after(0, lambda: messagebox.showinfo(
                    'Done', 'Nothing to download - all files verified.'))
                self.root.after(0, lambda: self.btn_start_dl.config(
                    state='normal', text='Start'))
                return

            confirmed = threading.Event()
            def ask():
                ans = messagebox.askyesno(
                    'Confirm Download',
                    f"Files to download: {len(to_download)}\n"
                    f"Files to skip:     {len(to_skip)}\n"
                    f"Required space:    {format_size(required_bytes)}\n"
                    f"Free space:        {format_size(free_bytes)}\n"
                    f"Hash DB:           {len(all_hashes)} entries\n\n"
                    f"Start?"
                )
                if ans:
                    confirmed.set()
                else:
                    self.btn_start_dl.config(state='normal', text='Start')
            self.root.after(0, ask)
            confirmed.wait()

            # Calculate skipped bytes from actual local file sizes
            skipped_bytes = 0
            for fname in to_skip:
                local_path = os.path.join(dest_dir, fname)
                if os.path.exists(local_path):
                    skipped_bytes += os.path.getsize(local_path)

            with self.dl_lock:
                self.dl_completed_files = 0
                self.dl_failed_files    = 0
                self.dl_skipped_files   = len(to_skip)
                self.dl_completed_bytes = skipped_bytes
                self.dl_total_files     = len(to_download)
                self.dl_total_bytes     = required_bytes + skipped_bytes
                self.dl_start_time      = time.time()
                self.dl_window          = []
                self.dl_failed_list     = []
                self.dl_slots           = {}

            self.dl_running = True
            self._debug(f"Download start: total_files={len(to_download)}, required={format_size(required_bytes)}, skipped_bytes={format_size(skipped_bytes)}, total_bytes={format_size(required_bytes + skipped_bytes)}")
            self.root.after(500, self._dl_tick)
            threading.Thread(target=self._sampler_loop,  daemon=True).start()
            threading.Thread(target=self._watchdog_loop, daemon=True).start()

            import queue as _queue
            work_queue   = _queue.Queue()
            for item in to_download:
                work_queue.put(item)

            active_slots = {}
            mgr_lock     = threading.Lock()
            flags_lock   = threading.Lock()
            slot_flags   = {}   # slot -> 'ok' | 'last' | 'remove'
            total        = len(to_download)
            finished_count = [0]

            with ThreadPoolExecutor(max_workers=20) as executor:

                def submit_slot(slot, fname, url, size):
                    dest_path = os.path.join(dest_dir, fname)
                    self.update_slot(slot, fname, 0, size or 1)
                    return executor.submit(
                        self._download_file, slot, fname, url, dest_path,
                        headers, size, etag_cache, cache_lock, cache_path,
                        max_ret, all_hashes, local_source, verify_mode,
                        size_cache, size_lock, dest_dir,
                    )

                def manager():
                    draining        = False
                    target_par      = max_par
                    queue_exhausted = False
                    self._debug(f"Manager started, par={max_par}, total={total}")
                    while finished_count[0] < total and self.dl_running:
                        par = self.parallel.get()

                        with mgr_lock:
                            # ── Detect par change ────────────────────────────
                            if par < target_par:
                                # Reduction — start draining
                                draining   = True
                                target_par = par
                                # Hide bars for idle slots above new par
                                for s in range(par, 20):
                                    if s not in active_slots:
                                        self.root.after(0, lambda sl=s:
                                            self.dl_slot_widgets[sl]['frame'].pack_forget())
                            elif par > target_par:
                                # Increase — stop draining, show new bars
                                draining   = False
                                target_par = par
                                for s in range(par):
                                    self.root.after(0, lambda sl=s:
                                        self.dl_slot_widgets[sl]['frame'].pack(fill='x', pady=2))

                            # ── Collect finished slots ───────────────────────
                            for slot in list(active_slots.keys()):
                                if not active_slots[slot].done():
                                    continue
                                fut = active_slots.pop(slot)
                                try:
                                    success, fn = fut.result()
                                except Exception:
                                    success, fn = False, ''
                                if not success and fn:
                                    self.add_issue(f"[failed] {fn}")
                                finished_count[0] += 1
                                if draining:
                                    # Hide this bar and repack remaining to close gap
                                    def _hide_repack(s=slot):
                                        self.dl_slot_widgets[s]['frame'].pack_forget()
                                        # Repack all visible bars in order to close gap
                                        visible = [i for i in range(20)
                                                   if self.dl_slot_widgets[i]['frame'].winfo_ismapped()]
                                        for i in visible:
                                            self.dl_slot_widgets[i]['frame'].pack_forget()
                                        for i in visible:
                                            self.dl_slot_widgets[i]['frame'].pack(fill='x', pady=2)
                                        self.slots_canvas.yview_moveto(0)
                                    self.root.after(0, _hide_repack)

                            # ── Check if drain complete ──────────────────────
                            if draining and len(active_slots) <= target_par:
                                draining = False
                                # Repack bars in order — hide above target, show below
                                def _repack(tp=target_par):
                                    for s in range(20):
                                        self.dl_slot_widgets[s]['frame'].pack_forget()
                                    for s in range(tp):
                                        self.dl_slot_widgets[s]['frame'].pack(fill='x', pady=2)
                                    self.slots_canvas.yview_moveto(0)
                                self.root.after(0, _repack)

                            # ── Fill free slots ──────────────────────────────
                            if not draining:
                                for slot in range(target_par):
                                    if slot not in active_slots:
                                        try:
                                            fn, url, size = work_queue.get_nowait()
                                            active_slots[slot] = submit_slot(slot, fn, url, size)
                                            self.root.after(0, lambda s=slot:
                                                self.dl_slot_widgets[s]['frame'].pack(fill='x', pady=2))
                                        except _queue.Empty:
                                            if not queue_exhausted:
                                                queue_exhausted = True
                                            break
                                if queue_exhausted:
                                    # Repack — show only active slots, hide idle ones
                                    active = sorted(active_slots.keys())
                                    def _repack_active(slots=active):
                                        for s in range(20):
                                            self.dl_slot_widgets[s]['frame'].pack_forget()
                                        for s in slots:
                                            self.dl_slot_widgets[s]['frame'].pack(fill='x', pady=2)
                                    self.root.after(0, _repack_active)

                        time.sleep(0.2)

                    # Wait for remaining active slots to finish
                    while active_slots:
                        with mgr_lock:
                            for slot in list(active_slots.keys()):
                                if active_slots[slot].done():
                                    try:
                                        success, fn = active_slots.pop(slot).result()
                                    except Exception:
                                        success, fn = False, ''
                                    if not success and fn:
                                        self.add_issue(f"[failed] {fn}")
                                    finished_count[0] += 1
                                    self.root.after(0, lambda s=slot:
                                        self.dl_slot_widgets[s]['frame'].pack_forget())
                        time.sleep(0.2)

                threading.Thread(target=manager, daemon=True).start()

                while finished_count[0] < total and self.dl_running:
                    time.sleep(0.5)

            self.dl_running = False
            self.root.after(0, self._dl_done)

        threading.Thread(target=check_and_run, daemon=True).start()

    def _show_gh_token_field(self):
        """Focus the GitHub token entry field."""
        if hasattr(self, '_gh_token_entry'):
            self._gh_token_entry.focus_set()

    # Platform name keywords → compat emulator name
    _PLATFORM_TO_EMULATOR = {
        'playstation 3': 'RPCS3 (PS3)',
        'playstation 2': 'PCSX2 (PS2)',
        'playstation vita': 'Vita3K (PS Vita)',
        'playstation portable': 'PPSSPP (PSP)',
        'psp': 'PPSSPP (PSP)',
        'nintendo switch': 'Eden (Switch)',
        'nintendo 3ds': 'Azahar (3DS)',
        'nintendo wii u': 'CEMU (Wii U)',
        'xbox 360': 'Xenia (Xbox 360)',
        'ps3': 'RPCS3 (PS3)',
        'ps2': 'PCSX2 (PS2)',
        'psvita': 'Vita3K (PS Vita)',
        'switch': 'Eden (Switch)',
        '3ds': 'Azahar (3DS)',
        'wii u': 'CEMU (Wii U)',
    }

    def _auto_set_compat_emulator(self, platform_name: str):
        """Auto-set compat emulator dropdown based on platform name."""
        if not platform_name or not hasattr(self, 'compat_source'):
            return
        pl = platform_name.lower()
        for keyword, emulator in self._PLATFORM_TO_EMULATOR.items():
            if keyword in pl:
                if emulator in COMPAT_SOURCES:
                    self.compat_source.set(emulator)
                return

    def _compat_prepopulate(self):
        """Fill the compat table with current selection (Not found) without re-fetching."""
        if not hasattr(self, 'compat_tree'):
            return
        self.compat_tree.delete(*self.compat_tree.get_children())
        rgx = self._get_type_filter_re() if hasattr(self, 'filter_var') else None
        total_size = 0
        n = 0
        for fname, data in self.rom_dict.items():
            if fname.startswith('__missing__'):
                continue
            sel = data.get('selected')
            if not sel:
                continue
            # Respect type filter
            if rgx and not rgx.search(sel.get('filename', fname)):
                continue
            size_str = sel.get('size', '')
            self.compat_tree.insert('', 'end',
                values=('●', fname, size_str, ''),
                tags=('Not found',))
            total_size += parse_size_bytes(size_str)
            n += 1
        self._compat_all_iids = list(self.compat_tree.get_children())
        self._compat_active_filter = None
        self._compat_status_map = {}  # cleared — must re-fetch compat after selection changes
        self.lbl_compat_summary.config(text=f'{n} files  —  {format_size(total_size)} total')
        if not getattr(self, '_compat_status_map', {}):
            self.lbl_compat_status.config(text='Press Fetch Compatibility to match.', fg=FG2)
        self._populate_compat_cards()

    def _build_compat(self):
        """Build the Compatibility tab."""
        f = self.tab_compat
        PAD = 16

        # ── Controls row ─────────────────────────────────────────────────────
        # ── Results title + cards ─────────────────────────────────────────────
        _compat_title_row = tk.Frame(f, bg=BG)
        _compat_title_row.pack(fill='x', padx=PAD, pady=(PAD, 8))
        self.lbl_compat_title = tk.Label(_compat_title_row, text='Compatibility Results',
                                         bg=BG, fg=FG, font=FONT_XL)
        self.lbl_compat_title.pack(side='left')
        tk.Label(_compat_title_row, text='Click card to search  ·  Double-click card to select/deselect group',
                 bg=BG, fg='#555555', font=FONT_SM).pack(side='right')
        self.compat_card_frame = tk.Frame(f, bg=BG)
        self.compat_card_frame.pack(fill='x', padx=PAD)

        ctrl = tk.Frame(f, bg=BG)
        ctrl.pack(fill='x', padx=PAD, pady=(PAD, 4))

        tk.Label(ctrl, text='Emulator:', bg=BG, fg=FG2, font=FONT_SM).pack(side='left')
        self.compat_source = tk.StringVar(value=sorted(COMPAT_SOURCES.keys())[0])
        ttk.Combobox(ctrl, textvariable=self.compat_source,
                     values=sorted(COMPAT_SOURCES.keys()),
                     state='readonly', font=FONT_SM, width=20).pack(side='left', padx=(4, 12))


        self.btn_fetch_compat = tk.Button(ctrl, text='Fetch Compatibility', bg=ACC, fg=FG,
                                          font=FONT_SM, relief='flat', padx=10,
                                          command=self._fetch_compat)
        self.btn_fetch_compat.pack(side='left')


        self.lbl_compat_status = tk.Label(ctrl, text='', bg=BG, fg=YELLOW, font=FONT_SM)
        self.lbl_compat_status.pack(side='left', padx=(12, 0))

        # Threshold deselect — right side (must be packed before left-side widgets)



        self.compat_threshold = tk.StringVar(value='Playable')


        # GH token — left of "Deselect below:" on the same ctrl row
        self.github_token.trace_add('write', lambda *_: self._save_settings())
        self._gh_token_link = tk.Label(ctrl, text='Get token', bg=BG, fg=ACC,
                                       font=FONT_SM, cursor='hand2')
        self._gh_token_link.bind('<Button-1>', lambda e: __import__('webbrowser').open(
            'https://github.com/settings/personal-access-tokens/new'))
        self._gh_token_link.pack(side='right', padx=(0, 16))
        self._gh_token_entry = tk.Entry(ctrl, textvariable=self.github_token, bg=BG2, fg=FG,
                                        font=FONT_SM, insertbackground=FG, relief='flat',
                                        borderwidth=3, show='*', width=5)
        self._gh_token_entry.pack(side='right', padx=(4, 0))
        self._gh_token_lbl = tk.Label(ctrl, text='GH Token:', bg=BG, fg=FG2, font=FONT_SM)
        self._gh_token_lbl.pack(side='right', padx=(16, 0))

        # ── Legend ────────────────────────────────────────────────────────────
        legend_row = tk.Frame(f, bg=BG)
        legend_row.pack(fill='x', padx=PAD, pady=(0, 4))
        tk.Label(legend_row, text='Legend:', bg=BG, fg='#555555',
                 font=FONT_SM).pack(side='left', padx=(0, 6))
        for label, color in [
            ('Perfect',              '#4a9eff'),
            ('Playable',             GREEN),
            ('Ingame',               YELLOW),
            ('Intro / Menu',         '#ff8c00'),
            ('Nothing / Unplayable', RED),
            ('Unknown',              '#9b59b6'),
            ('Not found',            FG2),
        ]:
            tk.Label(legend_row, text=f'● {label}',
                     bg=BG, fg=color, font=FONT_SM).pack(side='left', padx=(0, 10))


        # ── Search row ───────────────────────────────────────────────────────
        compat_sf_row = tk.Frame(f, bg=BG)
        compat_sf_row.pack(fill='x', padx=PAD, pady=(0, 4))
        tk.Label(compat_sf_row, text='Search:', bg=BG, fg=FG2,
                 font=FONT_SM).pack(side='left', padx=(0, 6))
        self.compat_search_var = tk.StringVar()
        compat_search_entry = tk.Entry(compat_sf_row, textvariable=self.compat_search_var,
                                       bg=BG2, fg=FG, font=FONT_SM,
                                       insertbackground=FG, relief='flat', borderwidth=4)
        compat_search_entry.pack(side='left', fill='x', expand=True)
        tk.Button(compat_sf_row, text='✕', bg=BG3, fg=FG2, font=FONT_SM,
                  relief='flat', padx=6,
                  command=lambda: self.compat_search_var.set('')).pack(side='left', padx=(4, 0))
        tk.Button(compat_sf_row, text='🕸', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6, pady=0, height=1,
                  command=self._compat_select_only_visible).pack(side='left', padx=(4, 0))
        tk.Button(compat_sf_row, text='+', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=lambda: self._compat_add_remove_visible(select=True)).pack(side='left', padx=(4, 0))
        tk.Button(compat_sf_row, text='-', bg=BG3, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=lambda: self._compat_add_remove_visible(select=False)).pack(side='left', padx=(4, 0))
        tk.Frame(compat_sf_row, bg=BG, width=16).pack(side='left')
        tk.Label(compat_sf_row, text='Deselect below:', bg=BG, fg=FG2,
                 font=FONT_SM).pack(side='left', padx=(0, 4))
        ttk.Combobox(compat_sf_row, textvariable=self.compat_threshold,
                     values=['Perfect', 'Playable', 'Ingame', 'Intro', 'Nothing'],
                     state='readonly', font=FONT_SM, width=10).pack(side='left', padx=(0, 4))
        tk.Button(compat_sf_row, text='Apply', bg=ACC, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._compat_apply_threshold).pack(side='left', padx=(0, 4))
        tk.Button(compat_sf_row, text='Reset', bg=RED, fg=FG, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._reset_compat_selection).pack(side='left', padx=(0, 4))
        self.compat_search_var.trace_add('write', lambda *_: self._apply_compat_search())

        # ── Table — same style as Selection tab ───────────────────────────────
        list_frame = tk.Frame(f, bg=BG)
        list_frame.pack(fill='both', expand=True, padx=PAD, pady=(0, PAD))

        tree_frame = tk.Frame(list_frame, bg=BG)
        tree_frame.pack(fill='both', expand=True)

        sb = ttk.Scrollbar(tree_frame, orient='vertical')
        sb.pack(side='right', fill='y')

        self.compat_tree = ttk.Treeview(
            tree_frame, style='Analysis.Treeview',
            columns=('status', 'filename', 'size', 'matched'),
            show='headings',
            yscrollcommand=sb.set,
        )
        self._compat_sort_col = None
        self._compat_sort_rev = False

        def _compat_sort(col):
            STATUS_SORT = {'Perfect': 0, 'Playable': 1, 'Good': 1, 'Ingame +': 2,
                           'Runs': 2, 'Gameplay': 2, 'Ingame -': 3, 'Ingame': 3,
                           'Intro': 4, 'Starts': 4, 'Menu': 4, 'Loads': 4,
                           'Bootable': 5, 'Loadable': 5, 'Nothing': 6,
                           'Unplayable': 6, "Won't Fix": 6,
                           'Unknown': 7, 'Not found': 99}
            rev = (self._compat_sort_col == col) and not self._compat_sort_rev
            self._compat_sort_col, self._compat_sort_rev = col, rev
            rows = [(self.compat_tree.set(iid, col),
                     self.compat_tree.item(iid, 'values'),
                     self.compat_tree.item(iid, 'tags'),
                     iid)
                    for iid in self.compat_tree.get_children()]
            if col == 'size':
                key = lambda r: parse_size_bytes(r[0])
            elif col == 'status':
                key = lambda r: STATUS_SORT.get(r[2][0] if r[2] else 'Not found', 99)
            else:
                key = lambda r: r[0].lower()
            rows.sort(key=key, reverse=rev)
            for i, (_, vals, tags, iid) in enumerate(rows):
                self.compat_tree.move(iid, '', i)
            # Update heading arrows
            for c, lbl in [('status',''), ('filename','Filename'), ('size','Size'), ('matched','Matched As')]:
                arrow = (' ▲' if not rev else ' ▼') if c == col else ''
                self.compat_tree.heading(c, text=lbl + arrow)

        self.compat_tree.heading('status',   text='',             anchor='center', command=lambda: _compat_sort('status'))
        self.compat_tree.heading('filename', text='Filename',     anchor='w',      command=lambda: _compat_sort('filename'))
        self.compat_tree.heading('size',     text='Size',         anchor='e',      command=lambda: _compat_sort('size'))
        self.compat_tree.heading('matched',  text='Matched As',   anchor='w',      command=lambda: _compat_sort('matched'))
        self.compat_tree.column('status',   width=30,  stretch=False, anchor='center')
        self.compat_tree.column('filename', width=480, stretch=True,  anchor='w')
        self.compat_tree.column('size',     width=80,  stretch=False, anchor='e')
        self.compat_tree.column('matched',  width=280, stretch=True,  anchor='w')

        # Tag colours matching the legend
        for tag, color in [
            ('Perfect', '#4a9eff'),   ('Playable', GREEN),  ('Good', GREEN),
            ('Ingame +', GREEN),  ('Ingame -', YELLOW), ('Ingame', YELLOW),
            ('Runs', YELLOW),     ('Gameplay', YELLOW),
            ('Intro', '#ff8c00'), ('Starts', '#ff8c00'), ('Menu', '#ff8c00'),
            ('Loads', '#ff8c00'), ('Bootable', RED),    ('Loadable', RED),
            ('Nothing', RED),     ('Unplayable', RED),  ("Won't Fix", RED),
            ('Unknown', '#9b59b6'),
            ('Not found', FG2),
        ]:
            self.compat_tree.tag_configure(tag, foreground=color)

        self.compat_tree.pack(fill='both', expand=True)
        sb.config(command=self.compat_tree.yview)
        self.compat_tree.bind('<Double-Button-1>', self._on_compat_click)
        self.compat_tree.bind('<space>', self._on_compat_click)

        self.lbl_compat_summary = tk.Label(f, text='', bg=BG, fg=FG2, font=FONT_SM)
        self.lbl_compat_summary.pack(anchor='e', padx=PAD)
        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(pady=(0, PAD))
        tk.Button(btn_row, text='Download', bg=ACC, fg=FG, font=FONT_LG,
                  relief='flat', padx=20, pady=8,
                  command=self._go_to_download).pack(side='left', padx=(0, 8))
        tk.Button(btn_row, text='Export DAT', bg=BG3, fg=FG, font=FONT_LG,
                  relief='flat', padx=20, pady=8,
                  command=lambda: self._export_dat(self.compat_tree)).pack(side='left')


    def _reset_compat_selection(self):
        """Restore selection to the state it was before compat fetch ran."""
        snapshot = getattr(self, '_pre_compat_snapshot', None)
        if not snapshot:
            messagebox.showinfo('Reset', 'No pre-compat snapshot found. Fetch compatibility first.')
            return
        for title, sel in snapshot.items():
            if title in self.rom_dict:
                self.rom_dict[title]['selected'] = sel
        self._compat_prepopulate()
        self._populate_cards()
        self.lbl_compat_status.config(text='Selection restored to pre-compat state.', fg=GREEN)

    def _fetch_compat(self):
        """Fetch compatibility data for the selected emulator and match against selected titles."""
        if not self.rom_dict:
            messagebox.showerror('Error', 'Run GoGet! first to build the selection.')
            return

        src_name = self.compat_source.get()
        src = COMPAT_SOURCES.get(src_name)
        if not src:
            return

        # Save snapshot of current selection before compat modifies it
        self._pre_compat_snapshot = {
            title: data['selected']
            for title, data in self.rom_dict.items()
        }
        self.btn_fetch_compat.config(state='disabled')
        self.lbl_compat_status.config(text=f'Fetching {src_name}...', fg=YELLOW)
        self.compat_tree.delete(*self.compat_tree.get_children())

        # Pre-populate with all selected titles as Not found
        selected_titles = []
        total_size = 0
        _rgx = self._get_type_filter_re() if hasattr(self, 'filter_var') else None
        for fname, data in self.rom_dict.items():
            if fname.startswith('__missing__'):
                continue
            sel = data.get('selected')
            if sel:
                if _rgx and not _rgx.search(sel.get('filename', fname)):
                    continue
                size_str = sel.get('size', '')
                base = re.sub(r'\s*\([^)]*\)', '', os.path.splitext(fname)[0]).strip()
                selected_titles.append((base, fname, size_str))
                total_size += parse_size_bytes(size_str)
                self.compat_tree.insert('', 'end',
                    values=('●', fname, size_str, ''),
                    tags=('Not found',))
        n = len(selected_titles)
        self.lbl_compat_summary.config(
            text=f'{n} files  —  {format_size(total_size)} total')
        self._compat_selected_titles = selected_titles

        def _do():
            _token = self.github_token.get().strip()
            # Monkey-patch _gh_headers to use the current token for this fetch
            import sys as _sys
            _mod = _sys.modules[__name__] if __name__ in _sys.modules else _sys.modules['__main__']
            _mod._github_token = _token
            try:
                def _progress(msg):
                    self.root.after(0, lambda m=msg: self.lbl_compat_status.config(text=m, fg=YELLOW))
                import inspect as _ins
                _fetch_fn = src['fetch']
                if 'progress_cb' in _ins.signature(_fetch_fn).parameters:
                    compat_map = _fetch_fn(progress_cb=_progress)
                else:
                    compat_map = _fetch_fn()
                self.root.after(0, lambda: self.lbl_compat_status.config(
                    text=f'Matching {len(compat_map):,} entries...', fg=YELLOW))
                self._debug(f'Compat map: {len(compat_map)} entries, sample: {list(compat_map.items())[:3]}')
                if len(compat_map) == 0:
                    def _show_rate_limit_err():
                        self.lbl_compat_status.config(
                            text='Github limit reached. Enter github token:',
                            fg=RED)
                        self._show_gh_token_field()
                        self.btn_fetch_compat.config(state='normal')
                    self.root.after(0, _show_rate_limit_err)
                    return

                selected_titles = self._compat_selected_titles
                if selected_titles:
                    t0, f0, s0 = selected_titles[0]
                    self._debug(f'First selected: title={t0!r} norm={normalize_title(t0)!r}')

                MATCH_STATUS_RANK = {'Perfect': 0, 'Playable': 1, 'Good': 1, 'Ingame +': 2,
                                     'Runs': 2, 'Gameplay': 2, 'Ingame -': 3, 'Ingame': 3,
                                     'Intro': 4, 'Starts': 4, 'Menu': 4, 'Loads': 4,
                                     'Bootable': 5, 'Loadable': 5, 'Nothing': 6,
                                     'Unplayable': 6, "Won't Fix": 6,
                                     'Unknown': 7, 'Not found': 99}
                results = []
                _VARIANT_C = re.compile(
                    r'\b(demo|soundtrack|beta|promo|trial|sample|move support)\b', re.IGNORECASE)

                # Pre-filter compat_map and build token index for fast candidate lookup
                self.root.after(0, lambda: self.lbl_compat_status.config(
                    text='Building index...', fg=YELLOW))
                filtered_compat = {
                    norm: val for norm, val in compat_map.items()
                    if not _VARIANT_C.search(norm)
                }
                from collections import defaultdict as _dd
                _token_index = _dd(list)
                for norm, val in filtered_compat.items():
                    for tok in _ctokenize(norm) - _STOPWORDS_C:
                        _token_index[tok].append(norm)

                total_titles = len(selected_titles)
                for i, (title, fname, size_str) in enumerate(selected_titles):
                    best_score, best_norm, best_status, best_color = 0.0, '', 'Not found', FG2
                    # Candidate set: compat entries sharing at least one non-stop token
                    title_tokens = _ctokenize(title) - _STOPWORDS_C
                    candidates = set()
                    for tok in title_tokens:
                        candidates.update(_token_index.get(tok, []))
                    # Fall back to full map if no token overlap (e.g. pure number titles)
                    if not candidates:
                        candidates = filtered_compat.keys()
                    for compat_norm in candidates:
                        val = filtered_compat.get(compat_norm)
                        if not val:
                            continue
                        status, color = val
                        score = _cscore(title, compat_norm)
                        if score > best_score:
                            best_score, best_norm = score, compat_norm
                            best_status, best_color = status, color
                    self._debug(f'  [{fname}] best={best_score:.3f} matched={best_norm!r} status={best_status}')
                    _has_cjk = lambda s: any('一' <= c <= '鿿' or '぀' <= c <= 'ヿ' for c in s)
                    _cjk_mismatch = _has_cjk(title) != _has_cjk(best_norm)
                    if best_score >= 0.6 and not _cjk_mismatch:
                        results.append((fname, size_str, best_status, best_color, best_norm))
                    else:
                        results.append((fname, size_str, 'Not found', FG2, ''))
                    matched_so_far = sum(1 for _,_,s,_,_ in results if s != 'Not found')
                    self.root.after(0, lambda c=i+1, t=total_titles, m=matched_so_far:
                        self.lbl_compat_status.config(
                            text=f'{c}/{t}  matched: {m}',
                            fg=YELLOW))
                def _update():
                  try:
                    from collections import Counter
                    status_counts = Counter(s for _,_,s,_,_ in results)
                    matched = sum(n for s,n in status_counts.items() if s != 'Not found')
                    grp_parts = []
                    for grp, statuses in [
                        ('Perfect',   {'Perfect'}),
                        ('Playable',  {'Playable','Good'}),
                        ('Ingame',    {'Ingame','Ingame +','Ingame -','Runs','Gameplay'}),
                        ('Intro/Menu',{'Intro','Menu','Starts','Loads'}),
                        ('Unplayable',{"Won't Fix",'Bootable','Loadable','Nothing','Unplayable'}),
                        ('Unknown',   {'Unknown'}),
                        ('Not found', {'Not found'}),
                    ]:
                        n = sum(status_counts.get(s,0) for s in statuses)
                        if n:
                            grp_parts.append(f'{grp} {n}')
                    count_str = '  ·  '.join(grp_parts)
                    self.lbl_compat_status.config(
                        text=f'{len(results)}/{total_titles}',
                        fg=GREEN)
                    self.compat_tree.delete(*self.compat_tree.get_children())
                    # Store compat status map keyed by rom_dict key for Apply to use
                    self._compat_status_map = {fname: status for fname, _, status, _, _ in results}
                    results.sort(key=lambda x: x[0].lower())
                    for fname, size_str, status, color, matched_as in results:
                        self.compat_tree.insert('', 'end',
                            values=('●', fname, size_str, matched_as),
                            tags=(status,))
                    self.btn_fetch_compat.config(state='normal')
                    self._compat_all_iids = list(self.compat_tree.get_children())
                    self._compat_active_filter = None
                    self._populate_compat_cards()
                  except Exception as _ue:
                    import traceback as _tb
                    self.lbl_compat_status.config(
                        text=f'_update error: {_ue}  {_tb.format_exc().splitlines()[-1]}', fg=RED)
                self.root.after(0, _update)

            except Exception as ex:
                self.root.after(0, lambda e=ex: self.lbl_compat_status.config(
                    text=f'Error: {e}', fg=RED))
                self.root.after(0, lambda: self.btn_fetch_compat.config(state='normal'))
                if 'rate limit' in str(ex).lower() or 'token' in str(ex).lower():
                    self.root.after(0, self._show_gh_token_field)
                self._debug(f'Compat fetch error: {ex}')

        threading.Thread(target=_do, daemon=True).start()


    def _on_compat_click(self, event):
        """Toggle selection of a title in the compatibility table on double-click or space."""
        if event.type == tk.EventType.KeyPress:
            iid = self.compat_tree.selection()[0] if self.compat_tree.selection() else None
        else:
            region = self.compat_tree.identify_region(event.x, event.y)
            iid    = self.compat_tree.identify_row(event.y)
            if region != 'cell' or not iid:
                # Fall back to treeview's own selection (set by the preceding Button-1)
                sel = self.compat_tree.selection()
                iid = sel[0] if sel else None
        if not iid:
            return
        fname      = self.compat_tree.set(iid, 'filename')
        size_str   = self.compat_tree.set(iid, 'size')
        matched_as = self.compat_tree.set(iid, 'matched')
        tags = self.compat_tree.item(iid, 'tags')
        if tags and tags[0] == 'Not found':
            return
        data = self.rom_dict.get(fname)
        if not data:
            return
        if data.get('selected'):
            data['_prev_selected'] = data['selected']
            data['selected'] = None
            self.compat_tree.item(iid, values=('○', fname, size_str, matched_as), tags=tags)
        else:
            prev = data.get('_prev_selected')
            insts = data.get('instances', [])
            restore = prev or (insts[0] if insts else None)
            if restore:
                data['selected'] = restore
            self.compat_tree.item(iid, values=('●', fname, size_str, matched_as), tags=tags)
        sel_bytes = sum(
            parse_size_bytes(d['selected'].get('size', '0'))
            for d in self.rom_dict.values() if d.get('selected'))
        n_sel = sum(1 for d in self.rom_dict.values() if d.get('selected'))
        self.lbl_compat_summary.config(text=f'{n_sel} files  —  {format_size(sel_bytes)} total')
        self._populate_cards()
        self._populate_compat_cards()
        return 'break'

    def _compat_add_remove_visible(self, select: bool):
        """Add or remove visible compat rows without touching non-visible selection state."""
        all_iids = getattr(self, '_compat_all_iids', None) or []
        visible = set(self.compat_tree.get_children())
        fname_map = self._fname_to_romdata()
        for iid in all_iids:
            if iid not in visible:
                continue
            try:
                vals = list(self.compat_tree.item(iid, 'values'))
                if not vals: continue
                fname = vals[1] if len(vals) > 1 else ''
                tags  = self.compat_tree.item(iid, 'tags')
            except Exception:
                continue
            entry = fname_map.get(fname)
            if entry is None:
                continue
            _key, data = entry
            if select and not data.get('selected'):
                inst = next((i for i in data.get('instances', [])
                             if i['filename'] == fname), None)
                if inst is None and data.get('instances'):
                    inst = select_best(data['instances']) or data['instances'][0]
                if inst:
                    data['selected'] = {'filename':   inst['filename'],
                                        'size':       inst['size'],
                                        'direct_url': inst.get('direct_url')}
                    vals[0] = '●'
                    self.compat_tree.item(iid, values=vals, tags=tags)
            elif not select and data.get('selected'):
                data['selected'] = None
                vals[0] = '○'
                self.compat_tree.item(iid, values=vals, tags=tags)
        self._populate_cards()
        self._populate_compat_cards()

    def _apply_compat_search(self):
        """Filter compat tree rows to those matching the search string."""
        query = self.compat_search_var.get().strip()
        all_iids = getattr(self, '_compat_all_iids', None) or []
        match = self._compile_search(query) if query else None
        for i, iid in enumerate(all_iids):
            try:
                vals = self.compat_tree.item(iid, 'values')
                fname = vals[1] if vals and len(vals) > 1 else ''
                if match and not match(fname):
                    self.compat_tree.detach(iid)
                else:
                    self.compat_tree.reattach(iid, '', i)
            except Exception:
                pass
        self._compat_active_filter = None

    def _compat_select_only_visible(self):
        """Select only compat rows currently visible, deselect all others."""
        all_iids = getattr(self, '_compat_all_iids', None) or []
        visible = set(self.compat_tree.get_children())
        fname_map = self._fname_to_romdata()
        for iid in all_iids:
            try:
                vals = list(self.compat_tree.item(iid, 'values'))
                if not vals: continue
                fname = vals[1] if len(vals) > 1 else ''
                size  = vals[2] if len(vals) > 2 else '0'
                entry = fname_map.get(fname)
                if entry is None: continue
                _key, data = entry
                if iid in visible:
                    if not data.get('selected'):
                        inst = next((i for i in data.get('instances', [])
                                     if i['filename'] == fname), None)
                        if inst:
                            data['selected'] = {'filename':   fname,
                                                'size':       inst['size'],
                                                'direct_url': inst.get('direct_url')}
                        else:
                            data['selected'] = {'filename': fname, 'size': size, 'direct_url': None}
                        vals[0] = '●'
                        tags = self.compat_tree.item(iid, 'tags')
                        self.compat_tree.item(iid, values=vals,
                                              tags=(tags[0],) if tags else ())
                else:
                    if data.get('selected'):
                        data['selected'] = None
                        vals[0] = '○'
                        self.compat_tree.item(iid, values=vals)
            except Exception:
                pass
        self._populate_cards()
        self._populate_compat_cards()

    def _compat_filter(self, statuses):
        """Show only rows whose tag is in statuses; toggle off if already active."""
        all_iids = getattr(self, '_compat_all_iids', None) or []
        # Restore all
        for i, iid in enumerate(all_iids):
            try: self.compat_tree.reattach(iid, '', i)
            except Exception: pass
        active = getattr(self, '_compat_active_filter', None)
        if active == statuses:
            self._compat_active_filter = None
            return
        self._compat_active_filter = statuses
        for iid in all_iids:
            try:
                tags = self.compat_tree.item(iid, 'tags')
                s = tags[0] if tags else 'Not found'
                if s not in statuses:
                    self.compat_tree.detach(iid)
            except Exception:
                pass

    def _populate_compat_cards(self):
        """Refresh stat cards above the compatibility table."""
        if not hasattr(self, 'compat_card_frame'):
            return
        for w in self.compat_card_frame.winfo_children():
            w.destroy()

        # Count over ALL iids (including detached/filtered)
        # Track selected (●) vs total per status — mirrors Selection tab card style
        all_iids = getattr(self, '_compat_all_iids', None) or list(self.compat_tree.get_children())
        counts_total    = {}   # status -> total row count
        counts_selected = {}   # status -> selected (●) row count
        total_size = 0
        sel_count  = 0
        sel_bytes  = 0
        for iid in all_iids:
            try:
                tags = self.compat_tree.item(iid, 'tags')
                vals = self.compat_tree.item(iid, 'values')
            except Exception:
                continue
            status = tags[0] if tags else 'Not found'
            is_sel = bool(vals) and vals[0] == '●'  # ●
            size_b = parse_size_bytes(vals[2]) if len(vals) > 2 else 0
            counts_total[status] = counts_total.get(status, 0) + 1
            total_size += size_b
            if is_sel:
                counts_selected[status] = counts_selected.get(status, 0) + 1
                sel_count += 1
                sel_bytes += size_b

        total = len(all_iids)
        def _filter_selected():
            all_iids_ = getattr(self, '_compat_all_iids', None) or []
            for i, iid in enumerate(all_iids_):
                try: self.compat_tree.reattach(iid, '', i)
                except Exception: pass
            active = getattr(self, '_compat_active_filter', None)
            if active == '__selected__':
                self._compat_active_filter = None
                return
            self._compat_active_filter = '__selected__'
            for iid in all_iids_:
                try:
                    vals = self.compat_tree.item(iid, 'values')
                    if not vals or vals[0] != '\u25cf':
                        self.compat_tree.detach(iid)
                except Exception:
                    pass
        def _clear_filter():
            all_iids_ = getattr(self, '_compat_all_iids', None) or []
            for i, iid in enumerate(all_iids_):
                try: self.compat_tree.reattach(iid, '', i)
                except Exception: pass
            self._compat_active_filter = None
        self._make_card(self.compat_card_frame, 'Total',         str(total),              FG,    command=_clear_filter)
        self._make_card(self.compat_card_frame, 'Total Size',    format_size(total_size), FG)
        self._make_card(self.compat_card_frame, 'Selected',      str(sel_count),          GREEN, command=_filter_selected)
        self._make_card(self.compat_card_frame, 'Selected Size', format_size(sel_bytes),  GREEN)

        GROUP_MAP = {
            'Perfect':    ('Perfect',    '#4a9eff'),
            'Playable':   ('Playable',   GREEN),
            'Good':       ('Playable',   GREEN),
            'Ingame +':   ('Ingame',     YELLOW),
            'Ingame -':   ('Ingame',     YELLOW),
            'Ingame':     ('Ingame',     YELLOW),
            'Runs':       ('Ingame',     YELLOW),
            'Gameplay':   ('Ingame',     YELLOW),
            'Intro':      ('Intro/Menu', '#ff8c00'),
            'Starts':     ('Intro/Menu', '#ff8c00'),
            'Menu':       ('Intro/Menu', '#ff8c00'),
            'Loads':      ('Intro/Menu', '#ff8c00'),
            'Bootable':   ('Unplayable', RED),
            'Loadable':   ('Unplayable', RED),
            'Nothing':    ('Unplayable', RED),
            'Unplayable': ('Unplayable', RED),
            "Won't Fix":  ('Unplayable', RED),
            'Unknown':    ('Unknown',    '#9b59b6'),
            'Not found':  ('Not found',  FG2),
        }
        # Build group tallies: selected / total per group label
        grp_sel      = {}
        grp_total    = {}
        grp_color_m  = {}
        grp_statuses = {}
        for status, n_total in counts_total.items():
            grp_label, grp_color = GROUP_MAP.get(status, (status, FG2))
            grp_total[grp_label]    = grp_total.get(grp_label, 0) + n_total
            grp_sel[grp_label]      = grp_sel.get(grp_label, 0) + counts_selected.get(status, 0)
            grp_color_m[grp_label]  = grp_color
            grp_statuses.setdefault(grp_label, set()).add(status)

        first_status = True
        for grp in ['Perfect', 'Playable', 'Ingame', 'Intro/Menu', 'Unplayable', 'Unknown', 'Not found']:
            if grp not in grp_total:
                continue
            n_sel_grp   = grp_sel.get(grp, 0)
            n_total_grp = grp_total[grp]
            color        = grp_color_m[grp]
            statuses     = grp_statuses[grp]
            label_val    = f'{n_sel_grp} / {n_total_grp}'
            if first_status:
                # Small visual gap before status cards
                tk.Frame(self.compat_card_frame, bg=BG, width=12).pack(side='left')
                first_status = False
            self._make_card(self.compat_card_frame, grp, label_val, color,
                            command=lambda s=frozenset(statuses): self._compat_filter(s),
                            dbl_command=lambda s=frozenset(statuses): self._compat_toggle_group(s))

    def _compat_toggle_group(self, statuses: frozenset):
        """Select or deselect all ROMs in a compatibility status group."""
        if not self._compat_all_iids:
            return
        # Find all iids in this group
        group_iids = [iid for iid in self._compat_all_iids
                      if self.compat_tree.item(iid, 'tags') and
                      self.compat_tree.item(iid, 'tags')[0] in statuses]
        if not group_iids:
            return
        # Check if any are currently selected (●)
        any_selected = any(
            self.compat_tree.item(iid, 'values')[0] == '●'
            for iid in group_iids)
        # Toggle: if any selected → deselect all; if none selected → select all
        for iid in group_iids:
            vals = list(self.compat_tree.item(iid, 'values'))
            fname = vals[1]
            tags  = self.compat_tree.item(iid, 'tags')
            if any_selected:
                vals[0] = '○'
                for title, data in self.rom_dict.items():
                    if data.get('selected') and data['selected'].get('filename') == fname:
                        data['selected'] = None
                        break
            else:
                vals[0] = '●'
                for title, data in self.rom_dict.items():
                    if data.get('selected') is None:
                        for inst in data.get('instances', []):
                            if inst.get('filename') == fname:
                                data['selected'] = inst
                                break
                    if data.get('selected') and data['selected'].get('filename') == fname:
                        break
            self.compat_tree.item(iid, values=vals, tags=tags)
        self._populate_compat_cards()
        self._populate_cards()

    def _compat_apply_threshold(self):
        """Deselect titles below the chosen compatibility threshold."""
        if not self.rom_dict:
            return
        status_map = getattr(self, '_compat_status_map', {})
        if not status_map:
            self.lbl_compat_status.config(
                text='Fetch compatibility first before applying threshold.', fg=RED)
            return
        RANK = {'Perfect': 0, 'Playable': 1, 'Good': 1, 'Ingame +': 2,
                'Runs': 2, 'Gameplay': 2, 'Ingame -': 3, 'Ingame': 3,
                'Intro': 4, 'Starts': 4, 'Menu': 4, 'Loads': 4,
                'Bootable': 5, 'Loadable': 5, 'Nothing': 6,
                'Unplayable': 6, "Won't Fix": 6, 'Not found': 99}
        threshold = self.compat_threshold.get()
        threshold_rank = RANK.get(threshold, 99)
        deselected = 0
        # Operate on rom_dict directly using stored compat status — works even if
        # the compat tree has been reset (e.g. by a Selection tab interaction)
        for key, data in self.rom_dict.items():
            if not data.get('selected'):
                continue
            status = status_map.get(key, 'Not found')
            if RANK.get(status, 99) > threshold_rank:
                data['selected'] = None
                deselected += 1
        # Sync the compat tree dots to reflect new selection state
        all_iids = getattr(self, '_compat_all_iids', None) or list(self.compat_tree.get_children())
        for iid in all_iids:
            try:
                vals = list(self.compat_tree.item(iid, 'values'))
                if not vals:
                    continue
                fname = vals[1]
                data  = self.rom_dict.get(fname)
                is_sel = bool(data and data.get('selected'))
                vals[0] = '●' if is_sel else '○'
                self.compat_tree.item(iid, values=vals)
            except Exception:
                continue
        if deselected:
            self.lbl_compat_status.config(
                text=f'{deselected} titles deselected below "{threshold}"', fg=YELLOW)
        else:
            self.lbl_compat_status.config(
                text=f'No titles below "{threshold}" to deselect.', fg=FG2)
        sel_bytes = sum(parse_size_bytes(d['selected'].get('size', '0'))
                        for d in self.rom_dict.values() if d.get('selected'))
        n_sel = sum(1 for d in self.rom_dict.values() if d.get('selected'))
        self.lbl_compat_summary.config(text=f'{n_sel} files  —  {format_size(sel_bytes)} total')
        self._populate_cards()
        self._populate_compat_cards()

    def _dl_tick(self):
        if not self.dl_running and not self.dl_slots:
            self._debug(f"_dl_tick: early return, dl_running={self.dl_running}, slots={len(self.dl_slots)}")
            return
        try:
            self._dl_tick_body()
        except Exception:
            import traceback
            self._debug(f"_dl_tick crash: {traceback.format_exc().splitlines()[-1]}")
        self.root.after(500, self._dl_tick)

    def _dl_tick_body(self):

        now = time.time()
        with self.dl_lock:
            slots       = dict(self.dl_slots)
            completed   = self.dl_completed_files
            skipped     = self.dl_skipped_files
            failed      = self.dl_failed_files
            comp_bytes  = self.dl_completed_bytes
            in_progress = sum(dl for _, dl, _ in slots.values())
            window      = list(self.dl_window)
            failed_list = list(self.dl_failed_list)
            total_files = self.dl_total_files
            total_bytes = self.dl_total_bytes

        total_done = comp_bytes + in_progress
        elapsed    = now - self.dl_start_time if self.dl_start_time else 0

        if len(window) >= 2:
            dt    = window[-1][0] - window[0][0]
            db    = window[-1][1] - window[0][1]
            speed = db / dt if dt > 0 else 0
        else:
            speed = 0

        remaining = max(total_bytes - total_done, 0)
        eta = remaining / speed if speed > 0 else float('inf')
        pct = total_done / total_bytes * 100 if total_bytes else 0

        self.dl_overall_bar['value'] = pct
        self.dl_lbl_pct.config(text=f"{pct:.1f}%")
        self.dl_lbl_size.config(
            text=f"{format_size(total_done)} / {format_size(total_bytes)}")
        self.dl_lbl_speed.config(
            text=f"{format_size(int(speed))}/s" if not self.dl_paused else 'paused')
        self.dl_lbl_eta.config(text=f"ETA: {format_eta(eta)}")
        self.dl_lbl_elapsed.config(text=format_duration(elapsed))
        self.dl_lbl_files.config(
            text=f"Files: {completed} done / {skipped} skipped / "
                 f"{failed} failed / {total_files} total"
        )

        active_count = len(slots)
        self.lbl_active_threads.config(text=f'({active_count} active / {self.parallel.get()} parallel)')

        max_par = self.parallel.get()
        for slot in range(20):
            widgets = self.dl_slot_widgets[slot]
            if slot in slots:
                fname, dl, total = slots[slot]
                short    = fname[:65] + '...' if len(fname) > 66 else fname
                pct_slot = dl / total * 100 if total else 0
                win = self._slot_window[slot]
                win.append((now, dl))
                cutoff = now - 10
                self._slot_window[slot] = [(t, b) for t, b in win if t >= cutoff]
                win = self._slot_window[slot]
                if len(win) >= 2 and not self.dl_paused:
                    dt       = win[-1][0] - win[0][0]
                    db       = win[-1][1] - win[0][1]
                    slot_spd = db / dt if dt > 0 else 0
                    rate_str = f"{format_size(int(slot_spd))}/s"
                else:
                    slot_spd = 0
                    rate_str = 'paused' if self.dl_paused else '--'
                widgets['lbl_name'].config(text=short)
                slot_eta = format_eta((total - dl) / slot_spd) if slot_spd > 0 else '--:--'
                widgets['lbl_stat'].config(
                    text=f"{format_size(dl)} / {format_size(total)}  {pct_slot:.0f}%  ETA:{slot_eta}")
                widgets['lbl_rate'].config(text=rate_str)
                widgets['bar']['value'] = pct_slot
            else:
                widgets['lbl_name'].config(text='idle')
                widgets['lbl_stat'].config(text='')
                widgets['lbl_rate'].config(text='')
                widgets['bar']['value'] = 0
                self._slot_window[slot] = []

        cur = self.dl_failed_box.size()
        if len(failed_list) > cur:
            for msg in failed_list[cur:]:
                self.dl_failed_box.insert('end', msg)

    def _dl_done(self):
        with self.dl_lock:
            completed = self.dl_completed_files
            skipped   = self.dl_skipped_files
            failed    = self.dl_failed_files

        self.dl_overall_bar['value'] = 100
        self.dl_lbl_pct.config(text='100%')
        summary = f'✓ All done — {completed} downloaded, {skipped} skipped'
        if failed:
            summary += f', {failed} failed'
        self.dl_lbl_verify.config(text=summary, fg=GREEN if not failed else YELLOW)
        self.btn_start_dl.config(state='normal', text='Start')
        messagebox.showinfo(
            'Download Complete',
            f"Downloaded: {completed}\nSkipped:    {skipped}\nFailed:     {failed}"
        )

    def _on_close(self):
        if self.dl_running:
            if not messagebox.askokcancel('Quit', 'Downloads in progress. Quit anyway?'):
                return
        self.dl_running = False
        self.dl_pause_event.set()
        # Cancel all active download slots so their connections close
        with self.dl_lock:
            callbacks = list(self.dl_slot_stuck_callbacks.values())
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass
        # Kill any running aria2c processes
        for proc in list(getattr(self, '_aria2c_procs', [])):
            try: proc.kill()
            except: pass
        self._save_settings()
        self.root.destroy()
        os._exit(0)

    def run(self):
        self.root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    try:
        app = App()
        app.run()
    except Exception as e:
        import traceback
        import tkinter as _tk
        import tkinter.messagebox as _mb
        _r = _tk.Tk(); _r.withdraw()
        _mb.showerror('Startup Error', traceback.format_exc())
        _r.destroy()


