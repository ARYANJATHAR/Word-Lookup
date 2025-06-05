import pyperclip
import time
import tkinter as tk
import tkinter.messagebox
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
import base64
from cryptography.fernet import Fernet
import json
from pathlib import Path

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    if not is_admin():
        try:
            logging.info("Requesting admin rights...")
            # Get the path of the executable
            if getattr(sys, 'frozen', False):
                app_path = sys.executable
            else:
                app_path = os.path.abspath(__file__)
            
            # Use the full path to python.exe for scripts
            if not getattr(sys, 'frozen', False):
                python_exe = sys.executable
                args = f'"{app_path}" --startup'
            else:
                python_exe = app_path
                args = "--startup"
            
            logging.info(f"Launching with admin rights: {python_exe} {args}")
            result = ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas",
                python_exe,
                args,
                None,
                1
            )
            
            if result <= 32:  # Error codes are <= 32
                raise Exception(f"Failed to get admin rights. Error code: {result}")
                
            return True
        except Exception as e:
            logging.error(f"Error requesting admin rights: {e}")
            return False
    return True

def get_app_data_dir():
    """Get or create application data directory"""
    app_data = os.path.join(os.getenv('APPDATA'), 'Word Lookup')
    os.makedirs(app_data, exist_ok=True)
    return app_data

def get_encryption_key():
    """Get or create encryption key"""
    key_file = os.path.join(get_app_data_dir(), '.key')
    if os.path.exists(key_file):
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        return key

def encrypt_api_key(api_key):
    """Encrypt API key"""
    f = Fernet(get_encryption_key())
    return f.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_key):
    """Decrypt API key"""
    try:
        f = Fernet(get_encryption_key())
        return f.decrypt(encrypted_key.encode()).decode()
    except:
        return None

# Set up logging to exclude sensitive information
class SensitiveFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.sensitive_patterns = [
            r'GEMINI_API_KEY=[^\s]*',
            r'api_key=[^\s]*',
            r'key=[^\s]*'
        ]

    def format(self, record):
        message = super().format(record)
        for pattern in self.sensitive_patterns:
            message = re.sub(pattern, '[REDACTED]', message)
        return message

# Set up logging
log_file = os.path.join(get_app_data_dir(), 'word_lookup.log')
formatter = SensitiveFormatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler]
)

# Load environment variables from .env file
logging.info("Starting application...")
load_dotenv()

# Check if we need admin rights for startup functionality
if len(sys.argv) > 1 and sys.argv[1] == "--startup":
    run_as_admin()

def load_api_key():
    logging.info("Loading API key...")
    
    # Try to load from secure storage
    config_file = os.path.join(get_app_data_dir(), 'config.json')
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                encrypted_key = config.get('api_key')
                if encrypted_key:
                    api_key = decrypt_api_key(encrypted_key)
                    if api_key:
                        logging.info("API key loaded from secure storage")
                        return api_key
        except Exception as e:
            logging.warning(f"Error loading stored API key: {str(e)}")
    
    logging.info("No stored API key found, showing input dialog...")
    
    try:
        # Create a simple input dialog
        root = tk.Tk()
        root.title("Word Lookup - API Key Required")
        
        # Set window properties
        root.attributes('-topmost', True)
        root.geometry("400x300")
        
        # Center the window
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        logging.info("Created main window")
        
        # Variables
        api_key_var = tk.StringVar()
        result = [None]  # Using list to store result from inner function
        
        # Create widgets
        tk.Label(
            root,
            text="Please enter your Gemini API Key:",
            font=("Segoe UI", 12)
        ).pack(pady=20)
        
        entry = tk.Entry(root, textvariable=api_key_var, width=40)
        entry.pack(pady=10)
        
        def validate_and_save():
            key = api_key_var.get().strip()
            if not key:
                tkinter.messagebox.showerror("Error", "Please enter an API key")
                return
                
            logging.info("Validating API key...")
            try:
                # Test the API key
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={key}"
                response = requests.post(url, json={
                    "contents": [{"parts": [{"text": "test"}]}]
                })
                response.raise_for_status()
                
                # If successful, encrypt and save the key
                encrypted_key = encrypt_api_key(key)
                os.makedirs(os.path.dirname(config_file), exist_ok=True)
                with open(config_file, 'w') as f:
                    json.dump({'api_key': encrypted_key}, f)
                
                result[0] = key
                root.quit()
                
            except Exception as e:
                error_msg = str(e)
                logging.error(f"API key validation failed: {error_msg}")
                tkinter.messagebox.showerror(
                    "Invalid API Key",
                    f"The API key appears to be invalid:\n{error_msg}\nPlease check and try again."
                )
        
        def open_api_page():
            os.system('start https://makersuite.google.com/app/apikey')
        
        # Buttons
        tk.Button(
            root,
            text="Get API Key",
            command=open_api_page,
            font=("Segoe UI", 10)
        ).pack(pady=10)
        
        tk.Button(
            root,
            text="Save",
            command=validate_and_save,
            font=("Segoe UI", 10, "bold")
        ).pack(pady=10)
        
        # Prevent window from being closed
        def on_closing():
            if tkinter.messagebox.askokcancel("Quit", "API key is required to run the application. Do you want to quit?"):
                root.quit()
        
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        logging.info("Showing dialog...")
        root.mainloop()
        logging.info("Dialog closed")
        
        try:
            root.destroy()
        except:
            pass
        
        if not result[0]:
            logging.error("No API key provided")
            raise ValueError("No API key provided")
        
        return result[0]
        
    except Exception as e:
        logging.error(f"Error showing API key dialog: {str(e)}")
        # Fallback to command line input if GUI fails
        logging.info("Attempting fallback to command line input...")
        print("\nFailed to show GUI dialog. Please enter your Gemini API key:")
        key = input("API Key: ").strip()
        if key:
            try:
                encrypted_key = encrypt_api_key(key)
                os.makedirs(os.path.dirname(config_file), exist_ok=True)
                with open(config_file, 'w') as f:
                    json.dump({'api_key': encrypted_key}, f)
                return key
            except Exception as e2:
                logging.error(f"Error saving API key from command line: {str(e2)}")
                raise ValueError("Failed to save API key")
        raise ValueError("No API key provided")

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
last_processed_text = ""  # Track last processed text globally

