# YouTube to MP3 Downloader Pro

A simple desktop app to download individual YouTube videos as high-quality 320kbps MP3 files, with a queue manager that lets you add multiple links, pause/resume, cancel, and prioritize downloads.

## Requirements

- **Python 3.10+**
- **Git** (optional, for cloning)

---

## Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd "mp3 downloader"
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the virtual environment

**Windows:**
```bash
venv\Scripts\activate
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

> `yt-dlp` handles YouTube downloading and `static-ffmpeg` bundles a portable `ffmpeg` binary — no separate ffmpeg installation required.

---

## Running the App

```bash
python downloader.py
```

Or on Windows, double-click **`run.bat`** if it's present.

---

## How to Use

1. Paste a YouTube video URL into the input field at the top.
2. Click **Add to Queue** — the download starts automatically.
3. Add as many links as you want. Downloads and MP3 conversions run in parallel in the background.

### Queue Controls

| Button | Action |
|---|---|
| **Pause Queue** | Pauses after the current download, or aborts it immediately |
| **Resume Queue** | Resumes all paused items |
| **Cancel Selected** | Removes the selected item from the queue (aborts if downloading) |
| **Download Next** | Moves the selected item to the top of the queue |

---

## Output

| Folder | Contents |
|---|---|
| `downloaded/` | Final 320kbps MP3 files |
| `.temp/` | Temporary raw audio files (auto-deleted after conversion, hidden) |

Both folders are listed in `.gitignore` and will not be committed.

---

## Notes

- Playlist links are **not** downloaded — only the individual video in the URL is processed. Remove the `&list=...` part of the URL if you only want a single song.
- On first run, `static-ffmpeg` may take a moment to initialize.
