#!/usr/bin/env python3
"""
GHV Monitor - Desktop Screenshot Monitor
Main application file - FIXED VERSION
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
    'STATUS_CHECK_SECONDS': 30,  # Check status every 30 seconds instead of 5 minutes
    'MAX_RETRY_ATTEMPTS': 3,
    'IMAGE_QUALITY': 85,
    'MAX_IMAGE_WIDTH': 1920,
}

class ScreenshotMonitor:
    def __init__(self):
        self.config_dir = Path.home() / '.ghv-monitor'
        self.config_file = self.config_dir / 'config.json'
        self.queue_file = self.config_dir / 'queue.json'
        
        # Create config directory
        self.config_dir.mkdir(exist_ok=True)
        
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
        
    def load_config(self):
        """Load saved configuration"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.credentials = data.get('credentials')
            except Exception as e:
                print(f"Error loading config: {e}")
    
    def save_config(self):
        """Save configuration"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump({
                    'credentials': self.credentials
                }, f)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def load_queue(self):
        """Load upload queue"""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r') as f:
                    self.upload_queue = json.load(f)
                print(f"Loaded {len(self.upload_queue)} items from queue")
            except Exception as e:
                print(f"Error loading queue: {e}")
    
    def save_queue(self):
        """Save upload queue"""
        try:
            with open(self.queue_file, 'w') as f:
                json.dump(self.upload_queue, f)
        except Exception as e:
            print(f"Error saving queue: {e}")
    
    def capture_screenshot(self):
        """Capture desktop screenshot"""
        try:
            print("[Screenshot] Capturing desktop...")
            
            # Capture all monitors
            with mss.mss() as sct:
                # Get all monitors
                monitor = sct.monitors[0]  # 0 = all monitors combined
                
                # Capture screenshot
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                
                # Resize if too large
                if img.width > CONFIG['MAX_IMAGE_WIDTH']:
                    ratio = CONFIG['MAX_IMAGE_WIDTH'] / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((CONFIG['MAX_IMAGE_WIDTH'], new_height), Image.Resampling.LANCZOS)
                
                # Convert to JPEG bytes
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=CONFIG['IMAGE_QUALITY'])
                img_bytes = buffer.getvalue()
                
                print(f"[Screenshot] Captured ({len(img_bytes)} bytes)")
                return img_bytes
                
        except Exception as e:
            print(f"[Screenshot] Error: {e}")
            raise
    
    def upload_screenshot(self, image_bytes):
        """Upload screenshot to server"""
        try:
            if not self.credentials:
                raise Exception("Not logged in")
            
            # Convert to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            print("[Upload] Uploading screenshot...")
            print(f"[Upload] URL: {CONFIG['UPLOAD_URL']}")
            print(f"[Upload] Image size: {len(image_bytes)} bytes")
            
            # Upload
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
            print(f"[Upload] Response body: {response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    print(f"[Upload] Success: {data.get('message')}")
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
        """Check session status with server"""
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
        """Sync monitoring state with time tracker"""
        try:
            print("[Sync] Checking status...")
            status = self.check_status()
            
            print(f"[Sync] Status: active={status.get('active')}, clocked_in={status.get('clocked_in')}, on_lunch={status.get('on_lunch')}")
            
            if status.get('active') and status.get('clocked_in') and not status.get('on_lunch'):
                # Should be monitoring
                if not self.is_monitoring:
                    print("[Sync] Starting monitoring (clocked in)")
                    self.start_monitoring()
                elif self.is_paused:
                    print("[Sync] Resuming monitoring (back from lunch)")
                    self.resume_monitoring()
            elif status.get('active') and status.get('on_lunch'):
                # Should be paused
                if self.is_monitoring and not self.is_paused:
                    print("[Sync] Pausing monitoring (on lunch)")
                    self.pause_monitoring()
            else:
                # Should be stopped
                if self.is_monitoring:
                    print("[Sync] Stopping monitoring (clocked out)")
                    self.stop_monitoring()
            
            self.session_active = status.get('active', False)
            
        except Exception as e:
            print(f"[Sync] Error: {e}")
    
    def capture_and_upload(self):
        """Capture screenshot and upload"""
        if not self.is_monitoring or self.is_paused:
            print("[Capture] Skipping (not monitoring or paused)")
            return
        
        try:
            # Capture
            image_bytes = self.capture_screenshot()
            
            # Upload
            result = self.upload_screenshot(image_bytes)
            
            if result.get('success'):
                # Process queue
                self.process_queue()
                
                # Notify UI
                if self.on_screenshot_captured:
                    self.on_screenshot_captured('success')
            else:
                # Queue for retry
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
        """Process upload queue"""
        if not self.upload_queue:
            return
        
        print(f"[Queue] Processing {len(self.upload_queue)} items")
        
        items_to_retry = []
        
        for item in self.upload_queue:
            try:
                # Decode image
                image_bytes = base64.b64decode(item['image'])
                
                # Try upload
                result = self.upload_screenshot(image_bytes)
                
                if not result.get('success'):
                    # Retry
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
        """Start screenshot monitoring"""
        if self.is_monitoring:
            return
        
        print("[Monitor] Starting...")
        self.is_monitoring = True
        self.is_paused = False
        
        # Schedule captures
        schedule.every(CONFIG['CAPTURE_INTERVAL_MINUTES']).minutes.do(self.capture_and_upload)
        
        # First capture after 5 seconds
        threading.Timer(5.0, self.capture_and_upload).start()
        
        # Notify UI
        if self.on_status_changed:
            self.on_status_changed()
        
        print("[Monitor] Started")
    
    def stop_monitoring(self):
        """Stop screenshot monitoring"""
        if not self.is_monitoring:
            return
        
        print("[Monitor] Stopping...")
        self.is_monitoring = False
        self.is_paused = False
        
        # Clear schedule
        schedule.clear()
        
        # Notify UI
        if self.on_status_changed:
            self.on_status_changed()
        
        print("[Monitor] Stopped")
    
    def pause_monitoring(self):
        """Pause monitoring (lunch break)"""
        if not self.is_monitoring or self.is_paused:
            return
        
        print("[Monitor] Pausing...")
        self.is_paused = True
        
        # Notify UI
        if self.on_status_changed:
            self.on_status_changed()
    
    def resume_monitoring(self):
        """Resume monitoring"""
        if not self.is_monitoring or not self.is_paused:
            return
        
        print("[Monitor] Resuming...")
        self.is_paused = False
        
        # Notify UI
        if self.on_status_changed:
            self.on_status_changed()
    
    def login(self, username, password):
        """Login with credentials"""
        try:
            # Verify credentials
            response = requests.post(
                CONFIG['STATUS_URL'],
                json={'username': username, 'password': password},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.credentials = {'username': username, 'password': password}
                    self.save_config()
                    
                    # Start sync
                    self.sync_with_tracker()
                    
                    # Schedule status checks every 30 seconds
                    schedule.every(CONFIG['STATUS_CHECK_SECONDS']).seconds.do(self.sync_with_tracker)
                    
                    return {'success': True}
                else:
                    return {'success': False, 'message': data.get('message')}
            else:
                return {'success': False, 'message': 'Connection failed'}
                
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def logout(self):
        """Logout"""
        self.stop_monitoring()
        self.credentials = None
        self.save_config()
        schedule.clear()
    
    def run_scheduler(self):
        """Run the scheduler loop"""
        while True:
            schedule.run_pending()
            time.sleep(1)

# Global instance
monitor = ScreenshotMonitor()

if __name__ == '__main__':
    # Auto-login if credentials exist
    if monitor.credentials:
        monitor.sync_with_tracker()
        schedule.every(CONFIG['STATUS_CHECK_SECONDS']).seconds.do(monitor.sync_with_tracker)
    
    # Run scheduler
    monitor.run_scheduler()
