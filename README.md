# RomGoGetter v0.14

**ROM curator and downloader for archive.org, lolroms.com, Minerva, and local collections. It helps you to download only the roms you want from larger romsets.**

RomGoGetter started as a 1G1R tool — pick the best regional variant of each game and skip the rest. It has since grown into a full ROM curation pipeline: pull no-intro and redump listings from multiple repositories, apply smart filtering to build exactly the collection you want, then download or copy only what's needed.

---

## Sources

- **archive.org** — fetches the file listing from any public (or credentialed) Internet Archive collection; supports S3 keys for access-restricted collections; works with "show all" and zip content pages
- **lolroms.com** — scrapes file listings and direct download URLs from category pages, including Wayback Machine snapshots
- **Minerva / Myrient** — downloads individual files from collection torrents via a full `aria2c` wrapper
- **Local directory** — scans a folder on disk and treats it as a source; local files are preferred over remote when the same filename exists in both. Enables using RomGoGetter as a **smart copy tool**: curate a large local collection down to a filtered subset in a new folder
- **Multiple sources at once** — paste multiple URLs (one per line); listings are merged into a single pool before filtering

---

## Selection

### 1G1R
The core mode. For each game title, picks one ROM: English preferred, highest revision, most language tracks. Excludes demos, kiosk builds, betas, prototypes, and non-game discs automatically.

### Modes

| Mode | Description |
|------|-------------|
| `1G1R English only` | One ROM per game, English/Western regions only, prefers multiple lanuages |
| `1G1R` | One ROM per game, best available region |
| `All files` | Every game rom file selected |
| `None` | All files shown, none pre-selected — toggle manually |
| `DAT` | Cross-reference against a No-Intro / Redump DAT local or remote file; matched files selected, unmatched shown as missing |
| `Top N` | Filter by a ranked game list — see below |

### Top N
Fetches a ranked list of games from an external source and maps them to your ROM pool using fuzzy/token title matching, then applies 1G1R within each matched group.

**Sources:** RetroAchievements (player count), IGDB (aggregate rating)

**Filter options:**
- **Top N** — take the N highest-ranked games
- **Min score** — take all games above a score threshold
- **Max size GB** — limit selection by commulative size

### DAT Group
Apply multiple DAT files simultaneously (local paths or URLs). Useful for cross-referencing against a curated list spanning several platforms or sets.

### Manual override
Double-click any file in the Analysis tab to toggle it in or out of the download queue. The selected size card updates live.

### Missing files
A title is shown as **Missing** (red) when it was matched to a ROM in the file listing but that ROM is not available — not present in the local source and not reachable remotely. Titles with no fuzzy match and titles trimmed by a size budget are not counted as missing.

---

## Download

- **Parallel slots** — up to 20 simultaneous downloads, adjustable live while downloading
- **Resume** — partial `.part` and torrented files are resumed automatically on retry
- **Stuck detection** — configurable idle timeout cancels and retries hung connections
- **Verification before skipping:**

| Mode | Behaviour |
|------|-----------|
| `Overwrite` | Always re-download |
| `Name` | Skip if file exists |
| `Size` | Skip if file exists and size matches |
| `Hash` | Skip if MD5 matches archive.org metadata; falls back to size; slow |

- **Local copy** — files sourced from a local directory are copied instead of downloaded, skipped if destination size already matches
- **Minerva torrents** — uses `aria2c` to fetch individual files by torrent index without downloading the full archive; temp torrent files are cleaned up after
- **Export DAT** — export the current selection as a No-Intro compatible DAT file

---

## Usage

### Basic 1G1R download from archive.org

1. Paste an archive.org collection URL(s) into **Source URLs**
2. Set a **Destination** folder
3. Choose a **Mode** (default: `1G1R English only`)
4. Click **GoGet!** — the Analysis tab shows what will be downloaded
5. Click **Download**

### Top N by size budget

1. Set source URL(s) and destination
2. Set Mode to `Top N`
3. In the Analysis tab, select source, platform, and **Max size GB**
4. Click **Fetch & Apply** — pages are fetched one at a time, full 1G1R selection is run after each page, and fetching stops as soon as the budget is reached
5. Click **Download**

### Smart copy from local collection

1. Set **Additional Local Source** to your existing ROM directory
2. Leave Source URLs blank (or add a URL source to fill in files missing locally)
3. Set **Destination** to a new folder
4. Click **GoGet!** — local files appear in the list with exact sizes, preferred over remote
5. Apply Top N or 1G1R filtering, then click **Download** to copy selected files

### Minerva/Myrient

1. Paste a Minerva browse URL
2. This uses the bundled `aria2c.exe`
3. A torrent warning banner is shown as a reminder to seed via a proper torrent client

---

## Requirements

- Python 3.10+
- tkinter (included with most Python distributions)
- `aria2c` — required for Minerva/Myrient downloads

---

## Installation

```
git clone https://github.com/shokoe/RomGoGetter
cd RomGoGetter
python RomGoGetter_v0_14.pyw
```

Currently this is tested only on windows.

---

## File layout

- Python 3.10+
- tkinter (included with standard Python on Windows)
- **aria2c.exe** — required for Minerva downloads; place next to the `.pyw` file
  - Download from [aria2.github.io](https://aria2.github.io/)
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

MIT — see [LICENSE](LICENSE)

© 2026 Shoko

---

<img width="1091" height="958" alt="image" src="https://github.com/user-attachments/assets/38d02881-0e07-475f-95f9-40b772f12f97" />
<img width="1086" height="961" alt="image" src="https://github.com/user-attachments/assets/f45c9294-a90a-4b7c-bd09-8d01231c3bee" />
<img width="1089" height="965" alt="image" src="https://github.com/user-attachments/assets/9aa43e7b-8a2d-4c39-bde7-e584b160f147" />



