import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import yt_dlp # type: ignore
import sys
import queue

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

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube to MP3 Downloader Pro")
        self.root.geometry("800x500")
        self.root.configure(bg="#f0f2f5")
        
        # Initialize queue manager
        self.qm = QueueManager(self._on_queue_update)
        
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

        # Queue Table
        table_frame = tk.Frame(root, padx=20, pady=10, bg="#f0f2f5")
        table_frame.pack(fill='both', expand=True)

        columns = ("id", "title", "status", "progress", "eta")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="#")
        self.tree.column("id", width=40, anchor='center')
        
        self.tree.heading("title", text="Title/URL")
        self.tree.column("title", width=350, anchor='w')
        
        self.tree.heading("status", text="Status")
        self.tree.column("status", width=100, anchor='center')
        
        self.tree.heading("progress", text="Progress")
        self.tree.column("progress", width=120, anchor='center')
        
        self.tree.heading("eta", text="ETA")
        self.tree.column("eta", width=80, anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def add_url(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid YouTube link.")
            return
        self.qm.add_url(url)
        self.url_entry.delete(0, tk.END)

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
        
        for item in q_list:
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

if __name__ == "__main__":
    import static_ffmpeg # type: ignore
    try:
        static_ffmpeg.add_paths()
    except Exception as e:
        print("Note: static_ffmpeg error on startup:", e)
        
    root = tk.Tk()
    
    # Simple style adjustments for Treeview
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#e0e0e0")
    style.configure("Treeview", font=("Segoe UI", 10), rowheight=25)
    
    app = App(root)
    root.mainloop()
