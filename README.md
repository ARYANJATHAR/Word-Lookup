# Word Lookup

An intelligent clipboard monitor that provides instant word meanings and synonyms using Gemini AI. Simply copy any word or phrase to get instant definitions and synonyms in a convenient popup.

## Features
- Real-time clipboard monitoring
- Instant word definitions and synonyms
- Clean popup interface
- Powered by Google's Gemini AI

## Installation

### Method 1: Windows Installer (Recommended)
1. Download the latest installer from the `installer` folder
2. Run `WordLookup_Setup_1.0.0.exe`
3. Follow the installation wizard
4. Add your Gemini API key in the settings (first-time setup)

### Method 2: Run from Source
1. Clone the repository:
   ```bash
   git clone https://github.com/ARYANJATHAR/Word-Lookup.git
   cd Word-Lookup
   ```
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory and add your Gemini API key:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```
4. Run the application:
   ```bash
   python main.py
   ```

## Usage

### Getting Started
1. After installation, Word Lookup runs in your system tray
2. Look for the Word Lookup icon (^) in your system tray (bottom-right corner)
3. The application monitors your clipboard for words

### How to Use
1. **Looking Up Words:**
   - Select any word in any application
   - Press Ctrl+C or copy the word
   - A popup will appear with the word's meaning and synonyms
   

2. **System Tray Options:**
   Right-click the system tray icon (^) to access:
   - Settings: Enable/disable, click to enable and disable whenever you want 
   - Startup: Starts the application when the system is started , and configure from there .
   - Exit: Closes the application 

### Tips
- Internet connection is required for lookups
- You can copy up to 3 words at once
- The application runs in background to work (if the startup option is clicked)

## Note
- For the installer version, the application will start automatically after installation
- You can find the application in your system tray
- Right-click the tray icon to access settings or exit the application
- for api issues , change the api key by deleting the application and again dowload it to enter new api key , same procedure.
  
- If Windows security error appears, stop antivirus, download the application, then start antivirus again
