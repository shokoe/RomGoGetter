# RomGoGetter v0.13
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
EXCLUDE_ATTRIBUTES  = {'Demo', 'Kiosk', 'Beta', 'Alpha', 'Proto', 'Prototype', 'Sample', 'Update'}
EXCLUDE_TITLE_WORDS = {'Magazine', 'Demo Disk', 'Demo Disc', 'Bonus Disk', 'Bonus Disc',
                       'Covermount', 'OXM', 'Tips', 'Tricks'}
CHUNK_SIZE    = 1024 * 1024
MAX_PARALLEL  = 3
MAX_RETRIES   = 3
STUCK_TIMEOUT = 60

APP_NAME      = 'RomGoGetter'
APP_VER       = 'v0.13'
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
FONT    = ('Consolas', 10)
FONT_SM = ('Consolas', 9)
FONT_LG = ('Consolas', 12, 'bold')
FONT_XL = ('Consolas', 14, 'bold')


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


def is_excluded(instance: dict) -> bool:
    for attr in instance['attributes']:
        # Match exact or prefixed: 'Demo', 'Demo 1', 'Kiosk Demo', etc.
        for excl in EXCLUDE_ATTRIBUTES:
            if attr == excl or attr.startswith(excl + ' ') or attr.startswith(excl + ','):
                return True
    title = instance.get('filename', '')
    return any(w.lower() in title.lower() for w in EXCLUDE_TITLE_WORDS)


def rev_key(instance: dict) -> tuple:
    """Sort key: Rev > native English country > language count.
    Higher is better. Numeric revs sort numerically (11 > 7), alpha lexicographically.
    """
    m          = REV_PATTERN.search(instance.get('filename', ''))
    native_en  = 1 if instance['countries'] & ENGLISH_COUNTRIES else 0
    lang_count = len(instance['languages'])
    if m:
        rev_str = m.group(1).strip()
        try:
            return (1, int(rev_str), 0, native_en, lang_count)
        except ValueError:
            return (1, 0, rev_str, native_en, lang_count)
    return (0, 0, '', native_en, lang_count)


def select_best(instances: list) -> dict | None:
    english = [i for i in instances if 'En' in i['languages'] and not is_excluded(i)]
    if english:
        best = max(english, key=rev_key)
    else:
        western = [i for i in instances if i['countries'] & WESTERN and not is_excluded(i)]
        if western:
            best = max(western, key=rev_key)
        else:
            # No western version — fall back to best available (e.g. Japan-only)
            non_excl = [i for i in instances if not is_excluded(i)]
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
        href_match = re.search(r'<a\s+href="([^"]+)"', first_cell, re.IGNORECASE)
        if href_match:
            fname = html.unescape(unquote(href_match.group(1)))
            if not fname.startswith('/'):
                results.append((fname, size_str))
        else:
            text = html.unescape(re.sub(r'<[^>]+>', '', first_cell).strip())
            if text and '.' in text and text != 'Name':
                results.append((text, size_str))
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
    ul_start = re.search(r'<ul\s[^>]*class="file-list"[^>]*>', content, re.IGNORECASE)
    if not ul_start:
        return [], page_title
    file_list_block = content[ul_start.end():]
    # Cut at the matching </ul> — first one after the opening tag
    ul_end = re.search(r'</ul>', file_list_block, re.IGNORECASE)
    if ul_end:
        file_list_block = file_list_block[:ul_end.start()]

    results = []
    for li in re.findall(r'<li[^>]*class="file-item"[^>]*>(.*?)</li>',
                         file_list_block, re.DOTALL | re.IGNORECASE):
        # href may appear after other attributes (class, download, etc.)
        href_match = re.search(r'\bhref="([^"]+)"', li, re.IGNORECASE)
        size_match = re.search(r'<span\s+class="file-size">(.*?)</span>', li, re.IGNORECASE)
        if not href_match:
            continue
        href = href_match.group(1).split('#')[0]

        # Wayback rewrites hrefs to /web/TIMESTAMP/https://lolroms.com/...
        # Extract the original lolroms.com path from it
        if wayback and 'lolroms.com' in href:
            lolroms_href = href[href.index('lolroms.com') + len('lolroms.com'):]
        else:
            lolroms_href = href  # already a clean /Category/file.7z path

        # Decode percent-encoding but spaces may also appear literally
        fname      = html.unescape(unquote(lolroms_href.split('/')[-1]))
        # Normalise to a clean percent-encoded URL: unquote first to avoid double-encoding
        direct_url = f"https://lolroms.com{quote(unquote(lolroms_href), safe='/')}"
        size_str   = html.unescape(size_match.group(1)).strip() if size_match else ''
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


