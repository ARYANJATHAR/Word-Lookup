import pyperclip
import time
import tkinter as tk
import threading
import ctypes
import re
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
api_key = os.getenv('GEMINI_API_KEY')

# Add error handling for missing API key
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please check your .env file.")

def get_meaning_and_synonyms_from_gemini(phrase):
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
    print("📋 Clipboard monitor running... Copy up to 3 words to see AI meaning + synonyms popup.")

    while True:
        time.sleep(0.3)

        current_text = pyperclip.paste().strip()
        valid_phrase = is_valid_phrase(current_text)

        if valid_phrase and valid_phrase != last_text:
            last_text = valid_phrase
            print(f"\n🔍 Text copied: {valid_phrase}")

            meaning, synonyms = get_meaning_and_synonyms_from_gemini(valid_phrase)
            print(f"📘 Meaning: {meaning}")
            print(f"🔗 Synonyms: {synonyms}")

            show_popup(valid_phrase, meaning, synonyms)

if __name__ == "__main__":
    clipboard_monitor()