def get_meaning_and_synonyms_from_gemini(phrase):
    logging.debug(f"Getting meaning for phrase: {phrase}")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={api_key}"
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
        self.configure(bg="#001d35")  # Updated to the specified dark blue
        
        # Initialize timer_id first
        self.timer_id = None
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Create main frame
        main_frame = tk.Frame(self, bg="#001d35", cursor="hand2")
        main_frame.pack(expand=True, fill='both', padx=2, pady=2)
        
        # Add close button
        close_button = tk.Button(main_frame, text='×', command=self.destroy,
                               bg='#001d35', fg='white', font=('Arial', 12, 'bold'),
                               relief='flat', padx=5, pady=0)
        close_button.pack(side='top', anchor='ne')
        
        text = f"{phrase}:\n\nMeaning:\n{meaning}\n\nSynonyms:\n{synonyms}"
        
        # Add main content
        label = tk.Label(main_frame, text=text, bg="#001d35", fg="white",
                        font=("Segoe UI", 10), justify="left",
                        relief="solid", borderwidth=1, padx=10, pady=5)
        label.pack(expand=True, fill='both', padx=5, pady=5)
        
        # Bind drag events
        main_frame.bind('<Button-1>', self._start_drag)
        main_frame.bind('<B1-Motion>', self._on_drag)
        
        # Bind hover events
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        
        # Store duration
        self.duration = duration
        
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
    global last_processed_text
    while True:  # Changed from while monitoring to while True for continuous running
        time.sleep(0.3)
        
        if not monitoring:
            # When disabled, just update the last processed text without showing popup
            last_processed_text = pyperclip.paste().strip()
            continue

        try:
            current_text = pyperclip.paste().strip()
            valid_phrase = is_valid_phrase(current_text)

            # Only process if it's a valid phrase and different from last processed
            if valid_phrase and valid_phrase != last_processed_text:
                last_processed_text = valid_phrase
                meaning, synonyms = get_meaning_and_synonyms_from_gemini(valid_phrase)
                show_popup(valid_phrase, meaning, synonyms)
        except Exception as e:
            logging.error(f"Error in clipboard monitor: {str(e)}")

def handle_startup_action():
    """Handle pending startup actions after getting admin rights"""
    action_file = os.path.join(get_app_data_dir(), 'startup_action.txt')
    if os.path.exists(action_file):
        try:
            with open(action_file, 'r') as f:
                action = f.read().strip()
            
            # Delete the file before performing the action to prevent loops
            try:
                os.remove(action_file)
            except Exception as e:
                logging.error(f"Failed to delete action file: {e}")
            
            if action == 'add':
                logging.info("Executing add to startup action")
                return add_to_startup()
            elif action == 'remove':
                logging.info("Executing remove from startup action")
                return remove_from_startup()
            else:
                logging.error(f"Unknown startup action: {action}")
                return False
        except Exception as e:
            logging.error(f"Error handling startup action: {e}")
            return False
    return None

