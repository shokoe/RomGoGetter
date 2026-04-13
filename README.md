# RomGoGetter v0.13

A ROM downloader and curator for **archive.org**, **lolroms.com**, and **Minerva Archive**. Fetches file listings from public ROM sources, applies smart filtering — 1G1R, DAT matching, RetroAchievements top lists, IGDB critic rankings — and downloads only the files you actually want. Every mode supports manual selection nmodification by doubleclicking the individual files or prressing space, toggling selection.

> ⚠ This app is not a torrents client and therefor doesn't seed. If you download from Minerva, please use a proper torrent client to seed back to the community.

---

## Requirements

- **Python 3.10+**
- **tkinter** — included with standard Python on Windows; on some Linux distros: `sudo apt install python3-tk`
- **aria2c** — required only for Minerva downloads. Bundled in the repository (`aria2c.exe`). Linux/Mac users can install via package manager or download from [aria2.github.io](https://aria2.github.io/)

No third-party Python packages required.

---

## Installation

```
git clone https://github.com/shokoe/RomGoGetter
python RomGoGetter_v0.13.pyw
```

On Windows, `.pyw` files run without a console window by default.

---

## Usage

### Basic workflow

1. **Setup tab** — paste one or more source URLs into the URL box (one per line) or use saved examples
2. Click **GoGet!** — fetches the file listing
3. **Analysis** -  Choose a **Mode** at the top to apply the selected mode
4. Insert additional data as needed.
5. Review the selection — toggle individual files by double-clicking or pressing Space
6. Click **Download**
7. Click **Start**

### URL formats supported

```
# Internet Archive collection page ("Show all")
https://archive.org/download/No-Intro-Nintendo-DS

# lolroms.com category page
https://lolroms.com/Nintendo-DS/

# Minerva Archive browse page
https://minerva-archive.org/browse/No-Intro/Nintendo%20-%20Nintendo%20DS/
```

Multiple URLs of the same or different source types can be combined in the URL box.

### URL Groups
Save and recall named sets of URLs using the group dropdown in the Setup tab — useful for collections you return to regularly.

### Internet Archive S3 Keys
Optional — only needed for access-restricted collections. Get your keys at [archive.org/account/s3.php](https://archive.org/account/s3.php). The key frame only appears when an archive.org URL is detected.

### Minerva / aria2c
For Minerva sources, the Download button triggers aria2c to download via torrent. Each browse URL maps to its own torrent — if you have multiple Minerva URLs, all their torrents are fetched and matched. Files already present in the destination are skipped automatically.

**Please seed back** — this app sets `--seed-time=0` and exits aria2c immediately after each file completes, with what this app is aimed for, any other option would be unrealistic. Open the torrent (saved in the target dir) in a proper torrent client to give back to the community.

`aria2c.exe` is bundled in the repository. Linux/Mac users should place an `aria2c` binary next to the script or have it on PATH.

---

## Features

### Sources
- **Internet Archive (archive.org)** — direct HTTP downloads with S3 key support for access-restricted collections, MD5 hash verification, ETag-based skip-if-unchanged, and resume support
- **lolroms.com** — scrapes the file listing and downloads directly
- **Minerva Archive** — individual files torrent-based downloads via aria2c, with per-collection torrent detection and multi-URL support (each browse URL has its own torrent)
- Multiple URLs can be combined — useful for split collections (e.g. a main set + an aftermarket/private subset)

### Selection Modes
| Mode | Description |
|------|-------------|
| **1G1R English only** | One game, one ROM — English language filtered, best revision |
| **1G1R** | One game, one ROM — any Western region, best revision |
| **All files** | No filtering, download everything |
| **None** | Show all files unselected — pick manually |
| **DAT** | Cross-reference against one or more No-Intro / Redump DAT files |
| **RA Top** | Top N games by RetroAchievements player count for a given console |
| **IGDB Top** | Top N games by IGDB aggregated critic score for a given platform |

### 1G1R Logic
- Prefers English language (`En` tag) → Western region → highest revision number → most languages
- Handles multi-disc games correctly — each disc gets its own 1G1R group, all discs of the winning variant are selected together
- Excludes demos, kiosks, betas, alphas, prototypes, samples, magazines, and covermounts automatically
- Article normalization for grouping (strips "The", "Le", "Die", "El" etc. in multiple languages)

### DAT Mode
- Load local DAT files or fetch from URLs (No-Intro, Redump, or any XML DAT)
- Named DAT groups — save and recall sets of DAT URLs with one click
- Extension-stripped matching — matches archive filenames to DAT entries regardless of format differences
- Missing entries shown in red; matched entries shown in green

### RetroAchievements Top N
- Fetches the RA leaderboard for any supported console directly from the source Google Sheet
- Fuzzy title matching with descending threshold (1.0 → 0.70) to handle naming variations
- English-first matching with non-English fallback for Japan-exclusive titles
- 1G1R applied within each matched title group
- Works great for Nintendo platforms where critic score data is sparse

### IGDB Top N
- Uses the IGDB API (Twitch credentials embedded) — no user setup required
- Fetches platforms dynamically on first use
- Sorts by aggregated critic rating (Metacritic etc.)
- Works best for platforms with good critic coverage (PS1, PS2, Xbox, PC etc.)
- Same fuzzy matching + 1G1R logic as RA Top

### Downloads
- Parallel HTTP downloads with up to 20 configurable slots
- Per-slot progress bars with speed, ETA, and file size
- Pause / resume mid-session
- Stuck download detection and automatic retry (configurable timeout and retry count)
- MD5 hash verification against archive.org metadata API
- ETag cache — skips files that haven't changed since last download
- Size cache — fast re-run skip without re-fetching metadata
- Local source folder — copies from a local directory before downloading, saving bandwidth
- aria2c integration for Minerva torrent downloads with `--select-file` per-file control

### Analysis Tab
- Sortable, searchable file list with colour-coded status (selected / unselected / non-English / non-game)
- Click legend items to cycle through filter states
- Type filter with regex support
- Stat cards: total titles, total size, selected ROMs, selected size, non-English count, non-game count
- Export to DAT — generate a No-Intro compatible XML DAT of your selected files
- Live re-filtering — switch modes without re-fetching

### Settings Persistence
All settings survive restarts and the Reset button:
- URLs and selected URL group
- Destination folder and local source folder
- S3 access/secret keys
- Download options (parallel slots, retries, stuck timeout, aria2c split, speed limit)
- Verification mode, analysis mode
- RA console selection and Top N value
- IGDB platform selection and Top N value
- DAT group selection and URLs
- Window geometry

---

## File layout

```
RomGoGetter_v0.13.pyw        # main script
aria2c.exe                   # bundled, for Minerva downloads (Windows)
RomGoGetter_settings.json    # auto-created, persists all settings
RomGoGetter_groups.json      # auto-created, persists URL groups
RomGoGetter_dat_groups.json  # auto-created, persists DAT groups
```

---

## Credits

- **[Internet Archive](https://archive.org)** — the world's library. [Donate](https://archive.org/donate)
- **[Myrient](https://myrient.erista.me)** — the team behind the Minerva Archive. [Memorial](https://minerva-archive.org/memorial/)
- **[lolroms.com](https://lolroms.com)** — [Donate](https://www.paypal.com/donate/?hosted_button_id=EG4YN6QGHCB6C)
- **[RetroAchievements](https://retroachievements.org)** — achievements and top lists for retro games
- **[IGDB](https://www.igdb.com)** — game database by Twitch

---

## License

MIT — see LICENSE file for details.  
Copyright © 2026 Shoko

---

Source:

<img width="1149" height="1174" alt="image" src="https://github.com/user-attachments/assets/9c9b4f2d-7aac-4119-9e44-783ccfd6d92d" />

Selection:

<img width="1149" height="1179" alt="image" src="https://github.com/user-attachments/assets/497736d6-7fc5-4a40-94f9-43e531343a86" />

Download:

<img width="1145" height="1174" alt="image" src="https://github.com/user-attachments/assets/0a8ca909-ff07-42b3-89fd-ee531a19cb1c" />

