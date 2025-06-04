import pyperclip
import time
import tkinter as tk
import threading
import ctypes
import re
import requests
import os
from dotenv import load_dotenv
import pystray
from PIL import Image;
import winreg
import logging
import sys

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    if not is_admin():
        # Re-run the program with admin rights
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

# Set up logging to user's temp directory
log_file = os.path.join(os.environ.get('TEMP', os.getcwd()), 'word_lookup_debug.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

# Load environment variables from .env file
logging.info("Starting application...")
load_dotenv()

# Check if we need admin rights for startup functionality
if len(sys.argv) > 1 and sys.argv[1] == "--startup":
    run_as_admin()

# Get API key from environment variable
def load_api_key():
    logging.info("Loading API key...")
    
    # Try multiple locations for .env file
    possible_paths = [
        '.env',  # Current directory
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),  # Script directory
        os.path.join(os.path.dirname(sys.executable), '.env')  # Executable directory
    ]
    
    if getattr(sys, 'frozen', False):
        # If running as exe (PyInstaller)
        possible_paths.append(os.path.join(sys._MEIPASS, '.env'))
    
    api_key = None
    for env_path in possible_paths:
        if os.path.exists(env_path):
            logging.info(f"Found .env file at: {env_path}")
            load_dotenv(env_path)
            api_key = os.getenv('GEMINI_API_KEY')
            if api_key:
                logging.info("API key loaded successfully")
                break
    
    if not api_key:
        logging.warning("No API key found in .env files, prompting user...")
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        # Create a simple dialog
        dialog = tk.Toplevel(root)
        dialog.title("API Key Required")
        dialog.geometry("400x150")
        dialog.transient(root)
        dialog.lift()  # Lift the window to the top
        dialog.focus_force()  # Force focus
        
        # Center the dialog
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        
        tk.Label(dialog, text="Please enter your Gemini API Key:").pack(pady=10)
        entry = tk.Entry(dialog, width=50)
        entry.pack(pady=10)
        
        def save_key():
            key = entry.get().strip()
            if key:
                # Try to save to multiple locations
                saved = False
                for env_path in possible_paths:
                    try:
                        with open(env_path, 'w') as f:
                            f.write(f'GEMINI_API_KEY={key}')
                        saved = True
                        logging.info(f"API key saved to: {env_path}")
                        break
                    except Exception as e:
                        logging.warning(f"Could not save to {env_path}: {e}")
                
                if not saved:
                    # If we couldn't save to any location, try user's documents
                    docs_path = os.path.join(os.path.expanduser('~'), 'Documents', '.env')
                    try:
                        os.makedirs(os.path.dirname(docs_path), exist_ok=True)
                        with open(docs_path, 'w') as f:
                            f.write(f'GEMINI_API_KEY={key}')
                        possible_paths.append(docs_path)
                        logging.info(f"API key saved to documents: {docs_path}")
                    except Exception as e:
                        logging.error(f"Could not save to documents: {e}")
                
                dialog.quit()
        
        tk.Button(dialog, text="Save", command=save_key).pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", dialog.quit)
        dialog.mainloop()
        dialog.destroy()
        root.destroy()
        
        # Try loading again after user input
        for env_path in possible_paths:
            if os.path.exists(env_path):
                load_dotenv(env_path)
                api_key = os.getenv('GEMINI_API_KEY')
                if api_key:
                    logging.info("API key loaded after user input")
                    break
    
    if not api_key:
        logging.error("No API key provided. Application will close.")
        raise ValueError("No API key provided. Application will close.")
    
    return api_key

# Replace the current api_key assignment with this
try:
    api_key = load_api_key()
except Exception as e:
    logging.error(f"Failed to load API key: {str(e)}")
    sys.exit(1)

# Add error handling for missing API key
if not api_key:
    logging.error("GEMINI_API_KEY not found in environment variables.")
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please check your .env file.")

# Global flag to control the monitoring thread
monitoring = True

