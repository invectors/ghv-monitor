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
from datetime import datetime, timezone, timedelta
from pathlib import Path

import mss
import requests
from PIL import Image
from io import BytesIO
import base64


# Idle detection.
# On macOS, pynput's keyboard listener calls main-thread-only Carbon
# (TSM) APIs from its background thread, which hard-crashes with
# EXC_BAD_INSTRUCTION (SIGILL). So on macOS we use the native, thread-safe
# Quartz idle query instead and never start pynput listeners.
IS_MACOS = sys.platform == 'darwin'
MACOS_IDLE_AVAILABLE = False
if IS_MACOS:
    try:
        from Quartz import (
            CGEventSourceSecondsSinceLastEventType,
            kCGEventSourceStateHIDSystemState,
            kCGAnyInputEventType,
        )
        MACOS_IDLE_AVAILABLE = True
    except Exception:
        print("[Idle] Quartz not available — macOS idle detection disabled")

# pynput is used for idle detection on Windows/Linux only.
try:
    from pynput import keyboard, mouse
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("[Idle] pynput not available — idle detection disabled")

# True if *some* idle backend is usable on this platform.
IDLE_AVAILABLE = MACOS_IDLE_AVAILABLE or (PYNPUT_AVAILABLE and not IS_MACOS)

# Configuration
CONFIG = {
    'UPLOAD_URL': 'https://hub.gohirevirtual.net/api/screenshots/upload.php',
    'STATUS_URL': 'https://hub.gohirevirtual.net/api/screenshots/status.php',
    'IDLE_URL':   'https://hub.gohirevirtual.net/api/screenshots/idle.php',
    'CAPTURE_INTERVAL_MINUTES': 10,
    'STATUS_CHECK_SECONDS': 30,
    'IDLE_CHECK_INTERVAL_SECONDS': 15,           # how often to poll OS for idle time
    'IDLE_DETECTION_THRESHOLD_SECONDS': 300,     # 5 min of no input = idle
    'MAX_RETRY_ATTEMPTS': 3,
    'IMAGE_QUALITY': 85,
    'MAX_IMAGE_WIDTH': 1920,
}

