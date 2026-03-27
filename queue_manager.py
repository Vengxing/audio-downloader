import os
import sys
import threading
import queue
import time
import subprocess
import yt_dlp # type: ignore
from download_log import DownloadLog # type: ignore

class QueueManager:
    def __init__(self, ui_update_cb, history_update_cb=None):
        self.queue = []         # List of dicts: {'id': int, 'url': str, 'title': str, 'status': str, 'progress': str, 'eta': str}
        self.next_id = 1
        
        self.ui_update_cb = ui_update_cb
        self.history_update_cb = history_update_cb
        
        self.is_paused = False
        self.download_cancel_flag = False
        self.current_download_id = None # type: ignore
        
        self.conversion_queue = queue.Queue()
        self.log = DownloadLog()
        
        os.makedirs('.temp', exist_ok=True)
        os.makedirs('downloaded', exist_ok=True)
        # Hide .temp folder on Windows
        if sys.platform == 'win32':
            subprocess.run(['attrib', '+h', '.temp'], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        
        # Start background threads
        self.dl_thread = threading.Thread(target=self._download_loop, daemon=True)
        self.dl_thread.start()
        
        self.conv_thread = threading.Thread(target=self._conversion_loop, daemon=True)
        self.conv_thread.start()

    def add_url(self, url):
        item = {
            'id': self.next_id,
            'url': url,
            'title': 'Fetching...',
            'status': 'Queued',
            'progress': '-',
            'eta': '-',
            'byte_size': 0
        }
        self.queue.append(item)
        self.next_id += 1
        self._notify_ui()
        return item['id']

    def pause_queue(self):
        self.is_paused = True
        # If currently downloading, trigger abort
        if self.current_download_id is not None:
            self.download_cancel_flag = True
            self._update_item(self.current_download_id, status='Paused')
        self._notify_ui()

    def resume_queue(self):
        self.is_paused = False
        self.download_cancel_flag = False
        # Any 'Paused' items go back to 'Queued'
        for item in self.queue:
            if item['status'] == 'Paused':
                item['status'] = 'Queued'
        self._notify_ui()

    def cancel_item(self, item_id):
        # If it's currently downloading, abort it
        if self.current_download_id == item_id:
            self.download_cancel_flag = True
        
        # Remove from queue list
        self.queue = [item for item in self.queue if item['id'] != item_id]
        self._notify_ui()

    def prioritize_item(self, item_id):
        # Find item
        idx = -1
        for i, item in enumerate(self.queue):
            if item['id'] == item_id:
                idx = i
                break
        
        if idx > 0:
            item = self.queue.pop(idx)
            # Insert at the top (under currently processing ones if we want, or absolute top)
            # Let's put it at index 0
            self.queue.insert(0, item)
            
            # If we are currently downloading something else, abort it so the prioritized one gets picked next
            if self.current_download_id is not None and self.current_download_id != item_id:
                self.download_cancel_flag = True
                self._update_item(self.current_download_id, status='Queued')
                
            self._notify_ui()

    def _update_item(self, item_id, **kwargs):
        for item in self.queue:
            if item['id'] == item_id:
                for k, v in kwargs.items():
                    item[k] = v
                self._notify_ui()
                return

    def _notify_ui(self):
        if self.ui_update_cb:
            self.ui_update_cb(list(self.queue))

    def _download_loop(self):
        while True:
            if self.is_paused:
                time.sleep(1)
                continue

            # Find next queued item
            next_item = None
            for item in self.queue:
                if item['status'] == 'Queued':
                    next_item = item
                    break
            
            if not next_item:
                time.sleep(1)
                continue
            
            self.current_download_id = next_item['id'] # type: ignore
            self.download_cancel_flag = False
            self._update_item(self.current_download_id, status='Downloading')
            
            try:
                self._do_download(next_item)
            except Exception as e:
                # Aborted or errored
                if str(e) == "Cancelled":
                    # If it wasn't removed entirely from the queue, make sure it's marked properly
                    pass 
                else:
                    self._update_item(self.current_download_id, status='Error', progress=str(e))
            finally:
                self.current_download_id = None

    def _do_download(self, item):
        downloaded_file_path = []
        
        def progress_hook(d):
            if self.download_cancel_flag:
                raise ValueError("Cancelled")
                
            if d['status'] == 'downloading':
                percent = str(d.get('_percent_str', 'N/A')).replace('\x1b[0;94m', '').replace('\x1b[0m', '')
                eta = str(d.get('_eta_str', 'N/A')).replace('\x1b[0;33m', '').replace('\x1b[0m', '')
                self._update_item(item['id'], progress=percent, eta=eta)
            elif d['status'] == 'finished':
                downloaded_file_path.append(d['filename'])
                # Capture total byte size (prefer actual over estimate)
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                self._update_item(item['id'], progress='100%', eta='-', byte_size=int(total))

        # Use static_ffmpeg path for yt-dlp too
        import static_ffmpeg # type: ignore
        import os
        ffmpeg_dir = os.path.dirname(static_ffmpeg.__file__)
        ffmpeg_bin = os.path.join(ffmpeg_dir, 'bin')
        if os.path.exists(ffmpeg_bin):
            ffmpeg_dir = ffmpeg_bin

        # yt-dlp options just to download best audio, NOT converting
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join('.temp', '%(title)s.%(ext)s'),
            'nocheckcertificate': True,
            'noplaylist': True,
            'noui': True,
            'progress_hooks': [progress_hook],
            'ignoreerrors': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Update title first
            info = ydl.extract_info(item['url'], download=False)
            if info and 'title' in info:
                self._update_item(item['id'], title=info['title'])
            
            ydl.download([item['url']])
            
        if downloaded_file_path:
            raw_file = downloaded_file_path[0]
            self._update_item(item['id'], status='Converting', progress='Wait...')
            self.conversion_queue.put({
                'id': item['id'],
                'url': item['url'],
                'raw_file': raw_file,
                'title': item['title'],
                'byte_size': item.get('byte_size', 0)
            })

    def _conversion_loop(self):
        while True:
            conv_task = self.conversion_queue.get()
            item_id = conv_task['id']
            raw_file = conv_task['raw_file']
            
            # Check if it was cancelled before conversion started
            item_exists = any(i['id'] == item_id for i in self.queue)
            if not item_exists:
                # Clean up file if they cancelled it
                if os.path.exists(raw_file):
                    os.remove(raw_file)
                self.conversion_queue.task_done()
                continue
                
            self._update_item(item_id, progress='Converting to MP3...')
            
            # Setup static_ffmpeg in PATH for the conversion subprocess
            import static_ffmpeg # type: ignore
            static_ffmpeg.add_paths()
            
            base_name_only = os.path.splitext(os.path.basename(raw_file))[0]
            output_file = os.path.join('downloaded', f"{base_name_only}.mp3")
            
            cmd = [
                'ffmpeg',
                '-y',
                '-i', raw_file,
                '-vn',
                '-ar', '44100',
                '-ac', '2',
                '-b:a', '320k',
                output_file
            ]
            
            try:
                # Run ffmpeg hiding console window on windows
                creation_flags = 0
                if sys.platform == "win32":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                    
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
                
                # Success — log to DB using actual MP3 file size
                actual_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
                self.log.add_entry(
                    url=conv_task.get('url', ''),
                    youtube_title=conv_task['title'],
                    filename=os.path.basename(output_file),
                    byte_size=actual_size
                )
                
                self._update_item(item_id, status='Done', progress='Saved as MP3')
                
                # Delete original raw temp file
                if os.path.exists(raw_file):
                    os.remove(raw_file)
                
                # Notify UI to refresh history tab
                if self.history_update_cb:
                    self.history_update_cb()
                    
            except Exception as e:
                self._update_item(item_id, status='Error', progress='Conversion failed')
                
            self.conversion_queue.task_done()