def add_to_startup():
    # First check if we're already in startup
    if is_in_startup():
        logging.info("Application is already in startup")
        return True
        
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"  # Changed to uppercase SOFTWARE
    app_name = "Word Lookup"
    
    try:
        # Get the path of the executable
        if getattr(sys, 'frozen', False):
            app_path = sys.executable
        else:
            app_path = os.path.abspath(__file__)
            
        logging.info(f"Adding to startup with path: {app_path}")
            
        # Check if we need admin rights
        if not is_admin():
            logging.info("Requesting admin rights for startup modification...")
            # Store the action in a temp file
            action_file = os.path.join(get_app_data_dir(), 'startup_action.txt')
            with open(action_file, 'w') as f:
                f.write('add')
            
            # Request admin rights
            if run_as_admin():
                return None  # Return None to indicate pending admin action
            else:
                raise Exception("Failed to get admin rights")

        # Try to add to CURRENT_USER first
        try:
            key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, 
                                   winreg.KEY_WRITE | winreg.KEY_READ)
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
            winreg.CloseKey(key)
            logging.info("Successfully added to CURRENT_USER")
            return True
                
        except Exception as current_user_error:
            logging.warning(f"Failed to add to CURRENT_USER: {current_user_error}")
            
            # Try LOCAL_MACHINE if CURRENT_USER fails
            try:
                key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, key_path, 0, 
                                       winreg.KEY_WRITE | winreg.KEY_READ)
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
                winreg.CloseKey(key)
                logging.info("Successfully added to LOCAL_MACHINE")
                return True
                    
            except Exception as local_machine_error:
                raise Exception(f"Failed to add to both registry locations. CURRENT_USER: {current_user_error}, LOCAL_MACHINE: {local_machine_error}")
            
    except Exception as e:
        logging.error(f"Error adding to startup: {e}")
        return False

def remove_from_startup():
    # First check if we're actually in startup
    if not is_in_startup():
        logging.info("Application is not in startup, no need to remove")
        return True
        
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"  # Changed to uppercase SOFTWARE
    app_name = "Word Lookup"
    
    try:
        # Check if we need admin rights
        if not is_admin():
            logging.info("Requesting admin rights for startup modification...")
            # Store the action in a temp file
            action_file = os.path.join(get_app_data_dir(), 'startup_action.txt')
            with open(action_file, 'w') as f:
                f.write('remove')
            
            # Request admin rights
            if run_as_admin():
                return None  # Return None to indicate pending admin action
            else:
                raise Exception("Failed to get admin rights")
        
        success = False
        errors = []
        
        # Try CURRENT_USER
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_SET_VALUE | winreg.KEY_READ)
            winreg.DeleteValue(key, app_name)
            winreg.CloseKey(key)
            success = True
            logging.info("Successfully removed from CURRENT_USER")
        except Exception as e:
            errors.append(f"CURRENT_USER: {str(e)}")
        
        # Try LOCAL_MACHINE if needed
        if not success:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0,
                                    winreg.KEY_SET_VALUE | winreg.KEY_READ)
                winreg.DeleteValue(key, app_name)
                winreg.CloseKey(key)
                success = True
                logging.info("Successfully removed from LOCAL_MACHINE")
            except Exception as e:
                errors.append(f"LOCAL_MACHINE: {str(e)}")
        
        if success:
            return True
        else:
            raise Exception(f"Failed to remove from both registry locations: {'; '.join(errors)}")
            
    except Exception as e:
        logging.error(f"Error removing from startup: {e}")
        return False

def is_in_startup():
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"  # Changed to uppercase SOFTWARE
    app_name = "Word Lookup"
    
    try:
        # Try CURRENT_USER first
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, app_name)
            winreg.CloseKey(key)
            return True
        except:
            # Try LOCAL_MACHINE if CURRENT_USER fails
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ)
                value, _ = winreg.QueryValueEx(key, app_name)
                winreg.CloseKey(key)
                return True
            except:
                return False
    except:
        return False

def on_startup_toggle(icon, item):
    current_state = is_in_startup()
    if current_state:  # If it's in startup, remove it
        result = remove_from_startup()
        if result is None:
            msg = "Please approve admin rights to remove from startup"
        else:
            msg = "Removed from startup" if result else "Failed to remove from startup"
    else:  # If it's not in startup, add it
        result = add_to_startup()
        if result is None:
            msg = "Please approve admin rights to add to startup"
        else:
            msg = "Added to startup" if result else "Failed to add to startup"
    
    # Update menu item state
    item.checked = is_in_startup()
    logging.info(msg)
    icon.notify("Word Lookup", msg)

# Modify the create_system_tray function to include startup options
# Add this at the top of your file with other imports
import os
import sys