class IdleDetector:
    """Cross-platform OS idle detector.

    On macOS: uses the native, thread-safe Quartz HID idle query
    (CGEventSourceSecondsSinceLastEventType) — no input listeners, so it
    is safe to call from the scheduler thread and does not crash.

    On Windows/Linux: uses pynput keyboard/mouse listeners to track the
    time of the most recent input event.

    `get_idle_seconds()` returns how long it's been since any input.
    """
    def __init__(self):
        self.last_input_time = time.time()
        self._listeners = []
        self._started = False

    def _on_activity(self, *args, **kwargs):
        self.last_input_time = time.time()

    def start(self):
        if self._started:
            return
        # macOS: nothing to start — idle time is queried on demand.
        if IS_MACOS:
            if MACOS_IDLE_AVAILABLE:
                self._started = True
                print("[Idle] Detector started (macOS native Quartz)")
            return
        # Windows/Linux: start pynput listeners on background threads.
        if not PYNPUT_AVAILABLE:
            return
        try:
            kb_listener = keyboard.Listener(on_press=self._on_activity)
            ms_listener = mouse.Listener(
                on_move=self._on_activity,
                on_click=self._on_activity,
                on_scroll=self._on_activity,
            )
            kb_listener.daemon = True
            ms_listener.daemon = True
            kb_listener.start()
            ms_listener.start()
            self._listeners = [kb_listener, ms_listener]
            self._started = True
            print("[Idle] Detector started (pynput)")
        except Exception as e:
            # Most common on Wayland or restricted/headless systems
            print(f"[Idle] Failed to start listeners: {e}")

    def get_idle_seconds(self):
        if not self._started:
            return 0.0
        if IS_MACOS:
            # System-wide seconds since the last HID input event.
            # Safe to call from any thread.
            try:
                return float(CGEventSourceSecondsSinceLastEventType(
                    kCGEventSourceStateHIDSystemState,
                    kCGAnyInputEventType,
                ))
            except Exception:
                return 0.0
        return time.time() - self.last_input_time

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

        # Idle detection state
        self.idle_detector = IdleDetector()
        self.is_idle = False  # True between sending 'start' and 'end' events
        
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
                # Screenshot uploads are ~150-300KB; allow generous read time
                # on slow connections, especially Windows after sleep/wake.
                timeout=(15, 60)
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
        """Check status with the server.

        Returns:
            dict with at least 'active' key — server's response
            None — could not determine (network error, timeout, transient 5xx);
                   caller should KEEP current state, not transition
            {'auth_failed': True} — credentials rejected (401); caller should
                                   stop and prompt re-login
        """
        try:
            if not self.credentials:
                return None  # No credentials = nothing to check

            response = requests.get(
                CONFIG['STATUS_URL'],
                headers={
                    'Authorization': f"Bearer {self.credentials['username']}:{self.credentials['password']}"
                },
                # (connect_timeout, read_timeout) — generous for Windows
                # network stack quirks and sleep/wake recovery
                timeout=(15, 30)
            )

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as e:
                    print(f"[Status] Server returned non-JSON 200: {e}")
                    return None  # Transient — server hiccup

            if response.status_code == 401:
                print("[Status] Authentication rejected (401)")
                return {'auth_failed': True}

            # Any other status (5xx, 502, 503, 504, etc.) is transient
            print(f"[Status] Transient HTTP {response.status_code} — keeping current state")
            return None

        except requests.exceptions.Timeout:
            print("[Status] Request timed out — keeping current state")
            return None
        except requests.exceptions.ConnectionError as e:
            # Most common Windows failure mode — DNS, reset, refused
            print(f"[Status] Connection error — keeping current state: {e}")
            return None
        except Exception as e:
            print(f"[Status] Unexpected error — keeping current state: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def sync_with_tracker(self):
        try:
            print("[Sync] Checking status...")
            status = self.check_status()

            # status is None when we couldn't determine — keep current state.
            # This prevents transient network failures from flipping the app
            # into "offline waiting for clockin" state.
            if status is None:
                print("[Sync] Could not determine status — keeping current state")
                return

            # Auth was rejected. Stop monitoring and let user re-login.
            if status.get('auth_failed'):
                print("[Sync] Auth failed — stopping monitoring, credentials need refresh")
                if self.is_monitoring:
                    self.stop_monitoring()
                # Don't auto-clear credentials here — let the user see the
                # login screen and decide; clearing silently is worse UX.
                return

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
                # Server confirmed: NOT clocked in. This is the only path that
                # stops monitoring on a "clocked out" signal — and it requires
                # a successful, parseable HTTP 200 response that said so.
                if self.is_monitoring:
                    print("[Sync] Stopping monitoring (server confirmed clocked out)")
                    self.stop_monitoring()

            self.session_active = status.get('active', False)
        except Exception as e:
            print(f"[Sync] Error: {e}")
            import traceback
            traceback.print_exc()

    def send_idle_event(self, event_type, when_utc):
        """POST an idle 'start' or 'end' event to the server.

        when_utc: a timezone-aware datetime in UTC
        """
        if not self.credentials:
            return
        try:
            timestamp = when_utc.strftime('%Y-%m-%d %H:%M:%S')
            response = requests.post(
                CONFIG['IDLE_URL'],
                json={
                    'event': event_type,        # 'start' or 'end'
                    'timestamp': timestamp,     # UTC, MySQL DATETIME format
                    'idle_type': 'idle',
                },
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f"Bearer {self.credentials['username']}:{self.credentials['password']}",
                },
                timeout=10,
            )
            if response.status_code == 200:
                print(f"[Idle] {event_type} event sent (timestamp UTC: {timestamp})")
            else:
                print(f"[Idle] {event_type} event failed: HTTP {response.status_code} — {response.text[:200]}")
        except Exception as e:
            print(f"[Idle] Error sending {event_type}: {e}")

    def check_idle(self):
        """Periodic idle-state check — runs every IDLE_CHECK_INTERVAL_SECONDS.

        Transitions:
          - not idle → idle: when idle_seconds crosses the threshold
          - idle → not idle: when idle_seconds drops back below the threshold
        """
        if not self.is_monitoring or self.is_paused:
            return
        if not IDLE_AVAILABLE:
            return

        idle_seconds = self.idle_detector.get_idle_seconds()
        threshold = CONFIG['IDLE_DETECTION_THRESHOLD_SECONDS']

        if idle_seconds >= threshold and not self.is_idle:
            # User became idle. The actual start was `idle_seconds` ago.
            idle_start_utc = datetime.now(timezone.utc) - timedelta(seconds=int(idle_seconds))
            print(f"[Idle] User went idle ({int(idle_seconds)}s since last input)")
            self.is_idle = True
            self.send_idle_event('start', idle_start_utc)

        elif idle_seconds < threshold and self.is_idle:
            # User returned to activity. End event timestamp = now.
            print(f"[Idle] User returned to activity")
            self.is_idle = False
            self.send_idle_event('end', datetime.now(timezone.utc))
    
    def capture_and_upload(self):
        if not self.is_monitoring or self.is_paused:
            print("[Capture] Skipping (not monitoring or paused)")
            return
        if self.is_idle:
            print("[Capture] Skipping (user is idle)")
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

        # Begin OS idle detection (idempotent — safe to call repeatedly)
        self.idle_detector.start()
        schedule.every(CONFIG['IDLE_CHECK_INTERVAL_SECONDS']).seconds.do(self.check_idle)

        schedule.every(CONFIG['CAPTURE_INTERVAL_MINUTES']).minutes.do(self.capture_and_upload)
        threading.Timer(5.0, self.capture_and_upload).start()
        
        if self.on_status_changed:
            self.on_status_changed()
        
        print("[Monitor] Started")
    
    def stop_monitoring(self):
        if not self.is_monitoring:
            return
        print("[Monitor] Stopping...")

        # If we're currently in an idle period, close it server-side so the
        # cron alert pipeline doesn't see an unbounded open period.
        if self.is_idle:
            self.send_idle_event('end', datetime.now(timezone.utc))
            self.is_idle = False

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
        """Main scheduler loop. Must never die from an exception —
        if it does, the app silently stops working while the tray icon
        keeps showing the last-known state."""
        print("[Scheduler] Loop started")
        consecutive_errors = 0
        while True:
            try:
                schedule.run_pending()
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                print(f"[Scheduler] Error in run_pending (#{consecutive_errors}): {e}")
                import traceback
                traceback.print_exc()
                # Back off slightly on repeated failures, but never give up
                if consecutive_errors > 10:
                    time.sleep(5)
            try:
                time.sleep(1)
            except Exception:
                # Even sleep can fail in extreme edge cases (signal interrupts
                # on Windows during sleep/wake). Don't let it kill us.
                pass

# Global instance
monitor = ScreenshotMonitor()

if __name__ == '__main__':
    if monitor.credentials:
        monitor.sync_with_tracker()
        schedule.every(CONFIG['STATUS_CHECK_SECONDS']).seconds.do(monitor.sync_with_tracker)
    
    monitor.run_scheduler()
