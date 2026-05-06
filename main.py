#!/usr/bin/env python3
"""
GHV Monitor - Desktop Screenshot Monitor
"""

import os
import sys
import time
import json
import threading
import schedule
from datetime import datetime
from pathlib import Path
import mss
import requests
from PIL import Image
from io import BytesIO
import base64

# Configuration
CONFIG = {
    'UPLOAD_URL': 'https://hub.gohirevirtual.net/api/screenshots/upload.php',
    'STATUS_URL': 'https://hub.gohirevirtual.net/api/screenshots/status.php',
    'CAPTURE_INTERVAL_MINUTES': 10,
    'STATUS_CHECK_SECONDS': 30,
    'MAX_RETRY_ATTEMPTS': 3,
    'IMAGE_QUALITY': 85,
    'MAX_IMAGE_WIDTH': 1920,
}

class ScreenshotMonitor:
    def __init__(self):
        # Cross-platform config directory
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / 'config.json'
        self.queue_file = self.config_dir / 'queue.json'
        
        print(f"[Config] Config directory: {self.config_dir}")
        print(f"[Config] Config file: {self.config_file}")
        
        # Create config directory with proper permissions
        self._ensure_config_dir()
        
        # State
        self.is_monitoring = False
        self.is_paused = False
        self.session_active = False
        self.credentials = None
        self.upload_queue = []
        
        # Load saved data
        self.load_config()
        self.load_queue()
        
        # Callbacks for UI
        self.on_status_changed = None
        self.on_screenshot_captured = None
    
    def _get_config_dir(self):
        """Get cross-platform config directory"""
        if sys.platform == 'win32':
            # Windows: Use APPDATA or fallback to USERPROFILE
            app_data = os.environ.get('APPDATA')
            if app_data:
                return Path(app_data) / 'GHV-Monitor'
            user_profile = os.environ.get('USERPROFILE')
            if user_profile:
                return Path(user_profile) / 'GHV-Monitor'
            return Path.home() / 'GHV-Monitor'
        else:
            # Linux/macOS: Use ~/.config/GHV-Monitor (XDG standard) or fallback to ~/.ghv-monitor
            xdg_config = os.environ.get('XDG_CONFIG_HOME')
            if xdg_config:
                return Path(xdg_config) / 'GHV-Monitor'
            return Path.home() / '.config' / 'GHV-Monitor'
    
    def _ensure_config_dir(self):
        """Create config directory with error handling"""
        try:
            # Create with parents=True, exist_ok=True
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Verify it exists and is writable
            if not self.config_dir.exists():
                raise RuntimeError(f"Failed to create directory: {self.config_dir}")
            
            # Test write permission by creating a test file
            test_file = self.config_dir / '.write_test'
            try:
                test_file.write_text('test')
                test_file.unlink()  # Clean up
                print(f"[Config] Directory verified and writable: {self.config_dir}")
            except Exception as e:
                print(f"[Config] Directory not writable: {e}")
                raise
                
        except Exception as e:
            print(f"[Config] ERROR creating directory: {e}")
            # Fallback: use temp directory
            import tempfile
            fallback = Path(tempfile.gettempdir()) / 'GHV-Monitor'
            print(f"[Config] Using fallback: {fallback}")
            fallback.mkdir(parents=True, exist_ok=True)
            self.config_dir = fallback
            self.config_file = self.config_dir / 'config.json'
            self.queue_file = self.config_dir / 'queue.json'
    
    def load_config(self):
        """Load saved configuration"""
        print(f"[Config] Loading from: {self.config_file}")
        print(f"[Config] File exists: {self.config_file.exists()}")
        
        if self.config_file.exists():
            try:
                content = self.config_file.read_text(encoding='utf-8')
                print(f"[Config] File content length: {len(content)}")
                data = json.loads(content)
                self.credentials = data.get('credentials')
                print(f"[Config] Loaded credentials: {self.credentials is not None}")
                if self.credentials:
                    print(f"[Config] Username: {self.credentials.get('username', 'N/A')}")
            except Exception as e:
                print(f"[Config] Error loading config: {e}")
                self.credentials = None
        else:
            print("[Config] No config file found")
            self.credentials = None
    
    def save_config(self):
        """Save configuration - FORCE WRITE"""
        print(f"[Config] Saving to: {self.config_file}")
        print(f"[Config] Current credentials: {self.credentials}")
        
        try:
            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Write atomically: temp file then rename
            temp_file = self.config_file.with_suffix('.tmp')
            data = {'credentials': self.credentials}
            
            # Write to temp file
            temp_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
            print(f"[Config] Temp file written: {temp_file}")
            
            # Rename to final (atomic on most systems)
            temp_file.replace(self.config_file)
            print(f"[Config] Renamed to: {self.config_file}")
            
            # Verify
            if self.config_file.exists():
                verify = self.config_file.read_text(encoding='utf-8')
                print(f"[Config] Verified write: {len(verify)} bytes")
                print("[Config] Saved successfully")
            else:
                print("[Config] CRITICAL: File not found after save!")
                
        except Exception as e:
            print(f"[Config] ERROR saving config: {e}")
            import traceback
            traceback.print_exc()
    
    def clear_saved_credentials(self):
        """Remove saved credentials when login fails"""
        print("[Config] Clearing saved credentials")
        self.credentials = None
        try:
            if self.config_file.exists():
                self.config_file.unlink()
                print("[Config] Config file deleted")
        except Exception as e:
            print(f"[Config] Error clearing config: {e}")
    
    def load_queue(self):
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    self.upload_queue = json.load(f)
                print(f"[Queue] Loaded {len(self.upload_queue)} items")
            except Exception as e:
                print(f"[Queue] Error loading queue: {e}")
    
    def save_queue(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(self.upload_queue, f)
        except Exception as e:
            print(f"[Queue] Error saving queue: {e}")
    
    def capture_screenshot(self):
        try:
            print("[Screenshot] Capturing desktop...")
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screenshot = sct.grab(monitor)
                img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                
                if img.width > CONFIG['MAX_IMAGE_WIDTH']:
                    ratio = CONFIG['MAX_IMAGE_WIDTH'] / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((CONFIG['MAX_IMAGE_WIDTH'], new_height), Image.Resampling.LANCZOS)
                
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=CONFIG['IMAGE_QUALITY'])
                img_bytes = buffer.getvalue()
                
                print(f"[Screenshot] Captured ({len(img_bytes)} bytes)")
                return img_bytes
        except Exception as e:
            print(f"[Screenshot] Error: {e}")
            raise
    
    def upload_screenshot(self, image_bytes):
        try:
            if not self.credentials:
                raise Exception("Not logged in")
            
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            print("[Upload] Uploading screenshot...")
            
            response = requests.post(
                CONFIG['UPLOAD_URL'],
                json={
                    'screenshot': base64_image,
                    'timestamp': datetime.now().isoformat()
                },
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f"Bearer {self.credentials['username']}:{self.credentials['password']}"
                },
                timeout=30
            )
            
            print(f"[Upload] Response code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    print(f"[Upload] Success")
                    return {'success': True, 'data': data}
                else:
                    raise Exception(data.get('message', 'Upload failed'))
            elif response.status_code == 401:
                print("[Upload] Session expired")
                self.stop_monitoring()
                return {'session_expired': True}
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            print(f"[Upload] Error: {e}")
            raise
    
    def check_status(self):
        try:
            if not self.credentials:
                return {'active': False}
            
            response = requests.get(
                CONFIG['STATUS_URL'],
                headers={
                    'Authorization': f"Bearer {self.credentials['username']}:{self.credentials['password']}"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'active': False}
                
        except Exception as e:
            print(f"[Status] Error: {e}")
            return {'active': False}
    
    def sync_with_tracker(self):
        try:
            print("[Sync] Checking status...")
            status = self.check_status()
            
            print(f"[Sync] Status: active={status.get('active')}, clocked_in={status.get('clocked_in')}, on_lunch={status.get('on_lunch')}")
            
            if status.get('active') and status.get('clocked_in') and not status.get('on_lunch'):
                if not self.is_monitoring:
                    print("[Sync] Starting monitoring (clocked in)")
                    self.start_monitoring()
                elif self.is_paused:
                    print("[Sync] Resuming monitoring (back from lunch)")
                    self.resume_monitoring()
            elif status.get('active') and status.get('on_lunch'):
                if self.is_monitoring and not self.is_paused:
                    print("[Sync] Pausing monitoring (on lunch)")
                    self.pause_monitoring()
            else:
                if self.is_monitoring:
                    print("[Sync] Stopping monitoring (clocked out)")
                    self.stop_monitoring()
            
            self.session_active = status.get('active', False)
            
        except Exception as e:
            print(f"[Sync] Error: {e}")
    
    def capture_and_upload(self):
        if not self.is_monitoring or self.is_paused:
            print("[Capture] Skipping (not monitoring or paused)")
            return
        
        try:
            image_bytes = self.capture_screenshot()
            result = self.upload_screenshot(image_bytes)
            
            if result.get('success'):
                self.process_queue()
                if self.on_screenshot_captured:
                    self.on_screenshot_captured('success')
            else:
                self.upload_queue.append({
                    'image': base64.b64encode(image_bytes).decode('utf-8'),
                    'timestamp': datetime.now().isoformat(),
                    'retry_count': 0
                })
                self.save_queue()
                
        except Exception as e:
            print(f"[Capture] Error: {e}")
            if self.on_screenshot_captured:
                self.on_screenshot_captured('error')
    
    def process_queue(self):
        if not self.upload_queue:
            return
        
        print(f"[Queue] Processing {len(self.upload_queue)} items")
        
        items_to_retry = []
        
        for item in self.upload_queue:
            try:
                image_bytes = base64.b64decode(item['image'])
                result = self.upload_screenshot(image_bytes)
                
                if not result.get('success'):
                    item['retry_count'] = item.get('retry_count', 0) + 1
                    if item['retry_count'] < CONFIG['MAX_RETRY_ATTEMPTS']:
                        items_to_retry.append(item)
                    else:
                        print(f"[Queue] Max retries reached for item")
                        
            except Exception as e:
                print(f"[Queue] Error: {e}")
                item['retry_count'] = item.get('retry_count', 0) + 1
                if item['retry_count'] < CONFIG['MAX_RETRY_ATTEMPTS']:
                    items_to_retry.append(item)
        
        self.upload_queue = items_to_retry
        self.save_queue()
    
    def start_monitoring(self):
        if self.is_monitoring:
            return
        
        print("[Monitor] Starting...")
        self.is_monitoring = True
        self.is_paused = False
        
        schedule.every(CONFIG['CAPTURE_INTERVAL_MINUTES']).minutes.do(self.capture_and_upload)
        
        threading.Timer(5.0, self.capture_and_upload).start()
        
        if self.on_status_changed:
            self.on_status_changed()
        
        print("[Monitor] Started")
    
    def stop_monitoring(self):
        if not self.is_monitoring:
            return
        
        print("[Monitor] Stopping...")
        self.is_monitoring = False
        self.is_paused = False
        
        schedule.clear()
        
        if self.on_status_changed:
            self.on_status_changed()
        
        print("[Monitor] Stopped")
    
    def pause_monitoring(self):
        if not self.is_monitoring or self.is_paused:
            return
        
        print("[Monitor] Pausing...")
        self.is_paused = True
        
        if self.on_status_changed:
            self.on_status_changed()
    
    def resume_monitoring(self):
        if not self.is_monitoring or not self.is_paused:
            return
        
        print("[Monitor] Resuming...")
        self.is_paused = False
        
        if self.on_status_changed:
            self.on_status_changed()
    
    def login(self, username, password):
        """Login with credentials"""
        try:
            print(f"[Login] Attempting login for {username}...")
            print(f"[Login] URL: {CONFIG['STATUS_URL']}")
            
            response = requests.post(
                CONFIG['STATUS_URL'],
                json={'username': username, 'password': password},
                timeout=10
            )
            
            print(f"[Login] Response code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"[Login] Response: {data}")
                
                if data.get('success'):
                    self.credentials = {'username': username, 'password': password}
                    self.save_config()  # This should now work!
                    
                    self.sync_with_tracker()
                    schedule.every(CONFIG['STATUS_CHECK_SECONDS']).seconds.do(self.sync_with_tracker)
                    
                    return {'success': True}
                else:
                    self.clear_saved_credentials()
                    return {'success': False, 'message': data.get('message', 'Invalid credentials')}
            else:
                self.clear_saved_credentials()
                return {'success': False, 'message': f'Server error: HTTP {response.status_code}'}
                
        except requests.exceptions.ConnectionError as e:
            print(f"[Login] Connection error: {e}")
            self.clear_saved_credentials()
            return {'success': False, 'message': 'Connection failed. Check your internet connection.'}
        except requests.exceptions.Timeout as e:
            print(f"[Login] Timeout: {e}")
            self.clear_saved_credentials()
            return {'success': False, 'message': 'Connection timed out. Server may be down.'}
        except Exception as e:
            print(f"[Login] Error: {e}")
            self.clear_saved_credentials()
            return {'success': False, 'message': f'Error: {str(e)}'}
    
    def logout(self):
        """Logout - clears everything"""
        self.stop_monitoring()
        self.credentials = None
        self.clear_saved_credentials()
        schedule.clear()
    
    def run_scheduler(self):
        while True:
            schedule.run_pending()
            time.sleep(1)

# Global instance
monitor = ScreenshotMonitor()

if __name__ == '__main__':
    if monitor.credentials:
        monitor.sync_with_tracker()
        schedule.every(CONFIG['STATUS_CHECK_SECONDS']).seconds.do(monitor.sync_with_tracker)
    
    monitor.run_scheduler()