# Modify the create_system_tray function
def create_system_tray():
    logging.info("Creating system tray icon...")
    try:
        # Clean up any existing system tray icon
        global icon
        if 'icon' in globals() and icon is not None:
            try:
                icon.stop()
            except:
                pass
            # Global variable for system tray icon
            icon = None
        
        # Get the correct path whether running as script or executable
        icon_path = None
        if getattr(sys, 'frozen', False):
            # If running as exe (PyInstaller)
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")
        else:
            # If running as script
            base_path = os.path.abspath(".")

        # Try multiple possible locations for the icon
        possible_paths = [
            os.path.join(base_path, "app_icon.ico"),
            "app_icon.ico",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico"),
            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "app_icon.ico")
        ]

        for path in possible_paths:
            if os.path.exists(path):
                icon_path = path
                logging.info(f"Found icon at: {icon_path}")
                break

        if not icon_path:
            logging.error("Icon file not found in any location")
            # Create a default icon as fallback
            img = Image.new('RGBA', (64, 64), color='blue')
            icon_path = os.path.join(get_app_data_dir(), 'default_icon.ico')
            img.save(icon_path, format='ICO')
            logging.info("Created default icon as fallback")

        # Load the icon
        try:
            image = Image.open(icon_path)
            logging.info("System tray icon loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load icon: {str(e)}")
            return None

        def on_exit(icon, item):
            global monitoring
            monitoring = False
            icon.stop()
            logging.info("Application exiting...")

        def on_toggle(icon, item):
            global monitoring, last_processed_text
            monitoring = not monitoring
            if monitoring:
                # Reset last processed text when enabling
                last_processed_text = pyperclip.paste().strip()
                logging.info("Monitoring enabled")
                icon.notify("Word Lookup", "Word lookup is now enabled")
            else:
                logging.info("Monitoring disabled")
                icon.notify("Word Lookup", "Word lookup is now disabled")

        def on_startup_toggle(icon, item):
            current_state = is_in_startup()
            if current_state:  # If it's in startup, remove it
                result = remove_from_startup()
                if result is None:
                    msg = "Please approve admin rights to remove from startup"
                else:
                    msg = "Removed from startup" if result else "Failed to remove from startup"
            else:  # If it's not in startup, add it
                result = add_to_startup()
                if result is None:
                    msg = "Please approve admin rights to add to startup"
                else:
                    msg = "Added to startup" if result else "Failed to add to startup"
            
            # Update menu item state
            item.checked = is_in_startup()
            logging.info(msg)
            icon.notify("Word Lookup", msg)

        # Create the system tray menu with startup option
        startup_state = is_in_startup()
        logging.info(f"Current startup state: {'Enabled' if startup_state else 'Disabled'}")
        
        menu = (
            pystray.MenuItem("Enable/Disable", on_toggle, default=True),
            pystray.MenuItem(
                "Run at Startup",
                on_startup_toggle,
                checked=lambda _: is_in_startup()  # Dynamic check of startup state
            ),
            pystray.MenuItem("Exit", on_exit)
        )

        icon = pystray.Icon("Word Lookup", image, "Word Lookup", menu)
        logging.info("System tray icon created")

        # Show notification that app is running
        def show_startup_notification():
            time.sleep(2)  # Wait for icon to be ready
            icon.notify("Word Lookup", "Application is running in system tray")

        threading.Thread(target=show_startup_notification, daemon=True).start()

        return icon
    except Exception as e:
        logging.error(f"Error creating system tray: {str(e)}")
        return None

if __name__ == "__main__":
    logging.info("Application main entry point")
    try:
        # Check if we're handling a startup action
        if len(sys.argv) > 1 and sys.argv[1] == "--startup":
            logging.info("Handling startup action...")
            result = handle_startup_action()
            if result is True:
                # Show success message and exit
                root = tk.Tk()
                root.withdraw()  # Hide the main window
                tkinter.messagebox.showinfo("Success", "Startup settings updated successfully!")
                root.destroy()
                sys.exit(0)
            elif result is False:
                # Show error message and exit
                root = tk.Tk()
                root.withdraw()  # Hide the main window
                tkinter.messagebox.showerror("Error", "Failed to update startup settings. Please try again.")
                root.destroy()
                sys.exit(1)
            sys.exit(0)

        # Create and run system tray
        icon = create_system_tray()
        if icon:
            # Start clipboard monitor thread
            monitor_thread = threading.Thread(target=clipboard_monitor, daemon=True)
            monitor_thread.start()
            
            # Run the icon
            icon.run()
        else:
            logging.error("Failed to create system tray icon")
            sys.exit(1)
            
    except Exception as e:
        logging.error(f"Error in main: {str(e)}")
        sys.exit(1)