def get_meaning_and_synonyms_from_gemini(phrase):
    logging.debug(f"Getting meaning for phrase: {phrase}")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    prompt_text = (
        f"Provide a short, clear meaning and 3 synonyms for the word or phrase: \"{phrase}\".\n"
        "Format your answer like this:\nMeaning: <meaning here>\nSynonyms: synonym1, synonym2, synonym3"
    )
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt_text
                    }
                ]
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        res_json = response.json()
        # Parsing AI output from Gemini response
        answer = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        meaning = ""
        synonyms = ""
        for line in answer.split("\n"):
            if line.lower().startswith("meaning:"):
                meaning = line.split(":", 1)[1].strip()
            elif line.lower().startswith("synonyms:"):
                synonyms = line.split(":", 1)[1].strip()
        return meaning, synonyms
    except Exception as e:
        return f"⚠️ Error: {str(e)}", ""

# Get mouse position (Windows)
def get_mouse_pos():
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

# Popup window class
class Popup(tk.Tk):
    def __init__(self, phrase, meaning, synonyms, x, y, duration=5000):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#FFFFE0")
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Create main frame
        main_frame = tk.Frame(self, bg="#FFFFE0", cursor="hand2")
        main_frame.pack(expand=True, fill='both', padx=2, pady=2)
        
        # Add close button
        close_button = tk.Button(main_frame, text='×', command=self.destroy,
                               bg='#FFFFE0', fg='black', font=('Arial', 12, 'bold'),
                               relief='flat', padx=5, pady=0)
        close_button.pack(side='top', anchor='ne')
        
        text = f"{phrase}:\n\nMeaning:\n{meaning}\n\nSynonyms:\n{synonyms}"
        
        # Add main content
        label = tk.Label(main_frame, text=text, bg="#FFFFE0", fg="black",
                        font=("Segoe UI", 10), justify="left",
                        relief="solid", borderwidth=1, padx=10, pady=5)
        label.pack(expand=True, fill='both', padx=5, pady=5)
        
        # Bind drag events
        main_frame.bind('<Button-1>', self._start_drag)
        main_frame.bind('<B1-Motion>', self._on_drag)
        
        # Bind hover events
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        
        # Store duration and timer id
        self.duration = duration
        self.timer_id = None
        
        # Initialize drag data
        self._drag_data = {"x": 0, "y": 0}
        
        # Position window considering screen boundaries
        self.update_idletasks()  # Update window size
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        
        # Adjust position if too close to screen edges
        x = min(max(x, 0), screen_width - window_width)
        y = min(max(y, 0), screen_height - window_height)
        
        self.geometry(f"+{x}+{y}")
        self._start_timer()
    
    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def _on_drag(self, event):
        # Calculate new position
        x = self.winfo_x() + (event.x - self._drag_data["x"])
        y = self.winfo_y() + (event.y - self._drag_data["y"])
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Keep window within screen boundaries
        x = min(max(x, 0), screen_width - self.winfo_width())
        y = min(max(y, 0), screen_height - self.winfo_height())
        
        # Move window
        self.geometry(f"+{x}+{y}")
    
    def _start_timer(self):
        if self.timer_id:
            self.after_cancel(self.timer_id)
        self.timer_id = self.after(self.duration, self.destroy)
    
    def _on_enter(self, event):
        if self.timer_id:
            self.after_cancel(self.timer_id)
    
    def _on_leave(self, event):
        self._start_timer()

def show_popup(phrase, meaning, synonyms):
    x, y = get_mouse_pos()
    popup_x = x + 20
    popup_y = y + 20

    def popup_thread():
        popup = Popup(phrase, meaning, synonyms, popup_x, popup_y)
        popup.mainloop()

    threading.Thread(target=popup_thread, daemon=True).start()

# Validate copied text: alphabets and spaces only, max 3 words
def is_valid_phrase(text):
    text = re.sub(r'\s+', ' ', text.strip())
    if 1 <= len(text.split()) <= 3 and re.fullmatch(r'[A-Za-z ]+', text):
        return text
    return None

