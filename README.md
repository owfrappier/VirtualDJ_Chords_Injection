# VirtualDJ Chords Injection

AI-powered chord detection and injection tool for VirtualDJ `database.xml`.

This tool analyzes your audio files (AIFF, WAV, FLAC, etc.), applies fine pitch detection and correction to **A=440 Hz**, and writes chords as POI markers directly into VirtualDJ.

---

## ⚠️ macOS Requirement

⚠️ **macOS Full Disk Access is required for AppleScript to work properly**

---

## Features

- Fast batch chord detection
- Fine pitch detection & correction (to A=440 Hz)
- Writes chords directly into VirtualDJ database
- Automatic database backup
- Supports large libraries (thousands of tracks)
- Optimized for macOS (Apple Silicon)

---

## Requirements

- VirtualDJ 2026 > BUILD 9295 (2026-04-19)
- macOS (Apple Silicon recommended)
- Python 3.10+
- VirtualDJ

---

## Python Setup (Recommended)

This project uses a dedicated Python virtual environment.

### 1. Create a virtual environment

mkdir -p ~/.venvs
python3 -m venv ~/.venvs/audio312

### 2. Activate it

source ~/.venvs/audio312/bin/activate

### 3. Install dependencies

pip install --upgrade pip
pip install numpy librosa soundfile scipy

### 4. Verify installation

python -c "import librosa, numpy"

---

## AppleScript Python Path

Make sure your AppleScript uses this Python path:

/Users/YOUR_USERNAME/.venvs/audio312/bin/python

Replace `YOUR_USERNAME` with your macOS username.

---

## Usage

1. Double-click:

VDJ Chord Injector V12.applescript

2. Select your `database.xml`

3. Choose analysis mode:
- Full folder
- Single file
- Filter by first letter

4. Let the analysis run in Terminal

---

## VirtualDJ Usage Notes ⚠️

### Do not open VirtualDJ during analysis

- The script automatically closes VirtualDJ before starting
- Do NOT reopen VirtualDJ during analysis
- This may corrupt or overwrite your database

---

### Selecting the correct database.xml

#### External drive (recommended)

/Volumes/YourDrive/VirtualDJ/database.xml

👉 Auto-detected by the script if available

---

#### Internal drive

/Users/YOUR_USERNAME/Library/Application Support/VirtualDJ/database.xml

---

### Important

- Always select the database matching your audio files location
- Using the wrong database will result in:
  - Missing chords
  - Wrong library being modified

---

## macOS Permissions ⚠️ (Important)

If you get errors like:

Operation not permitted
Permission denied

Enable Full Disk Access:

System Settings → Privacy & Security → Full Disk Access

Add:
- Terminal
- Script Editor (or the app used to run the script)

---

## ⚠️ Disclaimer & Safety

### Use at your own risk

This tool directly modifies your VirtualDJ `database.xml`.

👉 You MUST manually backup your database before using this tool.

Example:

Copy database.xml → database_backup.xml

---

### Important Warning

- This tool is intended for **advanced users and developers only**
- Incorrect usage may:
  - Corrupt your VirtualDJ database
  - Cause data loss
  - Affect your music library

---

### Liability

By using this tool, you agree that:

- You are fully responsible for any changes made
- The author is **not responsible** for any damage or data loss
- This tool is **not affiliated with VirtualDJ or its developers**

---

### Safety Summary

✔ Always backup your database manually  
✔ Do not run VirtualDJ during analysis  
✔ Use only if you understand the process  

---

## Recommended Audio Formats

- AIFF ✔ (best)
- WAV ✔
- FLAC ✔
- M4A / AAC ⚠️ (slower, less accurate)

---

## Tested Environment

- macOS (Apple Silicon)
- Python 3.12
- librosa 0.10+

---

## License

MIT License (recommended)
