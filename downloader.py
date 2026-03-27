import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import yt_dlp # type: ignore
import sys
import queue
import io
import requests # type: ignore
import re
import os
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from PIL import Image, ImageTk # type: ignore
from download_log import DownloadLog # type: ignore

class MyLogger(object):
    def __init__(self, log_queue, ui_queue_cb):
        self.log_queue = log_queue
        self.ui_queue_cb = ui_queue_cb

    def debug(self, msg):
        # yt-dlp sends both info and debug to debug()
        if not msg.startswith('[download]') and not msg.startswith('[youtube]'):
             self.log_queue.put(msg)
        else:
             self.log_queue.put(msg)

    def warning(self, msg):
        self.log_queue.put(msg)
        
    def error(self, msg):
        self.log_queue.put(msg)

# Obsolete thread deleted

from queue_manager import QueueManager # type: ignore
from tkinter import ttk

SEARCH_API_PORT = 5005

class SearchAPIHandler(BaseHTTPRequestHandler):
    """Lightweight HTTP server that lets the browser extension query local MP3s."""
    log_queue = None
    downloaded_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloaded')

    def log_message(self, format, *args):
        if self.log_queue:
            msg = f"{self.address_string()} - [{self.log_date_time_string()}] {format%args}\n"
            self.log_queue.put(msg)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        q = params.get('q', [''])[0].strip().lower()

        try:
            files = os.listdir(self.downloaded_dir)
        except FileNotFoundError:
            files = []

        if q:
            # Strip symbols and convert to words
            clean_q = re.sub(r'[^a-zA-Z0-9\s]', ' ', q)
            stop_words = {'the', 'a', 'and', 'of', 'in', 'on', 'for', 'with', 'official', 'video', 'music', 'audio', 'lyric', 'lyrics'}
            words = set(w for w in clean_q.split() if w not in stop_words and len(w) > 1)
            
            scored = []
            for f in files:
                if not f.lower().endswith('.mp3'): continue
                raw_name = os.path.splitext(f)[0]
                clean_f = re.sub(r'[^a-zA-Z0-9\s]', ' ', raw_name.lower())
                
                # Calculate match score (how many words from query exist in filename)
                score = sum(1 for w in words if w in clean_f)
                
                # Require at least 50% of the meaningful query words to match the filename
                if len(words) > 0 and (score / len(words)) >= 0.5:
                    scored.append((score, raw_name))
            
            # Sort by highest score first
            scored.sort(key=lambda x: x[0], reverse=True)
            results = [r[1] for r in scored]
        else:
            results = [os.path.splitext(f)[0] for f in files if f.lower().endswith('.mp3')]

        body = json.dumps(results).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def start_search_api():
    class ReusableServer(HTTPServer):
        allow_reuse_address = True
        
    try:
        server = ReusableServer(('localhost', SEARCH_API_PORT), SearchAPIHandler)
        server.serve_forever()
    except Exception as e:
        if SearchAPIHandler.log_queue:
            SearchAPIHandler.log_queue.put(f"CRITICAL ERROR: Search API Server crashed: {e}\n")
        print("Search API Error:", e)

DOWNLOADED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloaded')

