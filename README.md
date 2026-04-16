# RomGoGetter v0.14

**ROM curator and downloader for archive.org, lolroms.com, Minerva, and local collections. It helps you to download only the roms you want from larger romsets.**

RomGoGetter started as a 1G1R tool — pick the best regional variant of each game and skip the rest. It has since grown into a full ROM curation pipeline: pull file listings from multiple sources, apply smart filtering to build exactly the collection you want, then download or copy only what's needed.

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

## License

MIT — see [LICENSE](LICENSE)

© 2026 Shoko
