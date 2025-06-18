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
            if getattr(sys, 'frozen', False):
                app_path = sys.executable
            else:
                app_path = os.path.abspath(__file__)
            
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
            
            if result <= 32:
                raise Exception(f"Failed to get admin rights. Error code: {result}")
                
            return True
        except Exception as e:
            logging.error(f"Error requesting admin rights: {e}")
            return False
    return True

def get_app_data_dir():
    app_data = os.path.join(os.getenv('APPDATA'), 'Word Lookup')
    os.makedirs(app_data, exist_ok=True)
    return app_data

def get_encryption_key():
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
    f = Fernet(get_encryption_key())
    return f.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_key):
    try:
        f = Fernet(get_encryption_key())
        return f.decrypt(encrypted_key.encode()).decode()
    except:
        return None

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

logging.info("Starting application...")
load_dotenv()

if len(sys.argv) > 1 and sys.argv[1] == "--startup":
    run_as_admin()

def load_api_key():
    logging.info("Loading API key...")
    
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
        root = tk.Tk()
        root.title("Word Lookup - API Key Required")
        
        root.attributes('-topmost', True)
        root.geometry("400x350")
        
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.abspath(".")
            icon_path = os.path.join(base_path, "app_icon.ico")
            root.iconbitmap(icon_path)
        except:
            pass
        
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        root.grid_columnconfigure(0, weight=1)
        
        bg_color = "#ffffff"
        accent_color = "#1a73e8"
        text_color = "#202124"
        
        root.configure(bg=bg_color)
        
        main_frame = tk.Frame(root, bg=bg_color)
        main_frame.grid(row=0, column=0, padx=30, pady=20, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1)
        
        title_label = tk.Label(
            main_frame,
            text="Please enter your Gemini API Key",
            font=("Segoe UI", 14, "bold"),
            bg=bg_color,
            fg=text_color
        )
        title_label.grid(row=0, column=0, pady=(0, 20), sticky="w")
        
        entry_frame = tk.Frame(main_frame, bg=bg_color, highlightthickness=1, 
                             highlightbackground="#dadce0", highlightcolor=accent_color)
        entry_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        entry_frame.grid_columnconfigure(0, weight=1)
        
        api_key_var = tk.StringVar()
        entry = tk.Entry(
            entry_frame,
            textvariable=api_key_var,
            font=("Segoe UI", 11),
            bd=0,
            bg=bg_color
        )
        entry.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        
        def validate_and_save():
            key = api_key_var.get().strip()
            if not key:
                tkinter.messagebox.showerror(
                    "Error",
                    "Please enter an API key",
                    parent=root
                )
                return
                
            logging.info("Validating API key...")
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={key}"
                response = requests.post(url, json={
                    "contents": [{"parts": [{"text": "test"}]}]
                })
                response.raise_for_status()
                
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
                    f"The API key appears to be invalid:\n{error_msg}\nPlease check and try again.",
                    parent=root
                )
        
        def open_api_page():
            os.system('start https://makersuite.google.com/app/apikey')
        
        get_key_button = tk.Button(
            main_frame,
            text="Get API Key",
            command=open_api_page,
            font=("Segoe UI", 11),
            bg=bg_color,
            fg=accent_color,
            bd=1,
            relief="solid",
            cursor="hand2",
            padx=15
        )
        get_key_button.grid(row=2, column=0, pady=(0, 15), sticky="ew")
        
        def on_enter(e):
            e.widget['background'] = '#f8f9fa'
        
        def on_leave(e):
            e.widget['background'] = bg_color
            
        get_key_button.bind("<Enter>", on_enter)
        get_key_button.bind("<Leave>", on_leave)
        
        save_button = tk.Button(
            main_frame,
            text="Save",
            command=validate_and_save,
            font=("Segoe UI", 11, "bold"),
            bg=accent_color,
            fg="white",
            bd=0,
            cursor="hand2",
            padx=15
        )
        save_button.grid(row=3, column=0, pady=(0, 10), sticky="ew")
        
        def on_enter_save(e):
            e.widget['background'] = '#1557b0'
        
        def on_leave_save(e):
            e.widget['background'] = accent_color
            
        save_button.bind("<Enter>", on_enter_save)
        save_button.bind("<Leave>", on_leave_save)
        
        helper_text = tk.Label(
            main_frame,
            text="You can get your API key from Google's Makersuite.\nClick 'Get API Key' to open the page.",
            font=("Segoe UI", 9),
            bg=bg_color,
            fg="#5f6368",
            justify="left"
        )
        helper_text.grid(row=4, column=0, pady=(10, 0), sticky="w")
        
        result = [None]
        
        def on_closing():
            if tkinter.messagebox.askokcancel(
                "Quit",
                "API key is required to run the application. Do you want to quit?",
                parent=root
            ):
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

