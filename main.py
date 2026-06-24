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
    'IDLE_CHECK_INTERVAL_SECONDS': 15,
    'IDLE_DETECTION_THRESHOLD_SECONDS': 300,
    'IDLE_SANITY_CEILING_SECONDS': 4 * 3600,
    'MAX_RETRY_ATTEMPTS': 3,
    'IMAGE_QUALITY': 85,
    'MAX_IMAGE_WIDTH': 1920,
}

class IdleDetector:
    """Cross-platform OS idle detector."""
    def __init__(self):
        self.last_input_time = time.time()
        self._listeners = []
        self._started = False

    def _on_activity(self, *args, **kwargs):
        self.last_input_time = time.time()

    def start(self):
        if self._started:
            return
        if IS_MACOS:
            if MACOS_IDLE_AVAILABLE:
                self._started = True
                print("[Idle] Detector started (macOS native Quartz)")
            return
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
            print(f"[Idle] Failed to start listeners: {e}")

    def ensure_alive(self):
        if IS_MACOS or not PYNPUT_AVAILABLE:
            return
        alive = bool(self._listeners) and all(
            getattr(l, 'running', False) and getattr(l, 'is_alive', lambda: False)()
            for l in self._listeners
        )
        if alive:
            return
        print("[Idle] Listener(s) not alive — restarting.")
        for l in self._listeners:
            try:
                l.stop()
            except Exception:
                pass
        self._listeners = []
        self._started = False
        self.last_input_time = time.time()
        self.start()

    def get_idle_seconds(self):
        if not self._started:
            return 0.0
        if IS_MACOS:
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
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / 'config.json'
        self.queue_file = self.config_dir / 'queue.json'

        print(f"[Config] Config directory: {self.config_dir}")
        print(f"[Config] Config file: {self.config_file}")

        self._ensure_config_dir()

        self.is_monitoring = False
        self.is_paused = False
        self.session_active = False
        self.credentials = None
        self.upload_queue = []

        self.idle_detector = IdleDetector()
        self.is_idle = False
        self.last_capture_success = None

        self.load_config()
        self.load_queue()

        self.on_status_changed = None
        self.on_screenshot_captured = None

    def _get_config_dir(self):
        if sys.platform == 'win32':
            app_data = os.environ.get('APPDATA')
            if app_data:
                return Path(app_data) / 'GHV-Monitor'
            user_profile = os.environ.get('USERPROFILE')
            if user_profile:
                return Path(user_profile) / 'GHV-Monitor'
            return Path.home() / 'GHV-Monitor'
        else:
            xdg_config = os.environ.get('XDG_CONFIG_HOME')
            if xdg_config:
                return Path(xdg_config) / 'GHV-Monitor'
            return Path.home() / '.config' / 'GHV-Monitor'

    def _ensure_config_dir(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            if not self.config_dir.exists():
                raise RuntimeError(f"Failed to create directory: {self.config_dir}")
            test_file = self.config_dir / '.write_test'
            try:
                test_file.write_text('test')
                test_file.unlink()
                print(f"[Config] Directory verified and writable: {self.config_dir}")
            except Exception as e:
                print(f"[Config] Directory not writable: {e}")
                raise
        except Exception as e:
            print(f"[Config] ERROR creating directory: {e}")
            import tempfile
            fallback = Path(tempfile.gettempdir()) / 'GHV-Monitor'
            print(f"[Config] Using fallback: {fallback}")
            fallback.mkdir(parents=True, exist_ok=True)
            self.config_dir = fallback
            self.config_file = self.config_dir / 'config.json'
            self.queue_file = self.config_dir / 'queue.json'

    def load_config(self):
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
        print(f"[Config] Saving to: {self.config_file}")
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            temp_file = self.config_file.with_suffix('.tmp')
            data = {'credentials': self.credentials}
            temp_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
            temp_file.replace(self.config_file)
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
            if IS_MACOS:
                import subprocess
                import tempfile
                tmp_path = tempfile.mktemp(suffix='.jpg')
                subprocess.run(
                    ['screencapture', '-x', '-t', 'jpg', tmp_path],
                    check=True
                )
                with open(tmp_path, 'rb') as f:
                    raw = f.read()
                os.unlink(tmp_path)
                img = Image.open(BytesIO(raw)).convert('RGB')
            else:
                with mss.mss() as sct:
                    monitor_index = 1 if len(sct.monitors) > 1 else 0
                    mon = sct.monitors[monitor_index]
                    screenshot = sct.grab(mon)
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
        try:
            if not self.credentials:
                return None

            response = requests.get(
                CONFIG['STATUS_URL'],
                headers={
                    'Authorization': f"Bearer {self.credentials['username']}:{self.credentials['password']}"
                },
                timeout=(15, 30)
            )

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as e:
                    print(f"[Status] Server returned non-JSON 200: {e}")
                    return None

            if response.status_code == 401:
                print("[Status] Authentication rejected (401)")
                return {'auth_failed': True}

            print(f"[Status] Transient HTTP {response.status_code} — keeping current state")
            return None

        except requests.exceptions.Timeout:
            print("[Status] Request timed out — keeping current state")
            return None
        except requests.exceptions.ConnectionError as e:
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

            if status is None:
                print("[Sync] Could not determine status — keeping current state")
                return

            if status.get('auth_failed'):
                print("[Sync] Auth failed — stopping monitoring, credentials need refresh")
                if self.is_monitoring:
                    self.stop_monitoring()
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
                if self.is_monitoring:
                    print("[Sync] Stopping monitoring (server confirmed clocked out)")
                    self.stop_monitoring()

            self.session_active = status.get('active', False)
        except Exception as e:
            print(f"[Sync] Error: {e}")
            import traceback
            traceback.print_exc()

    def send_idle_event(self, event_type, when_utc):
        if not self.credentials:
            return
        try:
            timestamp = when_utc.strftime('%Y-%m-%d %H:%M:%S')
            response = requests.post(
                CONFIG['IDLE_URL'],
                json={
                    'event': event_type,
                    'timestamp': timestamp,
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
        if not self.is_monitoring or self.is_paused:
            return
        if not IDLE_AVAILABLE:
            return

        idle_seconds = self.idle_detector.get_idle_seconds()
        threshold = CONFIG['IDLE_DETECTION_THRESHOLD_SECONDS']
        ceiling = CONFIG['IDLE_SANITY_CEILING_SECONDS']

        if idle_seconds >= ceiling:
            print(f"[Idle] Reported idle {int(idle_seconds)}s exceeds ceiling "
                  f"{ceiling}s — detector likely frozen. Forcing not-idle + recovery.")
            if self.is_idle:
                self.is_idle = False
                self.send_idle_event('end', datetime.now(timezone.utc))
            self.idle_detector.last_input_time = time.time()
            try:
                self.idle_detector.ensure_alive()
            except Exception as e:
                print(f"[Idle] ensure_alive failed: {e}")
            return

        if idle_seconds >= threshold and not self.is_idle:
            idle_start_utc = datetime.now(timezone.utc) - timedelta(seconds=int(idle_seconds))
            print(f"[Idle] User went idle ({int(idle_seconds)}s since last input)")
            self.is_idle = True
            self.send_idle_event('start', idle_start_utc)
        elif idle_seconds < threshold and self.is_idle:
            print(f"[Idle] User returned to activity")
            self.is_idle = False
            self.send_idle_event('end', datetime.now(timezone.utc))

    def capture_watchdog(self):
        if not self.is_monitoring or self.is_paused:
            return
        interval = CONFIG['CAPTURE_INTERVAL_MINUTES'] * 60
        max_gap = interval * 2 + 30
        last = self.last_capture_success or 0
        gap = time.time() - last
        if gap < max_gap:
            return
        print(f"[Watchdog] No successful capture in {int(gap)}s "
              f"(limit {max_gap}s) — forcing recovery.")
        try:
            idle_now = self.idle_detector.get_idle_seconds()
            if self.is_idle and idle_now >= CONFIG['IDLE_SANITY_CEILING_SECONDS']:
                self.is_idle = False
                self.idle_detector.last_input_time = time.time()
                self.idle_detector.ensure_alive()
        except Exception as e:
            print(f"[Watchdog] idle recovery failed: {e}")
        self.capture_and_upload()

    def capture_and_upload(self):
        if not self.is_monitoring or self.is_paused:
            print("[Capture] Skipping (not monitoring or paused)")
            return
        if self.is_idle:
            try:
                idle_now = self.idle_detector.get_idle_seconds()
            except Exception:
                idle_now = 0
            if idle_now < CONFIG['IDLE_SANITY_CEILING_SECONDS']:
                print("[Capture] Skipping (user is idle)")
                return
            print(f"[Capture] is_idle set but idle reading {int(idle_now)}s is "
                  f"implausible — capturing anyway (detector may be frozen).")
        try:
            image_bytes = self.capture_screenshot()
            result = self.upload_screenshot(image_bytes)

            if result.get('success'):
                self.last_capture_success = time.time()
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
        self.idle_detector.start()
        schedule.every(CONFIG['IDLE_CHECK_INTERVAL_SECONDS']).seconds.do(self.check_idle)
        schedule.every(CONFIG['CAPTURE_INTERVAL_MINUTES']).minutes.do(self.capture_and_upload)
        threading.Timer(5.0, self.capture_and_upload).start()
        self.last_capture_success = time.time()
        schedule.every(1).minutes.do(self.capture_watchdog)
        if self.on_status_changed:
            self.on_status_changed()
        print("[Monitor] Started")

    def stop_monitoring(self):
        if not self.is_monitoring:
            return
        print("[Monitor] Stopping...")
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
        self.stop_monitoring()
        self.credentials = None
        self.clear_saved_credentials()
        schedule.clear()

    def run_scheduler(self):
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
                if consecutive_errors > 10:
                    time.sleep(5)
            try:
                time.sleep(1)
            except Exception:
                pass


# Global instance
monitor = ScreenshotMonitor()

if __name__ == '__main__':
    if monitor.credentials:
        monitor.sync_with_tracker()
        schedule.every(CONFIG['STATUS_CHECK_SECONDS']).seconds.do(monitor.sync_with_tracker)

    monitor.run_scheduler()
