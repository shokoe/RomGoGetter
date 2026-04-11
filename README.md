# RomGoGetter v0.9

RomGoGetter started as a 1G1R direct HTTP downloader for archive.org, but has since developed into a powerful general ROM selection and download tool — supporting multiple sources, intelligent filtering, and torrent-based downloading via the Minerva Archive.

---

## Usage

```
python RomGoGetter_v0.9.pyw
```

Or double-click the `.pyw` file on Windows.

---

## Sources

- **archive.org** — paste one or more collection URLs; files are fetched directly via HTTP with S3 key support for faster speeds
- **lolroms.com** — full category page support including Wayback Machine archived pages
- **Minerva Archive** — paste a browse URL (`minerva-archive.org/browse/...`)

Multiple source URLs can be combined in the URL box — RomGoGetter fetches and merges them all. Examples are included and you can add your own groups.

---

## Selection

Source filenames must be in no-intro/redump format!

- **1G1R** — picks the single best version of each game: English > western > any non-excluded fallback
- **1G1R English only** — same as 1G1R but restricts selection to English-speaking countries (USA, UK, Europe, Australia, Canada, NZ, Ireland); games only available in non-English-speaking countries are shown in red
- **All files** — selects everything, no filtering
- **None** — deselects everything, manual selection only
- **DAT file** — cross-reference against a No-Intro or Redump DAT file; missing ROMs shown in red

**Treeview legend:**
- 🟢 ● Selected
- ○ Unselected
- 🔴 ✗ Non-English / Missing
- 🟡 ⊘ Non-Game

**Filtering:**
- Live search bar
- Type filter — comma-separated extensions or regex, with live preview and Apply to deselect
- Double-click or Space to toggle individual entries
- Click legend items to cycle through that category

**Analysis cards** show total/selected counts and sizes, non-English, and non-game totals — clickable to jump to next item in category.

---

## Download

### HTTP (archive.org / lolroms)
- Parallel downloads with dynamic slot management — change parallel count mid-download, slots drain gracefully
- Per-slot progress bars with filename, size, speed, and ETA
- Overall progress bar, speed, ETA, and elapsed time
- Verification modes: **Hash** (MD5), **Size**, **Name**, **Overwrite**
- Additional local source directory — files found there are hash-verified and copied instead of downloaded
- Retries with configurable count
- Idle timeout — detects and cancels stuck downloads
- Free space check and confirmation dialog before starting
- Resume support via `.part` files

### Minerva Archive (aria2c)
- Downloads via torrent using **aria2c.exe** (bundled alongside the `.pyw`)
- Fetches the collection torrent, maps selected files to their torrent IDs, and drives one aria2c process per slot
- **Split** — parallel connections per file (`--split` / `--max-connection-per-server`)
- **Limit (MB)** — per-file speed cap in MB/s
- **Retries** — on failure, wipes the partial download and retries from scratch
- Pause/Resume — suspends all aria2c processes via Windows API
- Already-downloaded files are skipped automatically; interrupted downloads are resumed via aria2c's `-c` flag
- Each file downloads into an isolated `thread_<id>/` subdirectory, copied to destination on completion

### General
- Configurable: Parallel, Retries, Idle timeout
- Export selection as DAT file (No-Intro/Redump format)
- Group save/load — save and recall sets of URLs
- Source-aware donate button:
  - archive.org → Donate to the Internet Archive
  - lolroms → Donate to lolroms.com
  - Minerva → Pay Respects to Myrient ❤️

---

## Requirements

- Python 3.10+
- tkinter (included with standard Python on Windows)
- **aria2c.exe** — required for Minerva downloads; place next to the `.pyw` file
  - Download from [aria2.github.io](https://aria2.github.io/)

---


## License

MIT

---

<img width="1149" height="1174" alt="image" src="https://github.com/user-attachments/assets/9c9b4f2d-7aac-4119-9e44-783ccfd6d92d" />
<img width="1149" height="1179" alt="image" src="https://github.com/user-attachments/assets/497736d6-7fc5-4a40-94f9-43e531343a86" />
<img width="1145" height="1174" alt="image" src="https://github.com/user-attachments/assets/0a8ca909-ff07-42b3-89fd-ee531a19cb1c" />

By Shoko, 2026