try:
    api_key = load_api_key()
except Exception as e:
    logging.error(f"Failed to load API key: {str(e)}")
    sys.exit(1)

if not api_key:
    logging.error("GEMINI_API_KEY not found in environment variables.")
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please check your .env file.")

monitoring = True
last_processed_text = ""

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

def get_mouse_pos():
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

class Popup(tk.Tk):
    def __init__(self, phrase, meaning, synonyms, x, y, duration=5000):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#001d35")
        
        self.timer_id = None
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        main_frame = tk.Frame(self, bg="#001d35", cursor="hand2")
        main_frame.pack(expand=True, fill='both', padx=2, pady=2)
        
        close_button = tk.Button(main_frame, text='×', command=self.destroy,
                               bg='#001d35', fg='white', font=('Arial', 12, 'bold'),
                               relief='flat', padx=5, pady=0)
        close_button.pack(side='top', anchor='ne')
        
        text = f"{phrase}:\n\nMeaning:\n{meaning}\n\nSynonyms:\n{synonyms}"
        
        label = tk.Label(main_frame, text=text, bg="#001d35", fg="white",
                        font=("Segoe UI", 10), justify="left",
                        relief="solid", borderwidth=1, padx=10, pady=5)
        label.pack(expand=True, fill='both', padx=5, pady=5)
        
        main_frame.bind('<Button-1>', self._start_drag)
        main_frame.bind('<B1-Motion>', self._on_drag)
        
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        
        self.duration = duration
        
        self._drag_data = {"x": 0, "y": 0}
        
        self.update_idletasks()
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        
        x = min(max(x, 0), screen_width - window_width)
        y = min(max(y, 0), screen_height - window_height)
        
        self.geometry(f"+{x}+{y}")
        self._start_timer()
    
    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def _on_drag(self, event):
        x = self.winfo_x() + (event.x - self._drag_data["x"])
        y = self.winfo_y() + (event.y - self._drag_data["y"])
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        x = min(max(x, 0), screen_width - self.winfo_width())
        y = min(max(y, 0), screen_height - self.winfo_height())
        
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

def is_valid_phrase(text):
    text = re.sub(r'\s+', ' ', text.strip())
    if 1 <= len(text.split()) <= 3 and re.fullmatch(r'[A-Za-z ]+', text):
        return text
    return None

def clipboard_monitor():
    global last_processed_text
    while True:
        time.sleep(0.3)
        
        if not monitoring:
            last_processed_text = pyperclip.paste().strip()
            continue

        try:
            current_text = pyperclip.paste().strip()
            valid_phrase = is_valid_phrase(current_text)

            if valid_phrase and valid_phrase != last_processed_text:
                last_processed_text = valid_phrase
                meaning, synonyms = get_meaning_and_synonyms_from_gemini(valid_phrase)
                show_popup(valid_phrase, meaning, synonyms)
        except Exception as e:
            logging.error(f"Error in clipboard monitor: {str(e)}")