def clipboard_monitor():
    last_text = ""
    while monitoring:
        time.sleep(0.3)

        current_text = pyperclip.paste().strip()
        valid_phrase = is_valid_phrase(current_text)

        if valid_phrase and valid_phrase != last_text:
            last_text = valid_phrase
            meaning, synonyms = get_meaning_and_synonyms_from_gemini(valid_phrase)
            show_popup(valid_phrase, meaning, synonyms)

def add_to_startup():
    if not is_admin():
        # Re-run with admin rights and --startup flag
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, "--startup", None, 1)
        return False
        
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "Word Lookup"
    
    try:
        # Get the path of the executable
        if getattr(sys, 'frozen', False):
            # If running as exe (PyInstaller)
            app_path = sys.executable
        else:
            # If running as script
            app_path = os.path.abspath(__file__)
            
        # Open the registry key
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, 
                            winreg.KEY_SET_VALUE)
        
        # Set the value
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logging.error(f"Error adding to startup: {e}")
        return False

def remove_from_startup():
    if not is_admin():
        # Re-run with admin rights and --startup flag
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, "--startup", None, 1)
        return False
        
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "Word Lookup"
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, app_name)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logging.error(f"Error removing from startup: {e}")
        return False

# Modify the create_system_tray function to include startup options
# Add this at the top of your file with other imports
import os
import sys

# Modify the create_system_tray function
def create_system_tray():
    logging.info("Creating system tray icon...")
    try:
        # Get the correct path whether running as script or executable
        if getattr(sys, 'frozen', False):
            # If running as exe (PyInstaller)
            app_path = os.path.join(sys._MEIPASS, "app_icon.ico")
            logging.info(f"Running as exe, icon path: {app_path}")
        else:
            # If running as script
            app_path = "app_icon.ico"
            logging.info(f"Running as script, icon path: {app_path}")
            
        if not os.path.exists(app_path):
            logging.error(f"Icon file not found at: {app_path}")
            # Try alternate location
            app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
            logging.info(f"Trying alternate icon path: {app_path}")
            
        image = Image.open(app_path)
        logging.info("System tray icon loaded successfully")
        
        def on_exit(icon, item):
            global monitoring
            monitoring = False
            icon.stop()
            logging.info("Application exiting...")
        
        def on_toggle(icon, item):
            global monitoring
            monitoring = not monitoring
            if monitoring:
                threading.Thread(target=clipboard_monitor, daemon=True).start()
                logging.info("Monitoring enabled")
            else:
                logging.info("Monitoring disabled")
        
        def on_startup_toggle(icon, item):
            if item.checked:
                success = add_to_startup()
                logging.info("Added to startup" if success else "Failed to add to startup")
            else:
                success = remove_from_startup()
                logging.info("Removed from startup" if success else "Failed to remove from startup")
        
        # Create the system tray menu with startup option
        menu = (
            pystray.MenuItem("Enable/Disable", on_toggle, default=True),
            pystray.MenuItem("Run at Startup", on_startup_toggle, checked=lambda item: is_in_startup()),
            pystray.MenuItem("Exit", on_exit)
        )
        
        icon = pystray.Icon("Word Lookup", image, "Word Lookup", menu)
        logging.info("System tray icon created")
        return icon
    except Exception as e:
        logging.error(f"Error creating system tray: {str(e)}")
        return None

def is_in_startup():
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "Word Lookup"
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_READ)
        winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return True
    except:
        return False

if __name__ == "__main__":
    logging.info("Application main entry point")
    try:
        # Start clipboard monitoring thread
        monitor_thread = threading.Thread(target=clipboard_monitor, daemon=True)
        monitor_thread.start()
        logging.info("Clipboard monitoring thread started")

        # Create and run system tray
        icon = create_system_tray()
        if icon:
            logging.info("Running system tray icon...")
            icon.run()  # This will block until the icon is stopped
            logging.info("System tray icon stopped")
        else:
            logging.error("Failed to create system tray icon")
            sys.exit(1)
    except Exception as e:
        logging.error(f"Error in main: {str(e)}")
        raise
