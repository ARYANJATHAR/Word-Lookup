# Word Lookup

A tiny Windows tray app that shows the meaning of any word you copy, right next to your cursor. Powered by Google's Gemini AI.

## Features
- **Instant definitions**: meaning, part of speech, pronunciation, an example sentence and synonyms
- **Click a synonym to copy it**, or copy the whole definition with one click
- **Two ways to trigger**: automatically when you copy 1–3 words, or only when you select a word and press a shortcut (e.g. `Ctrl+Shift+D`)
- **Modern popup**: light and dark themes (follows Windows), rounded corners on Windows 11, sharp on high-DPI screens, stays open while you hover it
- **Fast repeat lookups**: answers are cached, so words you've looked up before appear instantly and cost nothing
- **Recent lookups** in the tray menu
- **Private by design**: your API key is encrypted with your Windows account (DPAPI), and copies from password managers are ignored

## Installation

### Method 1: Download the app (Recommended)
1. Download `WordLookup_2.0.0.exe` from the [latest release](https://github.com/ARYANJATHAR/Word-Lookup/releases/latest)
2. Run it. No installation or Python needed. The first launch can take a few seconds.
3. Paste your free Gemini API key ([get one here](https://aistudio.google.com/apikey)) and click **Get started**
4. Optional: right-click the tray icon and enable **Start with Windows**

Upgrading from 1.x? Exit the old version from its tray icon first (or uninstall it).

### Method 2: Run from Source
Requires Python 3.10+ on Windows.
```bash
git clone https://github.com/ARYANJATHAR/Word-Lookup.git
cd Word-Lookup
pip install -r requirements.txt
python main.py
```
The setup window asks for your API key on first run. Alternatively, create a `.env` file next to `main.py`:
```
GEMINI_API_KEY=your_api_key_here
```
A key set this way takes priority over the one saved in Settings.

## Usage
1. Word Lookup runs in the system tray (bottom-right corner; check the `^` overflow area).
2. Copy any word or short phrase (up to 3 words), and a card with its meaning appears next to your cursor.
   - In shortcut mode, select the word and press your shortcut instead.
3. Hover the card to keep it open, drag it to move it, and click a synonym to copy it.

### Tray menu
- **Pause / Resume lookups**: also triggered by clicking the tray icon
- **Recent lookups**: reopen any of your last 8 words
- **Settings…**: change API key, trigger mode, shortcut, Gemini model, theme and how long the popup stays
- **Start with Windows**
- **Exit**

## Notes
- An internet connection is required for new lookups.
- Settings, cache and logs are stored in `%APPDATA%\Word Lookup`.
- The default model, `gemini-flash-lite-latest`, is Google's cheapest and always points to the newest Flash-Lite model.
- Upgrading from 1.x: you'll be asked for your API key once more so it can be stored with the new encryption.
- If Windows SmartScreen or your antivirus flags the app, choose "More info → Run anyway". The app isn't code-signed.

https://github.com/user-attachments/assets/6ceff3f2-ba28-4c7e-9a1b-be2c6171f2a7