def _fmt_size(byte_size: int) -> str:
    """Human-readable file size."""
    if byte_size <= 0:
        return '-'
    for unit in ('B', 'KB', 'MB', 'GB'):
        if byte_size < 1024:
            return f"{byte_size:.1f} {unit}"
        byte_size /= 1024
    return f"{byte_size:.1f} TB"

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube to MP3 Downloader Pro")
        self.root.geometry("800x560")
        self.root.configure(bg="#f0f2f5")

        self.log = DownloadLog()
        
        # Initialize queue manager with history callback
        self.qm = QueueManager(self._on_queue_update, history_update_cb=self._schedule_history_refresh)
        
        # UI Setup
        top_frame = tk.Frame(root, padx=20, pady=15, bg="#f0f2f5")
        top_frame.pack(fill='x')
        
        tk.Label(top_frame, text="YouTube URL:", font=("Segoe UI", 11), bg="#f0f2f5").pack(side='left')
        self.url_entry = tk.Entry(top_frame, font=("Segoe UI", 12), relief=tk.FLAT, bd=5)
        self.url_entry.pack(side='left', fill='x', expand=True, padx=10, ipady=3)
        self.add_btn = tk.Button(top_frame, text="Add to Queue", command=self.add_url, 
                                 font=("Segoe UI", 11, "bold"), bg="#2a75d3", fg="white",
                                 activebackground="#1e5ba6", relief=tk.FLAT, cursor="hand2", padx=15)
        self.add_btn.pack(side='left')

        # Preview Box
        self.preview_frame = tk.Frame(root, padx=20, pady=0, bg="#f0f2f5")
        self.preview_frame.pack(fill='x')
        
        self.preview_img_lbl = tk.Label(self.preview_frame, bg="#f0f2f5")
        self.preview_img_lbl.pack(side='left', padx=(0, 10))
        
        self.preview_title_lbl = tk.Label(self.preview_frame, text="", font=("Segoe UI", 10, "italic"), bg="#f0f2f5", fg="#555555", wraplength=550, justify='left')
        self.preview_title_lbl.pack(side='left', fill='x', expand=True)
        
        self.current_preview_url = ""
        self.preview_debounce_timer = None
        self.preview_image_ref = None

        self.url_entry.bind('<KeyRelease>', self.on_url_change)
        self.url_entry.bind('<<Paste>>', lambda e: self.root.after(50, self.on_url_change))


        # Control Buttons Frame
        ctrl_frame = tk.Frame(root, padx=20, pady=5, bg="#f0f2f5")
        ctrl_frame.pack(fill='x')
        
        self.pause_btn = tk.Button(ctrl_frame, text="Pause Queue", command=self.toggle_pause,
                                  font=("Segoe UI", 10), bg="#ff9900", fg="white", relief=tk.FLAT, cursor="hand2")
        self.pause_btn.pack(side='left', padx=(0, 5))
        
        tk.Button(ctrl_frame, text="Cancel Selected", command=self.cancel_selected,
                  font=("Segoe UI", 10), bg="#ff3333", fg="white", relief=tk.FLAT, cursor="hand2").pack(side='left', padx=5)
                  
        tk.Button(ctrl_frame, text="Download Next", command=self.prioritize_selected,
                  font=("Segoe UI", 10), bg="#33cc33", fg="white", relief=tk.FLAT, cursor="hand2").pack(side='left', padx=5)

        self.show_logs_var = tk.BooleanVar(value=False)
        self.logs_cb = tk.Checkbutton(ctrl_frame, text="Show API Logs", variable=self.show_logs_var, command=self.toggle_log_window,
                                      font=("Segoe UI", 10), bg="#f0f2f5")
        self.logs_cb.pack(side='right', padx=10)

        # API Logs Window reference
        self.log_window = None
        self.log_text = None
        self.api_log_queue = queue.Queue()
        SearchAPIHandler.log_queue = self.api_log_queue
        
        self.root.after(100, self._poll_api_logs)

        tk.Button(ctrl_frame, text="📂 Open File", command=self._open_active_tab_in_explorer,
                  font=("Segoe UI", 10), bg="#555555", fg="white", relief=tk.FLAT, cursor="hand2").pack(side='left', padx=5)

        # --- Notebook (tabs) ---
        notebook_frame = tk.Frame(root, padx=20, pady=10, bg="#f0f2f5")
        notebook_frame.pack(fill='both', expand=True)

        self.notebook = ttk.Notebook(notebook_frame)
        self.notebook.pack(fill='both', expand=True)

        # --- Tab 1: Queue ---
        queue_tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(queue_tab, text="  Queue  ")

        columns = ("id", "title", "status", "progress", "eta")
        self.tree = ttk.Treeview(queue_tab, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="#")
        self.tree.column("id", width=40, anchor='center')
        
        self.tree.heading("title", text="Title/URL")
        self.tree.column("title", width=320, anchor='w')
        
        self.tree.heading("status", text="Status")
        self.tree.column("status", width=100, anchor='center')
        
        self.tree.heading("progress", text="Progress")
        self.tree.column("progress", width=120, anchor='center')
        
        self.tree.heading("eta", text="ETA")
        self.tree.column("eta", width=80, anchor='center')
        
        scrollbar_q = ttk.Scrollbar(queue_tab, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar_q.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar_q.pack(side='right', fill='y')

        # --- Tab 2: Downloaded ---
        history_tab = tk.Frame(self.notebook, bg="#f0f2f5")
        self.notebook.add(history_tab, text="  Downloaded  ")

        hist_cols = ("id", "title", "size", "date")
        self.hist_tree = ttk.Treeview(history_tab, columns=hist_cols, show="headings", selectmode="browse")

        self.hist_tree.heading("id", text="#")
        self.hist_tree.column("id", width=40, anchor='center')

        self.hist_tree.heading("title", text="YouTube Title")
        self.hist_tree.column("title", width=340, anchor='w')

        self.hist_tree.heading("size", text="Size")
        self.hist_tree.column("size", width=90, anchor='center')

        self.hist_tree.heading("date", text="Downloaded At")
        self.hist_tree.column("date", width=150, anchor='center')

        scrollbar_h = ttk.Scrollbar(history_tab, orient=tk.VERTICAL, command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=scrollbar_h.set)

        self.hist_tree.pack(side='left', fill='both', expand=True)
        scrollbar_h.pack(side='right', fill='y')

        # Remove button below history tree
        hist_btn_frame = tk.Frame(history_tab, bg="#f0f2f5")
        hist_btn_frame.pack(fill='x', pady=(4, 0))
        tk.Button(hist_btn_frame, text="Remove from list", command=self._remove_history_entry,
                  font=("Segoe UI", 10), bg="#888888", fg="white", relief=tk.FLAT, cursor="hand2", padx=12).pack(side='right', padx=4)
        tk.Button(hist_btn_frame, text="📂 Open File", command=self._open_history_item_in_explorer,
                  font=("Segoe UI", 10), bg="#555555", fg="white", relief=tk.FLAT, cursor="hand2", padx=12).pack(side='right', padx=4)

        # Map treeview iid → log entry id
        self._hist_iid_to_log_id: dict = {}

        # Load history on startup
        self._refresh_history()

    # ------------------------------------------------------------------ preview
    def on_url_change(self, event=None):
        url = self.url_entry.get().strip()
        
        if url == self.current_preview_url:
            return
            
        self.current_preview_url = url
        
        if self.preview_debounce_timer:
            self.root.after_cancel(self.preview_debounce_timer)
            self.preview_debounce_timer = None
            
        if not url or not re.match(r'^https?://', url):
            self.preview_img_lbl.config(image='')
            self.preview_title_lbl.config(text="")
            return
            
        self.preview_title_lbl.config(text="Loading preview...")
        self.preview_img_lbl.config(image='')
        self.preview_debounce_timer = self.root.after(500, self._start_preview_fetch)

    def _start_preview_fetch(self):
        url = self.current_preview_url
        threading.Thread(target=self._fetch_preview_thread, args=(url,), daemon=True).start()

    def _fetch_preview_thread(self, url):
        ydl_opts = {
            'quiet': True,
            'extract_flat': 'in_playlist',
            'noplaylist': True,
            'skip_download': True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    self.root.after(0, lambda: self._update_preview_ui(url, None, "Could not fetch info"))
                    return
                
                title = info.get('title', 'Unknown Title')
                thumbnails = info.get('thumbnails', [])
                
                img_data = None
                if thumbnails:
                    # Get a reasonably sized thumbnail, but not massive. The last one is usually best quality.
                    thumb_url = thumbnails[-1]['url']
                    try:
                        resp = requests.get(thumb_url, timeout=5)
                        if resp.status_code == 200:
                            img_data = resp.content
                    except Exception:
                        pass
                
                self.root.after(0, lambda: self._update_preview_ui(url, img_data, title))
        except Exception:
            self.root.after(0, lambda: self._update_preview_ui(url, None, "Invalid URL or Video Unavailable"))

    def _update_preview_ui(self, url, img_data, title):
        if url != self.current_preview_url:
            return
            
        self.preview_title_lbl.config(text=title)
        
        if img_data:
            try:
                if not hasattr(Image, 'Resampling'):
                    resample_filter = Image.ANTIALIAS # type: ignore
                else:
                    resample_filter = Image.Resampling.LANCZOS # type: ignore

                image = Image.open(io.BytesIO(img_data))
                image.thumbnail((120, 68), resample_filter)
                photo = ImageTk.PhotoImage(image)
                self.preview_img_lbl.config(image=photo)
                self.preview_image_ref = photo
            except Exception:
                self.preview_img_lbl.config(image='')
        else:
            self.preview_img_lbl.config(image='')

    # ------------------------------------------------------------------ queue actions
    def add_url(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid YouTube link.")
            return
        self.qm.add_url(url)
        self.url_entry.delete(0, tk.END)
        self.on_url_change()

    def toggle_pause(self):
        if self.qm.is_paused:
            self.qm.resume_queue()
            self.pause_btn.config(text="Pause Queue", bg="#ff9900")
        else:
            self.qm.pause_queue()
            self.pause_btn.config(text="Resume Queue", bg="#33cc33")

    def _get_selected_id(self):
        selected = self.tree.selection()
        if not selected:
            return None
        item = self.tree.item(selected[0])
        return item['values'][0]

    def cancel_selected(self):
        item_id = self._get_selected_id()
        if item_id:
            self.qm.cancel_item(item_id)

    def prioritize_selected(self):
        item_id = self._get_selected_id()
        if item_id:
            self.qm.prioritize_item(item_id)

    def _on_queue_update(self, q_list):
        # Update the UI from the thread safely using after()
        self.root.after(0, lambda: self._refresh_table(q_list))
        
    def _refresh_table(self, q_list):
        # Save selection
        selected_id = self._get_selected_id()
        
        self.tree.delete(*self.tree.get_children())
        
        for item in reversed(q_list):
            display_title = item['title'] if item['title'] != 'Fetching...' else item['url']
            
            row_id = self.tree.insert("", tk.END, values=(
                item['id'], 
                display_title, 
                item['status'], 
                item['progress'], 
                item['eta']
            ))
            
            # Restore selection
            if item['id'] == selected_id:
                self.tree.selection_set(row_id)

    def toggle_log_window(self):
        if self.show_logs_var.get():
            if self.log_window is None or not self.log_window.winfo_exists():
                self.log_window = tk.Toplevel(self.root)
                self.log_window.title("API Request Logs")
                self.log_window.geometry("500x300")
                self.log_text = scrolledtext.ScrolledText(self.log_window, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
                self.log_text.pack(fill='both', expand=True, padx=5, pady=5)
                self.log_window.protocol("WM_DELETE_WINDOW", self._on_log_window_close)
                self.log_text.insert(tk.END, "Waiting for browser extension requests...\n")
        else:
            if self.log_window and self.log_window.winfo_exists():
                self.log_window.destroy()
                self.log_window = None
                self.log_text = None

    def _on_log_window_close(self):
        self.show_logs_var.set(False)
        self.toggle_log_window()

    def _poll_api_logs(self):
        while not self.api_log_queue.empty():
            msg = self.api_log_queue.get_nowait()
            if self.log_text and self.log_window and self.log_window.winfo_exists():
                self.log_text.insert(tk.END, msg)
                self.log_text.see(tk.END)
        self.root.after(100, self._poll_api_logs)

    # ------------------------------------------------------------------ history
    def _schedule_history_refresh(self):
        """Called from background thread — schedule on main thread."""
        self.root.after(0, self._refresh_history)

    def _refresh_history(self):
        """Load log entries, cross-check files exist, populate history tab."""
        entries = self.log.get_visible_entries()

        self.hist_tree.delete(*self.hist_tree.get_children())
        self._hist_iid_to_log_id.clear()

        row_num = 1
        for entry in entries:
            filepath = os.path.join(DOWNLOADED_DIR, entry['filename'])
            if not os.path.exists(filepath):
                # File missing on disk — skip
                continue
            logged_size = entry.get('byte_size', 0)
            if logged_size > 0 and os.path.getsize(filepath) != logged_size:
                # File exists but size doesn't match — treat as not found
                continue

            size_str = _fmt_size(entry['byte_size'])
            iid = self.hist_tree.insert("", tk.END, values=(
                row_num,
                entry['youtube_title'],
                size_str,
                entry['downloaded_at'],
            ))
            self._hist_iid_to_log_id[iid] = entry['id']
            row_num += 1

        # Update tab label to show count
        count = len(self._hist_iid_to_log_id)
        self.notebook.tab(1, text=f"  Downloaded ({count})  ")

    def _remove_history_entry(self):
        """Soft-remove selected history entry (is_removed=1, file untouched)."""
        selected = self.hist_tree.selection()
        if not selected:
            messagebox.showinfo("Remove", "Please select an entry to remove.")
            return
        iid = selected[0]
        log_id = self._hist_iid_to_log_id.get(iid)
        if log_id is not None:
            self.log.remove_entry(log_id)
            self._refresh_history()

    # ------------------------------------------------------------------ explorer helpers
    def _open_active_tab_in_explorer(self):
        """Dispatch to the correct handler based on which tab is active."""
        if self.notebook.index(self.notebook.select()) == 1:
            self._open_history_item_in_explorer()
        else:
            self._open_queue_item_in_explorer()

    def _explorer_select(self, filepath: str):
        """Open Explorer with the given file highlighted. Falls back to opening the folder."""
        import subprocess
        if os.path.exists(filepath):
            subprocess.Popen(['explorer', '/select,', os.path.normpath(filepath)],
                             creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            # File gone — just open the downloaded folder
            subprocess.Popen(['explorer', os.path.normpath(DOWNLOADED_DIR)],
                             creationflags=subprocess.CREATE_NO_WINDOW)

    def _open_queue_item_in_explorer(self):
        """Open Explorer for the selected queue item. Selects the MP3 if status is Done."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Open File", "Please select a queue item first.")
            return
        values = self.tree.item(selected[0])['values']
        status = values[2]  # column index: id, title, status, progress, eta
        title = values[1]

        if status == 'Done':
            # Best-effort: find the MP3 by sanitised title
            import re as _re
            safe = _re.sub(r'[\\/:*?"<>|]', '_', str(title))
            candidate = os.path.join(DOWNLOADED_DIR, safe + '.mp3')
            self._explorer_select(candidate)
        else:
            # Not done yet — just open the downloaded folder
            import subprocess
            subprocess.Popen(['explorer', os.path.normpath(DOWNLOADED_DIR)],
                             creationflags=subprocess.CREATE_NO_WINDOW)

    def _open_history_item_in_explorer(self):
        """Open Explorer with the selected Downloaded-tab entry's file highlighted."""
        selected = self.hist_tree.selection()
        if not selected:
            messagebox.showinfo("Open File", "Please select an entry first.")
            return
        iid = selected[0]
        log_id = self._hist_iid_to_log_id.get(iid)
        if log_id is None:
            return
        # Find the entry to get filename
        for entry in self.log.get_visible_entries():
            if entry['id'] == log_id:
                filepath = os.path.join(DOWNLOADED_DIR, entry['filename'])
                self._explorer_select(filepath)
                return

if __name__ == "__main__":
    import static_ffmpeg # type: ignore
    try:
        static_ffmpeg.add_paths()
    except Exception as e:
        print("Note: static_ffmpeg error on startup:", e)

    # Start local search API server for browser extension
    api_thread = threading.Thread(target=start_search_api, daemon=True)
    api_thread.start()

    root = tk.Tk()
    
    # Simple style adjustments for Treeview
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#e0e0e0")
    style.configure("Treeview", font=("Segoe UI", 10), rowheight=25)
    
    app = App(root)
    root.mainloop()
