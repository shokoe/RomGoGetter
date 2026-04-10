# RomGoGetter v0.8

A 1G1R ROM downloader and curator for ROM preservation sites including [archive.org](https://archive.org) and [lolroms.com](https://lolroms.com).

Built for people who want a clean, verified, one-game-one-ROM collection without manually hunting through thousands of files.

---

## What it does

RomGoGetter fetches ROM collection listings from supported sources, applies 1G1R filtering (best regional version, highest revision, most languages), lets you review and customise the selection, then downloads and verifies the files — resuming where it left off if interrupted.

It also supports DAT files for cross-referencing your collection against a No-Intro/Redump database, showing you exactly what you have and what's missing from the source.

---

## Supported Sources

| Source | URL format | Verification |
|--------|-----------|-------------|
| archive.org | `https://archive.org/download/...` | Hash (MD5) + Size |
| lolroms.com | `https://lolroms.com/...` | Name only (no hash available) |

Multiple URLs can be combined in a single fetch — useful when a collection is split across multiple archive.org items or sources. Just paste one URL per line.

---

## Requirements

- Python 3.10 or later
- `tkinter` (included with standard Python on Windows and most Linux distros)
- No third-party packages required

---

## How to run

**Windows:**
```
double-click RomGoGetter_v0_5.pyw
```
or
```
python RomGoGetter_v0_5.pyw
```

**Linux / macOS:**
```
python3 RomGoGetter_v0_5.pyw
```
To detach from the terminal on Linux:
```
nohup python3 RomGoGetter_v0_5.pyw &
```

---

## Workflow

The app follows a strict linear flow:

```
Setup → GoGet! → Analysis → Download
```

### 1. Setup

- Paste one or more collection URLs (one per line) — archive.org and lolroms.com supported
- Set your **Destination** folder (full path, created automatically if needed)
- Optionally set an **Additional Local Source** directory — files found here are hash-verified and copied instead of downloaded, saving bandwidth
- Optionally enter archive.org **S3 keys** for access-restricted collections
- Adjust **Parallel downloads**, **Retries**, and **Stuck timeout**
- Save your URL sets as named **Groups** for quick reuse
- Click **GoGet!** to fetch the file listing

### 2. Analysis

After fetching, switch between filter modes using the **Mode** dropdown:

| Mode | Description |
|------|-------------|
| 1G1R English only | Best English/western version per game |
| 1G1R | Best version per game, falls back to any region |
| All files | Every file, excluding demos/updates |
| None | Clear all selections |
| DAT file | Cross-reference against a No-Intro/Redump DAT |

The table shows all files colour-coded:
- 🟢 **●** Selected for download
- ⚪ **○** Unselected
- 🔴 **✗** Non-English / Missing from source (DAT mode)
- 🟡 **⊘** Non-Game (demo, kiosk, beta, update, etc.)

**Double-click** or **Space** on any row to toggle it in/out of the download queue.

Click any **card** or **legend item** to cycle through rows of that type.

Use the **Search** bar to filter the list as you type.

Use the **Type filter** to select specific extensions (comma separated) OR as a regex selection when special charecters are included.

In **DAT mode**, browse a DAT file to cross-reference. Files found in the source show green, files in the DAT but missing from the source show red. Click the Missing card to cycle through missing entries — useful for finding alternative versions manually.

### 3. Download

- Choose a **Verify** mode:
  - **Hash** — full MD5 verification against archive.org metadata (recommended)
  - **Size** — exact byte count comparison (faster)
  - **Name** — skip if file exists (fastest, no verification)
  - **Overwrite** — always re-download
- Click **Start** and confirm
- Downloads resume from `.part` files if interrupted — just run again
- Progress bar reflects already-completed files from previous runs
- Variables are dynamic

---

## 1G1R Selection Logic

RomGoGetter picks the best version per game title using this priority:

1. **English language tag** (`En`) preferred over western-only
2. **Higher revision** wins (`Rev 11` beats `Rev 7`, `Rev B` beats `Rev A`)
3. **More languages** as tiebreaker
4. **Native English countries** (USA, UK, Europe, Australia, Canada, etc.) treated as implicitly English
5. **Demos, betas, updates, kiosk builds** excluded automatically
6. **Multi-disc games** — each disc is treated as its own title, so all discs are selected independently
7. In plain **1G1R** mode (not English-only), falls back to best available if no western version exists

---

## DAT File Support

DAT files from [No-Intro](https://www.no-intro.org) and [Redump](http://redump.org) are supported for selection cross-referencing.

**Important:** DAT files contain hashes and sizes for the **decompressed ROM**, not the downloaded archive (`.7z`, `.zip`). For this reason, DAT data is used for **selection only** — verification still uses the archive.org source metadata.

Extension matching is done without the file extension, so `Game (USA).zip` correctly matches `Game (USA)` in the DAT regardless of compression format.

---

## Files

| File | Purpose |
|------|---------|
| `RomGoGetter_v0_5.pyw` | Main application |
| `RomGoGetter_settings.json` | Saved settings (auto-created) |
| `RomGoGetter_groups.json` | Saved URL groups (auto-created) |

---

## Known Limitations

- DAT verification is not supported (DAT hashes are for uncompressed ROMs)
- No GUI for managing `.bad` files (files that failed verification) — delete them manually to trigger a re-download

---

## Sources

- [archive.org](https://archive.org) — primary ROM source, full hash verification
- [lolroms.com](https://lolroms.com) — secondary source, name-based verification only
- [No-Intro DATs](https://www.no-intro.org) — recommended for DAT cross-referencing
- [Redump DATs](http://redump.org) — for disc-based systems

---
<img width="1145" height="1175" alt="image" src="https://github.com/user-attachments/assets/e671a865-f5cf-4dd4-9ef1-ff5a60100772" />
<img width="1144" height="1174" alt="image" src="https://github.com/user-attachments/assets/89c37595-3bfd-4809-b85d-9c4181c95f03" />
<img width="1151" height="1176" alt="image" src="https://github.com/user-attachments/assets/3476a734-980a-413a-bc09-3f07bc7a0a13" />


*By Shoko*