def handle_startup_action():
    action_file = os.path.join(get_app_data_dir(), 'startup_action.txt')
    if os.path.exists(action_file):
        try:
            with open(action_file, 'r') as f:
                action = f.read().strip()
            
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
    if is_in_startup():
        logging.info("Application is already in startup")
        return True
        
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    app_name = "Word Lookup"
    
    try:
        if getattr(sys, 'frozen', False):
            app_path = sys.executable
        else:
            app_path = os.path.abspath(__file__)
            
        logging.info(f"Adding to startup with path: {app_path}")
            
        if not is_admin():
            logging.info("Requesting admin rights for startup modification...")
            action_file = os.path.join(get_app_data_dir(), 'startup_action.txt')
            with open(action_file, 'w') as f:
                f.write('add')
            
            if run_as_admin():
                return None
            else:
                raise Exception("Failed to get admin rights")

        try:
            key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, 
                                   winreg.KEY_WRITE | winreg.KEY_READ)
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
            winreg.CloseKey(key)
            logging.info("Successfully added to CURRENT_USER")
            return True
                
        except Exception as current_user_error:
            logging.warning(f"Failed to add to CURRENT_USER: {current_user_error}")
            
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
    if not is_in_startup():
        logging.info("Application is not in startup, no need to remove")
        return True
        
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    app_name = "Word Lookup"
    
    try:
        if not is_admin():
            logging.info("Requesting admin rights for startup modification...")
            action_file = os.path.join(get_app_data_dir(), 'startup_action.txt')
            with open(action_file, 'w') as f:
                f.write('remove')
            
            if run_as_admin():
                return None
            else:
                raise Exception("Failed to get admin rights")
        
        success = False
        errors = []
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_SET_VALUE | winreg.KEY_READ)
            winreg.DeleteValue(key, app_name)
            winreg.CloseKey(key)
            success = True
            logging.info("Successfully removed from CURRENT_USER")
        except Exception as e:
            errors.append(f"CURRENT_USER: {str(e)}")
        
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
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    app_name = "Word Lookup"
    
    try:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, app_name)
            winreg.CloseKey(key)
            return True
        except:
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
    if current_state:
        result = remove_from_startup()
        if result is None:
            msg = "Please approve admin rights to remove from startup"
        else:
            msg = "Removed from startup" if result else "Failed to remove from startup"
    else:
        result = add_to_startup()
        if result is None:
            msg = "Please approve admin rights to add to startup"
        else:
            msg = "Added to startup" if result else "Failed to add to startup"
    
    item.checked = is_in_startup()
    logging.info(msg)
    icon.notify("Word Lookup", msg)

import os
import sys

def create_system_tray():
    logging.info("Creating system tray icon...")
    try:
        global icon
        if 'icon' in globals() and icon is not None:
            try:
                icon.stop()
            except:
                pass
            icon = None
        
        icon_path = None
        if getattr(sys, 'frozen', False):
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")
        else:
            base_path = os.path.abspath(".")

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
            img = Image.new('RGBA', (64, 64), color='blue')
            icon_path = os.path.join(get_app_data_dir(), 'default_icon.ico')
            img.save(icon_path, format='ICO')
            logging.info("Created default icon as fallback")

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
                last_processed_text = pyperclip.paste().strip()
                logging.info("Monitoring enabled")
                icon.notify("Word Lookup", "Word lookup is now enabled")
            else:
                logging.info("Monitoring disabled")
                icon.notify("Word Lookup", "Word lookup is now disabled")

        def on_startup_toggle(icon, item):
            current_state = is_in_startup()
            if current_state:
                result = remove_from_startup()
                if result is None:
                    msg = "Please approve admin rights to remove from startup"
                else:
                    msg = "Removed from startup" if result else "Failed to remove from startup"
            else:
                result = add_to_startup()
                if result is None:
                    msg = "Please approve admin rights to add to startup"
                else:
                    msg = "Added to startup" if result else "Failed to add to startup"
            
            item.checked = is_in_startup()
            logging.info(msg)
            icon.notify("Word Lookup", msg)

        startup_state = is_in_startup()
        logging.info(f"Current startup state: {'Enabled' if startup_state else 'Disabled'}")
        
        menu = (
            pystray.MenuItem("Enable/Disable", on_toggle, default=True),
            pystray.MenuItem(
                "Run at Startup",
                on_startup_toggle,
                checked=lambda _: is_in_startup()
            ),
            pystray.MenuItem("Exit", on_exit)
        )

        icon = pystray.Icon("Word Lookup", image, "Word Lookup", menu)
        logging.info("System tray icon created")

        def show_startup_notification():
            time.sleep(2)
            icon.notify("Word Lookup", "Application is running in system tray")

        threading.Thread(target=show_startup_notification, daemon=True).start()

        return icon
    except Exception as e:
        logging.error(f"Error creating system tray: {str(e)}")
        return None

if __name__ == "__main__":
    logging.info("Application main entry point")
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--startup":
            logging.info("Handling startup action...")
            result = handle_startup_action()
            if result is True:
                root = tk.Tk()
                root.withdraw()
                tkinter.messagebox.showinfo("Success", "Startup settings updated successfully!")
                root.destroy()
                sys.exit(0)
            elif result is False:
                root = tk.Tk()
                root.withdraw()
                tkinter.messagebox.showerror("Error", "Failed to update startup settings. Please try again.")
                root.destroy()
                sys.exit(1)
            sys.exit(0)

        icon = create_system_tray()
        if icon:
            monitor_thread = threading.Thread(target=clipboard_monitor, daemon=True)
            monitor_thread.start()
            
            icon.run()
        else:
            logging.error("Failed to create system tray icon")
            sys.exit(1)
            
    except Exception as e:
        logging.error(f"Error in main: {str(e)}")
        sys.exit(1)
