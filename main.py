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
        self.config_dir = Path.home() / '.ghv-monitor'
        self.config_file = self.config_dir / 'config.json'
        self.queue_file = self.config_dir / 'queue.json'
        
        self.config_dir.mkdir(exist_ok=True)
        
        self.is_monitoring = False
        self.is_paused = False
        self.session_active = False
        self.credentials = None
        self.upload_queue = []
        
        self.load_config()
        self.load_queue()
        
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
    
    def clear_saved_credentials(self):
        """Remove saved credentials when login fails"""
        self.credentials = None
        try:
            if self.config_file.exists():
                self.config_file.unlink()
        except Exception as e:
            print(f"Error clearing config: {e}")
    
    def load_queue(self):
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r') as f:
                    self.upload_queue = json.load(f)
                print(f"Loaded {len(self.upload_queue)} items from queue")
            except Exception as e:
                print(f"Error loading queue: {e}")
    
    def save_queue(self):
        try:
            with open(self.queue_file, 'w') as f:
                json.dump(self.upload_queue, f)
        except Exception as e:
            print(f"Error saving queue: {e}")
    
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
        """Login with credentials - clears saved creds on failure"""
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
                    self.save_config()
                    
                    self.sync_with_tracker()
                    schedule.every(CONFIG['STATUS_CHECK_SECONDS']).seconds.do(self.sync_with_tracker)
                    
                    return {'success': True}
                else:
                    # Login rejected by server - clear any saved credentials
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