# ── Main App ──────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.settings = load_settings()

        self.root = tk.Tk()
        self.root.title(f'{APP_NAME}  {APP_VER}')
        self.root.configure(bg=BG)
        self.root.geometry(self.settings.get('geometry', '1150x800'))
        self.root.resizable(True, True)

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
        self.local_source= tk.StringVar(value=self.settings.get('local_source', ''))
        self.parallel    = tk.IntVar(   value=self.settings.get('parallel',     MAX_PARALLEL))
        self.retries     = tk.IntVar(   value=self.settings.get('retries',      MAX_RETRIES))
        self.stuck       = tk.IntVar(   value=self.settings.get('stuck',        STUCK_TIMEOUT))
        self.aria2_split = tk.IntVar(   value=self.settings.get('aria2_split',  5))
        self.aria2_speed = tk.StringVar(value=self.settings.get('aria2_speed',  '0'))
        self.verify_mode = tk.StringVar(value=self.settings.get('verify_mode',  'Hash'))
        self.mode        = tk.StringVar(value=self.settings.get('mode', '1G1R English only'))
        self.ra_top_n    = tk.IntVar(   value=self.settings.get('ra_top_n',   100))
        self.ra_system   = tk.StringVar(value=self.settings.get('ra_system',  ''))
        self.igdb_platform_id  = tk.IntVar(   value=self.settings.get('igdb_platform_id', 0))
        self.igdb_platform_name= tk.StringVar(value=self.settings.get('igdb_platform_name', ''))
        self.igdb_top_n        = tk.IntVar(   value=self.settings.get('igdb_top_n', 100))
        self._igdb_token       = None   # cached OAuth token
        self._igdb_platforms   = []     # [(id, name), ...] populated on first fetch
        self.dat_path    = ''
        self.url_groups: dict     = load_groups()
        self.dat_groups: dict     = load_dat_groups()
        self._dat_group_cache: dict = {}  # name -> merged parsed DAT dict

        self.nb = ttk.Notebook(self.root)

        self.tab_setup    = tk.Frame(self.nb, bg=BG)
        self.tab_analysis = tk.Frame(self.nb, bg=BG)
        self.tab_download = tk.Frame(self.nb, bg=BG)

        self.nb.add(self.tab_setup,    text='  Setup  ')
        self.nb.add(self.tab_analysis, text='  Analysis  ')
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

        # Notebook fills the rest
        self.nb.pack(fill='both', expand=True, padx=8, pady=(8, 0))

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
        self._nb_tab_download = self.tab_download
        self.tab_setup    = _make_scrollable(self.tab_setup)
        # Analysis tab must NOT be wrapped in a scrollable canvas — the treeview
        # needs fill/expand to work, which canvas inner frames cannot provide.
        # The treeview has its own scrollbar already.
        self.tab_download = _make_scrollable(self.tab_download)

        self._build_setup()
        self._build_analysis()
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
            'access':       self.access.get(),
            'secret':       self.secret.get(),
            'dest_dir':     self.dest_dir.get(),
            'local_source': self.local_source.get(),
            'parallel':     self.parallel.get(),
            'retries':      self.retries.get(),
            'stuck':        self.stuck.get(),
            'aria2_split':  self.aria2_split.get(),
            'aria2_speed':  self.aria2_speed.get(),
            'mode':         self.mode.get(),
            'verify_mode':  self.verify_mode.get(),
            'urls':         self.url_text.get('1.0', 'end').strip(),
            'url_group':    getattr(self, 'group_var', tk.StringVar()).get(),
            'ra_top_n':     self.ra_top_n.get(),
            'ra_system':    self.ra_system.get(),
            'igdb_platform_id':   self.igdb_platform_id.get(),
            'igdb_platform_name': self.igdb_platform_name.get(),
            'igdb_top_n':         self.igdb_top_n.get(),
            'dat_group':      getattr(self, 'dat_group_var', tk.StringVar()).get(),
            'dat_group_urls': self.dat_group_text.get('1.0', 'end').strip()
                              if hasattr(self, 'dat_group_text') else '',
        })

    # ── Setup tab ─────────────────────────────────────────────────────────────

    def _build_setup(self):
        f   = self.tab_setup
        PAD = 16

        title_row = tk.Frame(f, bg=BG)
        title_row.pack(pady=(PAD, 4))
        tk.Label(title_row, text=APP_NAME, bg=BG, fg=ACC,
                 font=('Consolas', 20, 'bold')).pack(side='left')
        tk.Label(title_row, text='  by Shoko 2026', bg=BG, fg=GREEN,
                 font=FONT_SM).pack(side='left', anchor='s', pady=(0, 4))
        tk.Label(f, text=f'1G1R ROM downloader for archive.org  |  {APP_VER}',
                 bg=BG, fg=FG2, font=FONT_SM).pack(pady=(0, PAD))

        # ── Source URLs ───────────────────────────────────────────────────────
        url_frame = tk.LabelFrame(f, text=' Source URLs ', bg=BG, fg=FG,
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

        src_frame = tk.LabelFrame(dirs_row, text=' Additional Local Source ', bg=BG, fg=FG,
                                  font=FONT, padx=PAD, pady=PAD)
        src_frame.pack(side='left', fill='x', expand=True, padx=(4, 0))
        src_row = tk.Frame(src_frame, bg=BG)
        src_row.pack(fill='x')
        tk.Entry(src_row, textvariable=self.local_source, bg=BG2, fg=FG, font=FONT,
                 insertbackground=FG, relief='flat',
                 borderwidth=4).pack(side='left', fill='x', expand=True, padx=(0, 8))
        tk.Button(src_row, text='Browse', bg=BG3, fg=FG, font=FONT,
                  relief='flat', padx=8,
                  command=self._browse_local_source).pack(side='left')

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
                  font=('Consolas', 48, 'bold'),
                  relief='flat', padx=40, pady=20, cursor='hand2')
        self.btn_donate.pack(pady=(8, 0))
        self.lbl_torrent_warning = tk.Label(f,
                 text='⚠ This app does not seed torrents — please use a proper torrent client to give back to the community.',
                 bg=BG, fg=RED, font=('Consolas', 24, 'bold'), wraplength=700)
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

        # Show/hide RA Top panel
        if hasattr(self, 'ra_frame'):
            if mode == 'RA Top':
                self.ra_frame.pack(fill='x', pady=(0, 4), before=self._legend_row)
            else:
                self.ra_frame.pack_forget()

        # Show/hide IGDB Top panel — auto-load platforms on first show
        if hasattr(self, 'igdb_frame'):
            if mode == 'IGDB Top':
                self.igdb_frame.pack(fill='x', pady=(0, 4), before=self._legend_row)
                if not self._igdb_platforms:
                    self._fetch_igdb_platforms()
            else:
                self.igdb_frame.pack_forget()

        if not self.raw_file_entries:
            return

        if mode in ('RA Top', 'IGDB Top'):
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
                        req = urllib.request.Request(url, headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
                            'Accept': 'text/plain, application/xml, */*',
                        })
                        with urllib.request.urlopen(req, timeout=20) as r:
                            xml_data = r.read().decode('utf-8', errors='replace')
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
            key = os.path.splitext(entry[0])[0].lower()
            fetched_by_key[key] = entry

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
        display = self.ra_system_var.get()
        if not display:
            messagebox.showerror('Error', 'Please select a console.')
            return

        self.btn_fetch_ra.config(state='disabled')
        self.lbl_ra_status.config(text='Fetching RA data...', fg=YELLOW)
        self.root.update()

        # Snapshot IntVar on main thread before handing off to worker
        _top_n_snapshot = max(1, self.ra_top_n.get())

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
                req = urllib.request.Request(CSV_URL, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'
                })
                with urllib.request.urlopen(req, timeout=30) as r:
                    csv_data = r.read().decode('utf-8', errors='replace')
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
                    self.root.after(0, lambda: self.lbl_ra_status.config(
                        text=f'No data for {display}', fg=RED))
                    self.root.after(0, lambda: self.btn_fetch_ra.config(state='normal'))
                    return

                # Remove rows with [...] or ~Hack~/~Homebrew~ etc in title
                matched_rows = [(p, t) for p, t in matched_rows
                                if '[' not in t and not t.startswith('~')]
                matched_rows.sort(key=lambda x: x[0], reverse=True)
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
                from difflib import SequenceMatcher

                def _fuzzy(a, b):
                    return SequenceMatcher(None, a, b).ratio()

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

                # Pre-compute best match for each source entry
                entry_matches = []
                for entry in english_entries:
                    fname = entry[0]
                    base  = os.path.splitext(fname)[0]
                    bare  = re.sub(r'\s*\([^)]*\)', '', base).strip()
                    bare  = re.sub(r'\s*(Disc|Disk)\s*\d+', '', bare, flags=re.IGNORECASE).strip()
                    norm  = _normalize(bare)
                    best_score, best_title = 0, None
                    for ra_norm, ra_title in ra_norm_list:
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
                still_unmatched = [t for t in top100 if not ra_groups[t]]
                if still_unmatched and nonenglish_entries:
                    nonenglish_matches = []
                    for entry in nonenglish_entries:
                        fname = entry[0]
                        base  = os.path.splitext(fname)[0]
                        bare  = re.sub(r'\s*\([^)]*\)', '', base).strip()
                        bare  = re.sub(r'\s*(Disc|Disk)\s*\d+', '', bare, flags=re.IGNORECASE).strip()
                        norm  = _normalize(bare)
                        best_score, best_title = 0, None
                        for ra_norm, ra_title in ra_norm_list:
                            if ra_title not in still_unmatched:
                                continue
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
                    for inst in variant_groups.get(best_key, [best]):
                        selected_fnames.add(inst['filename'])

                self._debug(f"RA 1G1R: {len(selected_fnames)} files from {len([t for t,e in ra_groups.items() if e])} titles selected")

                # Get All files result as base structure, then select only RA winners
                result, summary = self._apply_filter(self.raw_file_entries, 'All files')
                for title, data in result.items():
                    if data['selected']:
                        fname = data['selected']['filename']
                        if fname not in selected_fnames:
                            data['selected'] = None

                matched_titles = len([t for t, e in ra_groups.items() if e])
                self.rom_dict = result
                self.summary  = summary
                self.dat_mode = False
                self.root.after(0, self._analysis_done)
                self.root.after(0, lambda: self.lbl_ra_status.config(
                    text=f'Top {top_n} — {matched_titles} titles ({len(selected_fnames)} ROMs) from {len(matched_rows)} {console_name} games',
                    fg=GREEN))
                self.root.after(0, lambda: self.btn_fetch_ra.config(state='normal'))

            except Exception:
                import traceback
                tb = traceback.format_exc()
                self._debug(f"RA fetch error:\n{tb}")
                self.root.after(0, lambda: self.lbl_ra_status.config(
                    text='Fetch failed — see debug log', fg=RED))
                self.root.after(0, lambda: self.btn_fetch_ra.config(state='normal'))

        threading.Thread(target=_do, daemon=True).start()
        if not self.raw_file_entries:
            messagebox.showerror('Error', 'Run GoGet! first to fetch the file list.')
            return
        display = self.ra_system_var.get()

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
                self.root.after(0, lambda: self.lbl_igdb_status.config(
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
                    self.igdb_platform_combo['values'] = names
                    # Restore saved selection if valid
                    saved = self.igdb_platform_name.get()
                    if saved in names:
                        self.igdb_platform_combo.set(saved)
                    elif names:
                        self.igdb_platform_combo.set(names[0])
                        self._on_igdb_platform_select()
                    self.lbl_igdb_status.config(
                        text=f'{len(platforms)} platforms loaded', fg=GREEN)
                self.root.after(0, _update)
            except Exception:
                import traceback
                self._debug(f"IGDB platform fetch error:\n{traceback.format_exc()}")
                self.root.after(0, lambda: self.lbl_igdb_status.config(
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

        self.btn_fetch_igdb.config(state='disabled')
        self.lbl_igdb_status.config(text='Fetching IGDB data...', fg=YELLOW)
        self.root.update()

        _top_n = max(1, self.igdb_top_n.get())

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
                while len(titles) < _top_n:
                    self.root.after(0, lambda t=len(titles):
                        self.lbl_igdb_status.config(
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
                    for g in batch:
                        titles.append(g['name'])
                    if len(batch) < per_page:
                        break
                    offset += per_page

                titles = titles[:_top_n]
                if not titles:
                    self.root.after(0, lambda: self.lbl_igdb_status.config(
                        text='No titles found for this platform', fg=RED))
                    self.root.after(0, lambda: self.btn_fetch_igdb.config(state='normal'))
                    return
                self._debug(f"IGDB top {_top_n}: #1={titles[0]!r} #{len(titles)}={titles[-1]!r}")

                igdb_norm = [(_normalize(t), t) for t in titles]

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

                def _match_entries(entries):
                    scored = []
                    for entry in entries:
                        base = os.path.splitext(entry[0])[0]
                        bare = re.sub(r'\s*\([^)]*\)', '', base).strip()
                        bare = re.sub(r'\s*(Disc|Disk)\s*\d+', '', bare,
                                      flags=re.IGNORECASE).strip()
                        norm = _normalize(bare)
                        best_score, best_title = 0, None
                        for gn, gt in igdb_norm:
                            s = _fuzzy(norm, gn)
                            if s > best_score:
                                best_score, best_title = s, gt
                        scored.append((best_score, best_title, entry))
                    return scored

                matched_titles = set()
                for threshold in [1.0, 0.90, 0.85, 0.80, 0.75, 0.70]:
                    for score, title, entry in _match_entries(english_entries):
                        if title and score >= threshold and title not in matched_titles:
                            igdb_groups[title].append(entry)
                    for t in titles:
                        if igdb_groups[t]:
                            matched_titles.add(t)
                    self._debug(f"IGDB threshold {threshold:.2f}: {len(matched_titles)} matched")

                still_unmatched = [t for t in titles if not igdb_groups[t]]
                if still_unmatched and nonenglish_entries:
                    ne_only = [t for t in still_unmatched]
                    for threshold in [1.0, 0.90, 0.85, 0.80, 0.75, 0.70]:
                        for score, title, entry in _match_entries(nonenglish_entries):
                            if title and title in ne_only and score >= threshold and not igdb_groups[title]:
                                igdb_groups[title].append(entry)

                unmatched = [t for t in titles if not igdb_groups[t]]
                self._debug(f"IGDB unmatched ({len(unmatched)}): {sorted(unmatched)[:10]}")

                selected_fnames = set()
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
                        key = re.sub(r'\s*\(Disc\s*\d+[^)]*\)', '',
                                     os.path.splitext(entry[0])[0],
                                     flags=re.IGNORECASE).strip()
                        variant_groups.setdefault(key, []).append(inst)
                    representatives = []
                    for key, insts in variant_groups.items():
                        rep = next((i for i in insts
                                    if re.search(r'Disc\s*1', i['filename'], re.IGNORECASE)),
                                   insts[0])
                        rep['_variant_key'] = key
                        representatives.append(rep)
                    filtered = [i for i in representatives if not is_excluded(i)]
                    if not filtered:
                        filtered = representatives
                    best = select_best(filtered)
                    if not best:
                        continue
                    best_key = best.get('_variant_key') or re.sub(
                        r'\s*\(Disc\s*\d+[^)]*\)', '',
                        os.path.splitext(best['filename'])[0],
                        flags=re.IGNORECASE).strip()
                    for inst in variant_groups.get(best_key, [best]):
                        selected_fnames.add(inst['filename'])

                self._debug(f"IGDB 1G1R: {len(selected_fnames)} files selected")

                result, summary = self._apply_filter(self.raw_file_entries, 'All files')
                for title, data in result.items():
                    if data['selected']:
                        if data['selected']['filename'] not in selected_fnames:
                            data['selected'] = None
                self.rom_dict = result
                self.summary  = summary
                self.dat_mode = False
                self.root.after(0, self._analysis_done)
                self.root.after(0, lambda: self.lbl_igdb_status.config(
                    text=f'{len(selected_fnames)} ROMs from top {len(titles)} titles',
                    fg=GREEN))
                self.root.after(0, lambda: self.btn_fetch_igdb.config(state='normal'))

            except Exception:
                import traceback
                tb = traceback.format_exc()
                self._debug(f"IGDB fetch error:\n{tb}")
                self._igdb_token = None  # reset token in case it expired
                self.root.after(0, lambda: self.lbl_igdb_status.config(
                    text='Fetch failed — see debug log', fg=RED))
                self.root.after(0, lambda: self.btn_fetch_igdb.config(state='normal'))

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
        use_1g1r     = mode in ('1G1R', '1G1R English only')
        english_only = mode == '1G1R English only'

        rom_dict = defaultdict(list)
        for entry in sorted(file_entries, key=lambda x: x[0]):
            filename   = entry[0]
            size_str   = entry[1]
            direct_url = entry[2] if len(entry) > 2 else None
            parsed = parse_rom_filename(filename)
            group_key = normalize_title(parsed['title'])
            rom_dict[group_key].append({
                'filename':   filename,
                'size':       size_str,
                'direct_url': direct_url,
                'countries':  parsed['countries'],
                'languages':  parsed['languages'],
                'attributes': parsed['attributes'],
            })

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

        for title, instances in rom_dict.items():
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
                        elif not sel_inst['countries'] & ENGLISH_COUNTRIES:
                            selected = None
                            is_translated = True
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
                result[title] = {
                    'selected':    sel_entry,
                    'non_english': non_english,
                    'translated':  is_translated,
                    'instances':   instances,
                }
            else:
                for inst in instances:
                    if not is_excluded(inst):
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
            # Build map of selected filename → (languages, countries) for quick lookup
            sel_langs = {}
            for title, data in result.items():
                if data['selected']:
                    inst = next((i for i in data['instances']
                                 if i['filename'] == data['selected']['filename']), None)
                    if inst:
                        sel_langs[title] = (inst['languages'], inst['countries'])

            for title, data in result.items():
                if not data['selected']:
                    continue
                inst = next((i for i in data['instances']
                             if i['filename'] == data['selected']['filename']), None)
                if not inst:
                    continue
                # Check if this title starts with a non-English article
                base_title = title.split('(')[0].strip()
                if not has_non_english_article(base_title):
                    continue
                my_langs = inst['languages'] | inst['countries']
                # Look for another selected title whose languages are a superset
                for other_title, (other_langs, other_countries) in sel_langs.items():
                    if other_title == title:
                        continue
                    other_all = other_langs | other_countries
                    if my_langs <= other_all:
                        # Covered — deselect this non-English titled entry
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
        return result, summary

    def _refresh_analysis_table(self):
        self._populate_analysis()

    def _update_donate(self):
        urls = self.url_text.get('1.0', 'end').strip().splitlines()
        first = next((u.strip() for u in urls if u.strip()), '')
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
            text = 'Pay Respects to Myrient ❤️'
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
        # ── URL fetch — always, regardless of mode ────────────────────────────
        urls = [u.strip() for u in self.url_text.get('1.0', 'end').splitlines() if u.strip()]
        if not urls:
            messagebox.showerror('Error', 'Please enter at least one URL.')
            return
        if not self.dest_dir.get():
            messagebox.showerror('Error', 'Please select a destination folder.')
            return
        self._fetch_cancel.clear()
        self._save_settings()
        self.dat_mode = False
        self.setup_status.config(text='Fetching...', fg=YELLOW)
        self.lbl_analysis_title.config(text='Fetching…', fg=YELLOW)
        self.btn_analyse.config(text='Reset', bg=RED, fg=FG)
        self.root.update()
        mode = self.mode.get()
        # DAT and None modes fetch as All files, then apply their filter after
        effective_mode = 'All files' if mode in ('None', 'DAT file', 'RA Top', 'IGDB Top') else mode

        def run():
            try:
                file_entries = []
                page_title   = None
                access       = self.access.get() or None
                secret       = self.secret.get() or None
                total_urls   = len(urls)

                # ── Fetch ROM listings ────────────────────────────────────────
                for i, url in enumerate(urls, 1):
                    if self._fetch_cancel.is_set():
                        return
                    self.root.after(0, lambda i=i, u=url, n=total_urls:
                        self.setup_status.config(
                            text=f'Fetching {i}/{n}: {u}', fg=YELLOW))
                    self._debug(f"Fetching ({i}/{total_urls}): {url}")
                    entries, title = None, None
                    for attempt in range(1, 4):
                        try:
                            if is_lolroms_url(url):
                                entries, title = fetch_lolroms_filenames(url)
                            elif is_minerva_url(url):
                                entries, title = fetch_minerva_filenames(url)
                            else:
                                entries, title = fetch_archive_filenames(url, access, secret)
                            self._debug(f"OK — {len(entries)} files, title={title!r}")
                            break
                        except Exception as ex:
                            self._debug(f"Attempt {attempt}/3 FAILED: {type(ex).__name__}: {ex}")
                            if attempt == 3:
                                self.root.after(0, lambda u=url, i=i, n=total_urls:
                                    self.setup_status.config(
                                        text=f'FAILED {i}/{n}: {u}', fg=RED))
                                return
                            time.sleep(2)
                    file_entries.extend(entries)
                    if title and page_title is None:
                        page_title = title
                    self.root.after(0, lambda i=i, n=total_urls, c=len(file_entries):
                        self.setup_status.config(
                            text=f'Done {i}/{n} -- {c} files so far', fg=YELLOW))
                    self.root.after(0, lambda i=i, n=total_urls, c=len(file_entries):
                        self.lbl_analysis_title.config(
                            text=f'Fetching {i}/{n}  —  {c:,} files…', fg=YELLOW))


                # Store raw entries for live re-filtering on mode change
                self.raw_file_entries = file_entries
                self.page_title       = page_title
                self.dat_mode         = False

                if mode == 'DAT' and self.dat_path:
                    self.root.after(0, self._apply_dat_mode)
                elif mode in ('None', 'RA Top', 'IGDB Top'):
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
        self.setup_status.config(text='Analysis complete!', fg=GREEN)
        mode = self.mode.get()
        total = self.summary.get('total_files', 0)
        self.lbl_analysis_title.config(text=f'Analysis Results  ({total:,} files)', fg=FG)
        if self.dat_mode:
            self.lbl_list_title.config(text='DAT selection:')
        elif mode == '1G1R English only':
            self.lbl_list_title.config(text='Selected titles (1G1R — English only):')
        elif mode == '1G1R':
            self.lbl_list_title.config(text='Selected titles (1G1R):')
        elif mode == 'None':
            self.lbl_list_title.config(text='No files selected:')
        elif mode == 'RA Top':
            n = getattr(self, 'ra_top_n', None)
            n_val = n.get() if n else 100
            self.lbl_list_title.config(text=f'RA Top {n_val} (1G1R):')
        elif mode == 'IGDB Top':
            n_val = getattr(self, 'igdb_top_n', None)
            n_val = n_val.get() if n_val else 100
            plat  = getattr(self, 'igdb_platform_name', tk.StringVar()).get() or 'unknown'
            self.lbl_list_title.config(text=f'IGDB Top {n_val} — {plat} (1G1R):')
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

        self.lbl_analysis_title = tk.Label(f, text='Analysis Results', bg=BG, fg=FG,
                 font=FONT_XL)
        self.lbl_analysis_title.pack(pady=(PAD, 8), anchor='w', padx=PAD)

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
        MODE_OPTIONS = ['1G1R English only', '1G1R', 'All files', 'None', 'DAT', 'RA Top', 'IGDB Top']
        self.mode_combo = ttk.Combobox(
            list_hdr, textvariable=self.mode,
            values=MODE_OPTIONS, state='readonly',
            font=FONT_SM, width=18,
        )
        self.mode_combo.pack(side='right', padx=(4, 0))
        tk.Label(list_hdr, text='Mode:', bg=BG, fg=FG2,
                 font=FONT_SM).pack(side='right')
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

        # ── RA Top N panel ────────────────────────────────────────────────────
        self.ra_frame = tk.LabelFrame(list_frame, text=' RetroAchievements Top N ',
                                      bg=BG, fg=FG2, font=FONT_SM, padx=8, pady=6)
        ra_inner = tk.Frame(self.ra_frame, bg=BG)
        ra_inner.pack(fill='x')
        tk.Label(ra_inner, text='Console:', bg=BG, fg=FG2, font=FONT_SM).pack(side='left')
        if not self.ra_system.get() or self.ra_system.get() not in RA_SYSTEM_DISPLAY:
            self.ra_system.set(RA_SYSTEM_DISPLAY[0])
        self.ra_system_var = self.ra_system  # alias for legacy references
        self.ra_system.trace_add('write', lambda *_: self._save_settings()
                                 if hasattr(self, '_init_done') else None)
        ra_combo = ttk.Combobox(ra_inner, textvariable=self.ra_system,
                                values=RA_SYSTEM_DISPLAY, state='readonly',
                                font=FONT_SM, width=30)
        ra_combo.pack(side='left', padx=(4, 12))
        tk.Label(ra_inner, text='Top', bg=BG, fg=FG2, font=FONT_SM).pack(side='left')
        tk.Spinbox(ra_inner, textvariable=self.ra_top_n,
                   from_=1, to=9999, increment=10, width=5,
                   bg=BG2, fg=FG, font=FONT_SM, relief='flat',
                   buttonbackground=BG3, insertbackground=FG
                   ).pack(side='left', padx=(4, 12))
        self.btn_fetch_ra = tk.Button(ra_inner, text='Fetch & Apply', bg=ACC, fg=FG,
                                      font=FONT_SM, relief='flat', padx=10,
                                      command=self._fetch_ra_top)
        self.btn_fetch_ra.pack(side='left')
        self.lbl_ra_status = tk.Label(ra_inner, text='', bg=BG, fg=YELLOW, font=FONT_SM)
        self.lbl_ra_status.pack(side='left', padx=(10, 0))

        # ── Moby Top panel ───────────────────────────────────────────────────
        self.igdb_frame = tk.LabelFrame(list_frame, text=' IGDB Top N (by rating) ',
                                        bg=BG, fg=FG2, font=FONT_SM, padx=8, pady=6)
        igdb_inner = tk.Frame(self.igdb_frame, bg=BG)
        igdb_inner.pack(fill='x')
        tk.Label(igdb_inner, text='Platform:', bg=BG, fg=FG2,
                 font=FONT_SM).pack(side='left')
        self.igdb_platform_combo = ttk.Combobox(
            igdb_inner, textvariable=self.igdb_platform_name,
            font=FONT_SM, width=28, state='readonly')
        self.igdb_platform_combo.pack(side='left', padx=(4, 8))
        self.igdb_platform_combo.bind('<<ComboboxSelected>>', self._on_igdb_platform_select)
        tk.Button(igdb_inner, text='↺', bg=BG3, fg=FG2, font=FONT_SM,
                  relief='flat', padx=6,
                  command=self._fetch_igdb_platforms).pack(side='left', padx=(0, 8))
        tk.Label(igdb_inner, text='Top', bg=BG, fg=FG2,
                 font=FONT_SM).pack(side='left')
        tk.Spinbox(igdb_inner, textvariable=self.igdb_top_n,
                   from_=1, to=9999, increment=10, width=5,
                   bg=BG2, fg=FG, font=FONT_SM, relief='flat',
                   buttonbackground=BG3, insertbackground=FG
                   ).pack(side='left', padx=(4, 8))
        self.btn_fetch_igdb = tk.Button(igdb_inner, text='Fetch & Apply', bg=ACC, fg=FG,
                                        font=FONT_SM, relief='flat', padx=10,
                                        command=self._fetch_igdb_top)
        self.btn_fetch_igdb.pack(side='left')
        self.lbl_igdb_status = tk.Label(igdb_inner, text='', bg=BG, fg=YELLOW, font=FONT_SM)
        self.lbl_igdb_status.pack(side='left', padx=(10, 0))
        tk.Label(self.igdb_frame,
                 text='Click ↺ to load platform list from IGDB',
                 bg=BG, fg='#555555', font=FONT_SM).pack(anchor='w')

        legend_row = tk.Frame(list_frame, bg=BG)
        self._legend_row = legend_row  # save ref for dat_group_frame positioning
        legend_row.pack(fill='x', pady=(4, 0))
        for symbol, label, color, tag in [
            ('●', 'Selected',              GREEN,  'selected'),
            ('○', 'Unselected',            FG2,    'unselected'),
            ('✗', 'Non-English / Missing', RED,    'nonenglish'),
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
        self.title_list.tag_configure('excluded',    foreground=YELLOW)
        self.title_list.tag_configure('filtered',    foreground='#444444')
        self.title_list.tag_configure('translated',  foreground='#4488ff')

        self.title_list.pack(fill='both', expand=True)
        sb.config(command=self.title_list.yview)
        self._analysis_sort_col = 'filename'
        self._analysis_sort_rev = False
        self.title_list.bind('<Double-Button-1>', self._on_analysis_click)
        self.title_list.bind('<space>', self._on_analysis_click)

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(pady=PAD)
        self.btn_download = tk.Button(btn_row, text='Download', bg=ACC, fg=FG, font=FONT_LG,
                  relief='flat', padx=20, pady=8,
                  command=self._go_to_download)
        self.btn_download.pack(side='left', padx=(0, 8))
        tk.Button(btn_row, text='Export DAT', bg=BG3, fg=FG, font=FONT_LG,
                  relief='flat', padx=20, pady=8,
                  command=self._export_dat).pack(side='left')

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
        self._populate_cards()

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

        self._make_card(self.card_frame, 'Total Titles', str(s['total_titles']),  FG)
        self._make_card(self.card_frame, 'Total Size',   s['total_size'],          FG)
        self._make_card(self.card_frame, 'Selected ROMs', str(sel_count),          GREEN,  command=lambda: self._filter_tag('selected'))
        self._make_card(self.card_frame, 'Selected Size', format_size(sel_bytes),  GREEN,  command=lambda: self._filter_tag('selected'))
        if not self.dat_mode:
            self._make_card(self.card_frame, 'Non-English',      str(s['non_english_titles']), RED,    command=lambda: self._filter_tag('nonenglish'))
            self._make_card(self.card_frame, 'Non-English Size', s['non_english_size'],        RED,    command=lambda: self._filter_tag('nonenglish'))
            self._make_card(self.card_frame, 'Non-Game',         str(s['excluded_files']),     YELLOW, command=lambda: self._filter_tag('excluded'))
            self._make_card(self.card_frame, 'Non-Game Size',    s['excluded_size'],           YELLOW, command=lambda: self._filter_tag('excluded'))
        else:
            self._make_card(self.card_frame, 'Missing',      str(s['excluded_files']), RED, command=lambda: self._filter_tag('nonenglish'))
            self._make_card(self.card_frame, 'Missing Size',  s['excluded_size'],       RED, command=lambda: self._filter_tag('nonenglish'))

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
                    self.title_list.item(iid, tags=('filtered',))
                else:
                    if 'filtered' in current_tags:
                        self.title_list.item(iid, tags=(orig_tag,))
            except tk.TclError:
                pass

    def _retag_row(self, iid, fname):
        """Restore the correct tag for a row from stored original tag."""
        if iid in self._all_tree_items:
            _, orig_tag = self._all_tree_items[iid]
            self.title_list.item(iid, tags=(orig_tag,))

    def _apply_type_filter(self):
        """Unselect all rows that are greyed out by the type filter."""
        rgx = self._get_type_filter_re()
        if not rgx:
            return
        changed = 0
        for iid, (fname, orig_tag) in self._all_tree_items.items():
            if not rgx.search(fname):
                # Find this file in rom_dict and unselect it
                for title, data in self.rom_dict.items():
                    if data.get('selected') and data['selected'].get('filename') == fname:
                        data['selected'] = None
                        # Update stored tag
                        self._all_tree_items[iid] = (fname, 'unselected')
                        changed += 1
                        break
        if changed:
            self._preview_type_filter()
            self._update_selected_cards()

    def _apply_search(self):
        """Show/hide treeview rows based on search text."""
        self._active_tag_filter = None  # clear tag filter on search
        q = self.search_var.get().lower().strip()
        if not q:
            # Restore all rows
            for iid in self._all_tree_items:
                self.title_list.reattach(iid, '', 'end')
            return
        # Detach non-matching, reattach matching
        pos = 0
        for iid in self._all_tree_items:
            fname, _ = self._all_tree_items[iid]
            if q in fname.lower():
                self.title_list.reattach(iid, '', pos)
                pos += 1
            else:
                self.title_list.detach(iid)

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

    def _make_card(self, parent, label: str, value: str, color: str = FG, command=None):
        card = tk.Frame(parent, bg=BG2, padx=8, pady=6,
                        cursor='hand2' if command else '')
        card.pack(side='left', padx=3, pady=4)
        lbl_val = tk.Label(card, text=value, bg=BG2, fg=color,
                           font=('Consolas', 12, 'bold'), width=12)
        lbl_val.pack()
        lbl_name = tk.Label(card, text=label, bg=BG2, fg=FG2,
                            font=FONT_SM, width=12)
        lbl_name.pack()
        if command:
            for w in (card, lbl_val, lbl_name):
                w.bind('<Button-1>', lambda e: command())

    def _populate_analysis(self):
        self._populate_cards()

        # Clear treeview and search index
        for row in self.title_list.get_children():
            self.title_list.delete(row)
        self._all_tree_items = {}  # iid → filename for search

        def _insert(values, tags):
            iid = self.title_list.insert('', 'end', values=values, tags=tags)
            self._all_tree_items[iid] = (values[1], tags[0])  # (filename, original_tag)

        if self.dat_mode:
            self._cycle_pos = {}  # reset cycle on new data

            # Build all rows with sort key = display filename
            rows = []
            for key, data in self.rom_dict.items():
                if data.get('_dat_missing'):
                    rows.append((data['_dat_fname'], ('✗', data['_dat_fname'], data['_dat_size']), ('nonenglish',)))
                elif data['selected']:
                    fname = data['selected']['filename']
                    rows.append((fname, ('●', fname, data['selected']['size']), ('selected',)))
                else:
                    fname = key
                    size = next((e[1] for e in self.raw_file_entries if e[0] == fname), '')
                    rows.append((fname, ('○', fname, size), ('unselected',)))

            for sort_key, values, tags in sorted(rows, key=lambda r: r[0].lower()):
                iid = self.title_list.insert('', 'end', values=values, tags=tags)
                self._all_tree_items[iid] = (values[1], tags[0])
        else:
            for title, data in sorted(self.rom_dict.items()):
                selected_fn = data['selected']['filename'] if data['selected'] else None
                non_english = data.get('non_english', False)
                instances   = data.get('instances', [])

                if not instances:
                    # All-files mode — single entry
                    if data['selected']:
                        _insert(('●', data['selected']['filename'],
                                 data['selected']['size']), ('selected',))
                    continue

                for inst in sorted(instances, key=lambda i: i['filename']):
                    fname  = inst['filename']
                    size   = inst['size']
                    excl   = is_excluded(inst)
                    is_sel = fname == selected_fn
                    is_translated = data.get('translated', False)

                    if is_sel:
                        symbol, tag = '●', 'selected'
                    elif excl:
                        symbol, tag = '⊘', 'excluded'
                    elif non_english:
                        symbol, tag = '✗', 'nonenglish'
                    elif is_translated and not is_sel:
                        symbol, tag = '✗', 'nonenglish'
                    elif not inst['countries'] & ENGLISH_COUNTRIES and 'En' not in inst['languages']:
                        symbol, tag = '○', 'unselected'
                    else:
                        symbol, tag = '○', 'unselected'

                    _insert((symbol, fname, size), (tag,))

        # Re-apply search if active
        if hasattr(self, 'search_var') and self.search_var.get().strip():
            self._apply_search()

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
                        self.complete_slot(slot, os.path.getsize(dst))
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
                    draining   = False
                    target_par = max_par
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
                                            break
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

    def _export_dat(self):
        if not self.rom_dict:
            messagebox.showerror('Error', 'Run analysis first.')
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

            for key, data in sorted(self.rom_dict.items()):
                if not data['selected']:
                    continue
                fname  = data['selected']['filename']
                size_s = data['selected']['size']
                # Normalise size to bytes int for the DAT attribute
                if self.dat_mode:
                    size_b = str(parse_size_bytes_dat(size_s))
                else:
                    size_b = str(parse_size_bytes(size_s))
                title  = os.path.splitext(fname)[0]
                game   = ET.SubElement(root_el, 'game', name=title)
                ET.SubElement(game, 'rom', name=fname, size=size_b)

            tree = ET.ElementTree(root_el)
            ET.indent(tree, space='  ')
            tree.write(path, encoding='utf-8', xml_declaration=True)
            messagebox.showinfo('Export complete',
                                f"Exported {sum(1 for d in self.rom_dict.values() if d['selected'])} "
                                f"entries to:\n{path}")
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

    def complete_slot(self, slot: int, nbytes: int, skipped=False, failed=False):
        with self.dl_lock:
            self.dl_slots.pop(slot, None)
            if skipped:
                self.dl_skipped_files += 1
            elif failed:
                self.dl_failed_files += 1
            else:
                self.dl_completed_files += 1
                self.dl_completed_bytes += nbytes

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

                self.complete_slot(slot, expected_size or downloaded)
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

        urls     = [u.strip() for u in self.url_text.get('1.0', 'end').splitlines() if u.strip()]
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
            archive_urls = [u for u in urls if not is_lolroms_url(u)]
            if archive_urls:
                self.root.after(0, lambda: self.dl_lbl_verify.config(
                    text='Fetching file metadata from archive.org API...'
                ))
                for base_url in archive_urls:
                    all_hashes.update(fetch_file_hashes(base_url, headers))
                self.root.after(0, lambda: self.dl_lbl_verify.config(
                    text=f"Metadata: {len(all_hashes)} files loaded"
                ))
            else:
                self.root.after(0, lambda: self.dl_lbl_verify.config(
                    text='lolroms source — skipping metadata fetch'
                ))

            url_map = {}
            for base_url in urls:
                base_url_stripped = base_url.split('#')[0].rstrip('/')
                for data in self.rom_dict.values():
                    if data['selected']:
                        fname      = data['selected']['filename']
                        direct_url = data['selected'].get('direct_url')
                        if fname not in url_map:
                            if direct_url:
                                # lolroms / wayback: use the extracted direct URL
                                url_map[fname] = direct_url
                            else:
                                url_map[fname] = f"{base_url_stripped}/{quote(fname, safe='')}"

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
                    draining   = False
                    target_par = max_par
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
                                            break

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
        self.dl_lbl_verify.config(text='')
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


