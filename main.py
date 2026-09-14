#!/usr/bin/env python3
"""
GHV Monitor — Core
Handles screenshot capture, idle detection, clock state sync,
clock actions (in/out/lunch), and activity window tracking.
"""

import os
import sys
import time
import json
import threading
import schedule
from datetime import datetime, timezone, timedelta
from pathlib import Path
from version import VERSION

import mss
import requests
from PIL import Image
from io import BytesIO
import base64

# ── File logging for packaged builds ─────────────────────────────────────────
if getattr(sys, 'frozen', False):
    try:
        _log_dir  = Path.home() / '.config' / 'GHV-Monitor'
        _log_dir.mkdir(parents=True, exist_ok=True)
        _log_path = _log_dir / 'ghv-monitor.log'
        if _log_path.exists() and _log_path.stat().st_size > 5 * 1024 * 1024:
            _log_path.unlink()
        _log_file = open(_log_path, 'a', buffering=1, encoding='utf-8')
        sys.stdout = _log_file
        sys.stderr = _log_file
        print(f"\n{'='*60}")
        print(f"[Startup] GHV Monitor v{VERSION} — log file: {_log_path}")
        print(f"{'='*60}")
    except Exception:
        pass

IS_MACOS   = sys.platform == 'darwin'
IS_WINDOWS = sys.platform == 'win32'

# ── macOS idle detection (Quartz) ────────────────────────────────────────────
MACOS_IDLE_AVAILABLE  = False
PYNPUT_AVAILABLE      = False
if IS_MACOS:
    try:
        from Quartz import (
            CGEventSourceSecondsSinceLastEventType,
            kCGEventSourceStateHIDSystemState,
            kCGAnyInputEventType,
        )
        MACOS_IDLE_AVAILABLE = True
    except ImportError:
        pass
try:
    from pynput import keyboard, mouse
    PYNPUT_AVAILABLE = True
except ImportError:
    pass

IDLE_AVAILABLE = MACOS_IDLE_AVAILABLE or (PYNPUT_AVAILABLE and not IS_MACOS)

# ── CONFIG ────────────────────────────────────────────────────────────────────
CONFIG = {
    'UPLOAD_URL':   'https://hub.gohirevirtual.net/api/screenshots/upload.php',
    'STATUS_URL':   'https://hub.gohirevirtual.net/api/screenshots/status.php',
    'IDLE_URL':     'https://hub.gohirevirtual.net/api/screenshots/idle.php',
    'CLOCK_URL':    'https://hub.gohirevirtual.net/api/screenshots/clock.php',
    'ACTIVITY_URL': 'https://hub.gohirevirtual.net/api/screenshots/activity.php',
    'CAPTURE_INTERVAL_MINUTES':      10,
    'STATUS_CHECK_SECONDS':          30,
    'IDLE_CHECK_INTERVAL_SECONDS':   15,
    'IDLE_DETECTION_THRESHOLD_SECONDS': 300,
    'IDLE_SANITY_CEILING_SECONDS':   28800,
    'MAX_IMAGE_WIDTH':               1920,
    'IMAGE_QUALITY':                 75,
    'MAX_RETRY_ATTEMPTS':            3,
    'ACTIVITY_CHECK_SECONDS':        10,
    'ACTIVITY_FLUSH_SECONDS':        120,
}

# ─────────────────────────────────────────────────────────────────────────────
# ACTIVITY TRACKER — monitors which app/window is in focus and for how long
# ─────────────────────────────────────────────────────────────────────────────
class ActivityTracker:
    """
    Polls the active foreground window every ~10 seconds.
    When the window changes, it logs the previous app + duration.
    Collected logs are flushed periodically to the server.
    """

    def __init__(self):
        self._current_app   = None
        self._current_title = None
        self._session_start = None
        self._lock          = threading.Lock()
        self._pending       = []

    # ── Platform-specific window detection ────────────────────────────────
    def _active_window(self):
        """Returns (app_name, window_title) or (None, None) on failure."""
        try:
            if IS_MACOS:
                from AppKit import NSWorkspace
                info = NSWorkspace.sharedWorkspace().activeApplication()
                app  = info.get('NSApplicationName', '') if info else ''
                return app, ''
            elif IS_WINDOWS:
                import win32gui, win32process
                hwnd  = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    import psutil
                    app = psutil.Process(pid).name()
                except Exception:
                    app = ''
                return app, title
        except Exception as e:
            print(f"[Activity] Window detection error: {e}")
        return None, None

    # ── Called by scheduler every ACTIVITY_CHECK_SECONDS ─────────────────
    def check(self):
        app_name, title = self._active_window()
        if not app_name:
            return
        now = datetime.now(timezone.utc)
        with self._lock:
            if app_name != self._current_app or title != self._current_title:
                if self._current_app and self._session_start:
                    duration = int((now - self._session_start).total_seconds())
                    if duration >= 5:
                        self._pending.append({
                            'app_name':         self._current_app,
                            'window_title':     self._current_title or '',
                            'started_at':       self._session_start.strftime('%Y-%m-%d %H:%M:%S'),
                            'ended_at':         now.strftime('%Y-%m-%d %H:%M:%S'),
                            'duration_seconds': duration,
                        })
                self._current_app   = app_name
                self._current_title = title
                self._session_start = now

    def flush(self):
        """Return and clear pending log entries."""
        with self._lock:
            logs = list(self._pending)
            self._pending.clear()
            return logs


# ─────────────────────────────────────────────────────────────────────────────
# IDLE DETECTOR
# ─────────────────────────────────────────────────────────────────────────────
class IdleDetector:
    def __init__(self):
        self._last_input  = time.time()
        self._kb_listener = None
        self._ms_listener = None
        self._running     = False

    def _on_input(self, *_):
        self._last_input = time.time()

    def start(self):
        if self._running:
            return
        # Reset the idle clock to NOW so we don't inherit the creation-time
        # timestamp as "last input". Without this, if there's any gap between
        # __init__ and start() the detector immediately reports fake idle.
        self._last_input = time.time()
        self._running = True
        if IS_MACOS and MACOS_IDLE_AVAILABLE:
            print("[Idle] Detector started (macOS native Quartz)")
            return
        if PYNPUT_AVAILABLE and not IS_MACOS:
            try:
                self._kb_listener = keyboard.Listener(on_press=self._on_input)
                self._ms_listener = mouse.Listener(on_move=self._on_input,
                                                   on_click=self._on_input,
                                                   on_scroll=self._on_input)
                self._kb_listener.start()
                self._ms_listener.start()
                print("[Idle] Detector started (pynput)")
            except Exception as e:
                print(f"[Idle] pynput start failed: {e}")
                # pynput failed — reset again so the fallback timer starts
                # from now rather than from __init__ time
                self._last_input = time.time()

    def stop(self):
        self._running = False
        if self._kb_listener:
            try: self._kb_listener.stop()
            except Exception: pass
        if self._ms_listener:
            try: self._ms_listener.stop()
            except Exception: pass
        self._kb_listener = None
        self._ms_listener = None

    def seconds_idle(self) -> float:
        if IS_MACOS and MACOS_IDLE_AVAILABLE:
            try:
                return float(CGEventSourceSecondsSinceLastEventType(
                    kCGEventSourceStateHIDSystemState, kCGAnyInputEventType))
            except Exception:
                pass
        # On macOS without Quartz, pynput is not started (thread-safety +
        # Input Monitoring permission issues). Rather than falsely reporting
        # large idle times from the stale _last_input, assume the user is
        # active. This means idle detection is simply disabled on macOS
        # without Quartz — far safer than fake idle flags.
        if IS_MACOS:
            return 0.0
        return time.time() - self._last_input


# ─────────────────────────────────────────────────────────────────────────────
# SCREENSHOT MONITOR
# ─────────────────────────────────────────────────────────────────────────────
class ScreenshotMonitor:
    def __init__(self):
        # ── Auth ──────────────────────────────────────────────────────────
        self.credentials = None
        self._config_dir  = Path.home() / '.config' / 'GHV-Monitor'
        self._config_file = self._config_dir / 'config.json'
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._load_credentials()

        # ── Clock / shift state (synced from status.php) ──────────────────
        self.is_monitoring     = False
        self.is_paused         = False
        self.is_idle           = False
        self.server_capture_disabled = False

        # Values refreshed from status.php on each sync
        self.clocked_in    = False
        self.on_lunch      = False
        self.clock_in_time = None
        self.clock_in_time_utc = None
        self.lunch_out_time= None
        self.shift_timezone = 'UTC'   # VA's shift timezone from employee_shifts

        # Lunch budget (refreshed on every sync so app enforces without server round-trip)
        self.lunch_used_seconds      = 0
        self.lunch_limit_seconds     = 3600   # default 1 hr until first sync
        self.lunch_remaining_seconds = 3600
        self.lunch_exhausted         = False

        self.upload_queue       = []
        self.last_capture_success = None
        self._capture_job       = None
        self.on_update_required = None

        # ── Callbacks (all called from bg thread → marshal in GUI) ────────
        self.on_status_changed     = None
        self.on_screenshot_captured= None
        self.on_idle_started       = None   # NEW — VA went idle
        self.on_idle_ended         = None   # NEW — VA returned from idle

        # ── Sub-systems ───────────────────────────────────────────────────
        self.idle_detector    = IdleDetector()
        self.activity_tracker = ActivityTracker()

        self._load_queue()

    # ── Config / credentials ─────────────────────────────────────────────
    def _load_credentials(self):
        print(f"[Config] Config directory: {self._config_dir}")
        print(f"[Config] Config file: {self._config_file}")
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            print(f"[Config] Directory verified and writable: {self._config_dir}")
        except Exception as e:
            print(f"[Config] Warning: could not create config dir: {e}")
        print(f"[Config] Loading from: {self._config_file}")
        if self._config_file.exists():
            print(f"[Config] File exists: True")
            try:
                content = self._config_file.read_text(encoding='utf-8')
                print(f"[Config] File content length: {len(content)}")
                data = json.loads(content)
                if data.get('username') and data.get('password'):
                    self.credentials = data
                    print(f"[Config] Loaded credentials: True")
                    print(f"[Config] Username: {data['username']}")
                else:
                    print("[Config] Credentials incomplete")
            except Exception as e:
                print(f"[Config] Failed to load: {e}")
        else:
            print("[Config] File exists: False")
            print("[Config] No config file found")

    def _save_credentials(self, username, password):
        data = {'username': username, 'password': password}
        tmp  = self._config_file.with_suffix('.tmp')
        try:
            print(f"[Config] Saving to: {self._config_file}")
            print(f"[Config] Current credentials: {data}")
            tmp.write_text(json.dumps(data), encoding='utf-8')
            print(f"[Config] Temp file written: {tmp}")
            tmp.rename(self._config_file)
            print(f"[Config] Renamed to: {self._config_file}")
            print(f"[Config] Verified write: {len(self._config_file.read_text())} bytes")
            print("[Config] Saved successfully")
        except Exception as e:
            print(f"[Config] Failed to save: {e}")

    def _clear_credentials(self):
        self.credentials = None
        try:
            if self._config_file.exists():
                self._config_file.unlink()
        except Exception:
            pass

    def _load_queue(self):
        qf = self._config_dir / 'queue.json'
        if qf.exists():
            try:
                self.upload_queue = json.loads(qf.read_text(encoding='utf-8'))
                print(f"[Queue] Loaded {len(self.upload_queue)} items")
            except Exception:
                pass

    def _save_queue(self):
        try:
            qf = self._config_dir / 'queue.json'
            qf.write_text(json.dumps(self.upload_queue), encoding='utf-8')
        except Exception:
            pass

    # ── Auth header ──────────────────────────────────────────────────────
    def _auth_headers(self):
        if not self.credentials:
            return {}
        creds = f"{self.credentials['username']}:{self.credentials['password']}"
        return {'Authorization': f'Bearer {creds}'}

    # ── Login ────────────────────────────────────────────────────────────
    def login(self, username, password):
        try:
            print(f"[Login] Attempting login for {username}...")
            print(f"[Login] URL: {CONFIG['STATUS_URL']}")
            creds = f"{username}:{password}"
            resp  = requests.post(
                CONFIG['STATUS_URL'],
                json={'username': username, 'password': password},
                headers={'Authorization': f'Bearer {creds}'},
                timeout=(10, 30)
            )
            print(f"[Login] Response code: {resp.status_code}")
            data = resp.json()
            print(f"[Login] Response: {data}")
            if data.get('success'):
                self.credentials = {'username': username, 'password': password}
                self._save_credentials(username, password)
                return {'success': True}
            return {'success': False, 'message': data.get('message', 'Invalid credentials')}
        except Exception as e:
            print(f"[Login] Error: {e}")
            return {'success': False, 'message': 'Connection error. Check your internet.'}

    def logout(self):
        self.stop_monitoring()
        schedule.clear()  # Kill the sync job too — user has logged out
        self._clear_credentials()

    # ── Clock action (NEW) ────────────────────────────────────────────────
    def clock_action(self, action):
        """
        Sends a clock action (clock_in/clock_out/lunch_out/lunch_in)
        to the hub via the new Bearer-auth clock API endpoint.
        Returns {'success': bool, 'message': str}.
        """
        if not self.credentials:
            return {'success': False, 'message': 'Not logged in'}
        try:
            print(f"[Clock] Sending action: {action} → {CONFIG['CLOCK_URL']}")
            resp = requests.post(
                CONFIG['CLOCK_URL'],
                json={'action': action},
                headers={**self._auth_headers(), 'Content-Type': 'application/json'},
                timeout=(10, 30)
            )
            print(f"[Clock] HTTP {resp.status_code} — {resp.text[:300]}")
            data = resp.json()
            if data.get('success'):
                # Immediately sync so UI reflects new state
                self.sync_with_tracker()
            return data
        except Exception as e:
            print(f"[Clock] Error: {e}")
            return {'success': False, 'message': f'Connection error: {e}'}

    # ── Screen capture ───────────────────────────────────────────────────
    def capture_screenshot(self):
        try:
            print("[Screenshot] Capturing desktop...")

            # ── Screen Recording permission preflight (macOS) ────────────
            if IS_MACOS:
                try:
                    from Quartz import (CGPreflightScreenCaptureAccess,
                                        CGRequestScreenCaptureAccess)
                    _has_perm = bool(CGPreflightScreenCaptureAccess())
                    print(f"[Permission] Screen Recording access: {_has_perm}")
                    if not _has_perm:
                        print(f"[Permission] Running from: {sys.executable}")
                        print("[Permission] MISSING — requesting access")
                        CGRequestScreenCaptureAccess()
                except ImportError:
                    pass
                except Exception as e:
                    print(f"[Permission] Check failed: {e}")

            if IS_MACOS:
                import tempfile, subprocess, os as _os
                img = None
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as _f:
                    _tmp = _f.name
                try:
                    _bin = '/usr/sbin/screencapture'
                    if not _os.path.exists(_bin):
                        _bin = 'screencapture'
                    _res = subprocess.run(
                        [_bin, '-x', '-t', 'png', _tmp],
                        capture_output=True, timeout=15
                    )
                    if _res.returncode != 0:
                        print(f"[Screenshot] screencapture rc={_res.returncode} "
                              f"stderr={_res.stderr.decode(errors='replace')[:300]}")
                    elif _os.path.getsize(_tmp) == 0:
                        print("[Screenshot] screencapture produced empty file")
                    else:
                        img = Image.open(_tmp).convert('RGB')
                except Exception as e:
                    print(f"[Screenshot] screencapture failed: {e}")
                finally:
                    try: _os.unlink(_tmp)
                    except OSError: pass
                if img is None:
                    print("[Screenshot] Falling back to mss")
                    with mss.mss() as sct:
                        screenshot = sct.grab(sct.monitors[0])
                        img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
            else:
                with mss.mss() as sct:
                    screenshot = sct.grab(sct.monitors[0])
                    img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)

            if img.width > CONFIG['MAX_IMAGE_WIDTH']:
                ratio  = CONFIG['MAX_IMAGE_WIDTH'] / img.width
                img    = img.resize((CONFIG['MAX_IMAGE_WIDTH'], int(img.height * ratio)),
                                    Image.Resampling.LANCZOS)
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=CONFIG['IMAGE_QUALITY'])
            img_bytes = buf.getvalue()
            print(f"[Screenshot] Captured ({len(img_bytes)} bytes)")
            return img_bytes
        except Exception as e:
            print(f"[Screenshot] Error: {e}")
            raise

    # ── Upload screenshot ────────────────────────────────────────────────
    def upload_screenshot(self, image_bytes):
        try:
            print("[Upload] Uploading screenshot...")
            resp = requests.post(
                CONFIG['UPLOAD_URL'],
                data=base64.b64encode(image_bytes).decode(),
                headers={**self._auth_headers(), 'Content-Type': 'text/plain'},
                timeout=(15, 60)
            )
            print(f"[Upload] Response code: {resp.status_code}")
            if resp.status_code == 200:
                print("[Upload] Success")
                return True
            print(f"[Upload] Failed: {resp.text[:200]}")
            return False
        except Exception as e:
            print(f"[Upload] Error: {e}")
            return False

    # ── Activity flush (NEW) ─────────────────────────────────────────────
    def flush_activity(self):
        """Send buffered activity logs to the server."""
        if not self.credentials:
            return
        logs = self.activity_tracker.flush()
        if not logs:
            return
        try:
            resp = requests.post(
                CONFIG['ACTIVITY_URL'],
                json={'logs': logs},
                headers={**self._auth_headers(), 'Content-Type': 'application/json'},
                timeout=(10, 30)
            )
            print(f"[Activity] Flushed {len(logs)} logs → {resp.status_code}")
        except Exception as e:
            print(f"[Activity] Flush error: {e}")

    # ── Status sync ──────────────────────────────────────────────────────
    def check_status(self):
        try:
            resp = requests.get(
                CONFIG['STATUS_URL'],
                headers=self._auth_headers(),
                timeout=(15, 30)
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                return {'success': False, 'error': 'auth_failed',
                        'session_expired': resp.json().get('session_expired', False),
                        'reason': resp.json().get('reason', '')}
            return None
        except Exception as e:
            print(f"[Status] Request error: {e}")
            return None

    @staticmethod
    def _parse_version(v: str):
        try:
            return tuple(int(x) for x in v.lstrip('v').split('.'))
        except (ValueError, AttributeError):
            return (0, 0, 0)

    def _reschedule_capture(self, new_interval_minutes):
        if not self.is_monitoring:
            CONFIG['CAPTURE_INTERVAL_MINUTES'] = new_interval_minutes
            return
        if new_interval_minutes == CONFIG['CAPTURE_INTERVAL_MINUTES']:
            if self._capture_job is not None and self._capture_job in schedule.jobs:
                return
            print(f"[Monitor] Capture job missing, recreating at {new_interval_minutes}m")
        print(f"[Monitor] Capture interval: "
              f"{CONFIG['CAPTURE_INTERVAL_MINUTES']}m → {new_interval_minutes}m")
        CONFIG['CAPTURE_INTERVAL_MINUTES'] = new_interval_minutes
        if self._capture_job is not None:
            schedule.cancel_job(self._capture_job)
            self._capture_job = None
        self._capture_job = schedule.every(new_interval_minutes).minutes.do(
            self.capture_and_upload).tag('monitoring')
        print(f"[Monitor] Rescheduled capture every {new_interval_minutes}m")

    def sync_with_tracker(self):
        print("[Sync] Checking status...")
        try:
            status = self.check_status()
            if status is None:
                print("[Sync] No response — keeping current state")
                return

            if not status.get('success'):
                if status.get('session_expired') or status.get('error') == 'auth_failed':
                    reason = status.get('reason', '')
                    if reason == 'force_logout':
                        print("[Sync] Force logout — clearing credentials")
                        self._clear_credentials()
                    if self.is_monitoring:
                        self.stop_monitoring()
                    if self.on_status_changed:
                        self.on_status_changed()
                return

            print(f"[Sync] Status: active={status.get('active')}, "
                  f"clocked_in={status.get('clocked_in')}, "
                  f"on_lunch={status.get('on_lunch')}")

            # ── Update shift state for GUI ─────────────────────────────
            self.clocked_in          = bool(status.get('clocked_in'))
            self.on_lunch            = bool(status.get('on_lunch'))
            self.clock_in_time       = status.get('clock_in_time')
            self.clock_in_time_utc   = status.get('clock_in_time_utc')
            self.lunch_out_time      = status.get('lunch_out_time')
            self.shift_timezone      = status.get('shift_timezone') or 'UTC'
            self.lunch_used_seconds  = int(status.get('lunch_used_seconds', 0))
            self.lunch_limit_seconds = int(status.get('lunch_limit_seconds', 3600))
            self.lunch_remaining_seconds = int(status.get('lunch_remaining_seconds', 3600))
            self.lunch_exhausted     = bool(status.get('lunch_exhausted', False))
            self.server_capture_disabled = (status.get('reason') == 'disabled')

            # Store session info for elapsed timer
            self._last_session_info  = status.get('session_info')

            # ── Capture interval override ──────────────────────────────
            srv_interval = status.get('capture_interval_minutes')
            try:
                srv_interval = int(float(srv_interval)) if srv_interval is not None else None
            except (TypeError, ValueError):
                srv_interval = None
            if srv_interval and srv_interval > 0:
                self._reschedule_capture(srv_interval)

            # ── Force-update check ─────────────────────────────────────
            min_ver = status.get('min_app_version', '').strip()
            if min_ver and self._parse_version(min_ver) > self._parse_version(VERSION):
                print(f"[Update] Server requires {min_ver}, running {VERSION}")
                if self.on_update_required:
                    self.on_update_required(min_ver)

            # ── Monitoring state ───────────────────────────────────────
            if status.get('active') and status.get('clocked_in') and not status.get('on_lunch'):
                if not self.is_monitoring:
                    print("[Sync] Starting monitoring (clocked in)")
                    self.start_monitoring()
                elif self.is_paused:
                    self.resume_monitoring()
            elif status.get('on_lunch'):
                if self.is_monitoring and not self.is_paused:
                    self.pause_monitoring()
            else:
                if self.is_monitoring:
                    print("[Sync] Stopping monitoring (server confirmed clocked out)")
                    self.stop_monitoring()

            if self.on_status_changed:
                self.on_status_changed()

        except Exception as e:
            print(f"[Sync] Unexpected error: {e}")
            import traceback
            traceback.print_exc()

    # ── Idle events ──────────────────────────────────────────────────────
    def send_idle_event(self, event_type, ts):
        if not self.credentials:
            return
        try:
            payload = {
                'event':     event_type,
                'timestamp': ts.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'idle_type': 'idle',
            }
            requests.post(CONFIG['IDLE_URL'],
                          json=payload,
                          headers={**self._auth_headers(),
                                   'Content-Type': 'application/json'},
                          timeout=(10, 30))
            print(f"[Idle] {event_type} event sent (timestamp UTC: "
                  f"{ts.strftime('%Y-%m-%d %H:%M:%S')})")
        except Exception as e:
            print(f"[Idle] Event send error: {e}")

    def check_idle(self):
        try:
            if not self.is_monitoring:
                return
            idle_now = self.idle_detector.seconds_idle()
            threshold = CONFIG['IDLE_DETECTION_THRESHOLD_SECONDS']
            ceiling   = CONFIG['IDLE_SANITY_CEILING_SECONDS']

            if idle_now < threshold and self.is_idle:
                print(f"[Idle] User returned to activity")
                self.is_idle = False
                ts = datetime.now(timezone.utc)
                self.send_idle_event('end', ts)
                if self.on_idle_ended:
                    self.on_idle_ended()
                if self.on_status_changed:
                    self.on_status_changed()
                return

            if idle_now >= threshold and not self.is_idle:
                if idle_now < ceiling:
                    print(f"[Idle] User went idle ({idle_now:.0f}s since last input)")
                    self.is_idle = True
                    ts = datetime.now(timezone.utc) - timedelta(seconds=idle_now - threshold)
                    self.send_idle_event('start', ts)
                    if self.on_idle_started:
                        self.on_idle_started(idle_now)
                    if self.on_status_changed:
                        self.on_status_changed()
        except Exception as e:
            print(f"[Idle] Check error: {e}")

    # ── Capture and upload ───────────────────────────────────────────────
    def capture_watchdog(self):
        if not self.is_monitoring or self.is_paused or self.server_capture_disabled:
            return
        try:
            interval  = CONFIG['CAPTURE_INTERVAL_MINUTES'] * 60
            max_gap   = interval * 2 + 30
            if (self.last_capture_success
                    and (time.time() - self.last_capture_success) > max_gap):
                print("[Watchdog] Capture seems stalled, forcing...")
                threading.Thread(target=self.capture_and_upload, daemon=True).start()
        except Exception as e:
            print(f"[Watchdog] Error: {e}")

    def capture_and_upload(self):
        if not self.is_monitoring or self.is_paused:
            print("[Capture] Skipping (not monitoring or paused)")
            return
        if self.server_capture_disabled:
            print("[Capture] Skipping (admin disabled capture for this user)")
            return
        try:
            image_bytes = self.capture_screenshot()
            if image_bytes:
                ok = self.upload_screenshot(image_bytes)
                if ok:
                    self.last_capture_success = time.time()
                    print(f"[Capture] Success — uploaded {len(image_bytes)} bytes")
                    if self.on_screenshot_captured:
                        self.on_screenshot_captured('success')
                else:
                    self.upload_queue.append({
                        'data': base64.b64encode(image_bytes).decode(),
                        'retry_count': 0,
                        'timestamp': datetime.now().isoformat()
                    })
                    self._save_queue()
                    if self.on_screenshot_captured:
                        self.on_screenshot_captured('queued')
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
                image_bytes = base64.b64decode(item['data'])
                ok = self.upload_screenshot(image_bytes)
                if not ok:
                    item['retry_count'] = item.get('retry_count', 0) + 1
                    if item['retry_count'] < CONFIG['MAX_RETRY_ATTEMPTS']:
                        items_to_retry.append(item)
            except Exception:
                item['retry_count'] = item.get('retry_count', 0) + 1
                if item['retry_count'] < CONFIG['MAX_RETRY_ATTEMPTS']:
                    items_to_retry.append(item)
        self.upload_queue = items_to_retry
        self._save_queue()

    # ── Monitoring lifecycle ─────────────────────────────────────────────
    def start_monitoring(self):
        if self.is_monitoring:
            return
        print("[Monitor] Starting...")
        self.is_monitoring = True
        self.is_paused     = False

        self._capture_job = schedule.every(
            CONFIG['CAPTURE_INTERVAL_MINUTES']).minutes.do(
            self.capture_and_upload).tag('monitoring')
        threading.Timer(5.0, self.capture_and_upload).start()
        print(f"[Monitor] Capture job scheduled every {CONFIG['CAPTURE_INTERVAL_MINUTES']}m")

        self.last_capture_success = time.time()
        schedule.every(1).minutes.do(self.capture_watchdog).tag('monitoring')

        try:
            self.idle_detector.start()
            schedule.every(CONFIG['IDLE_CHECK_INTERVAL_SECONDS']).seconds.do(
                self.check_idle).tag('monitoring')
            print("[Monitor] Idle detection started")
        except Exception as e:
            print(f"[Monitor] Idle detection failed (continuing): {e}")

        schedule.every(CONFIG['ACTIVITY_CHECK_SECONDS']).seconds.do(
            self.activity_tracker.check).tag('monitoring')
        schedule.every(CONFIG['ACTIVITY_FLUSH_SECONDS']).seconds.do(
            self.flush_activity).tag('monitoring')
        print("[Monitor] Activity tracking started")

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
        self.flush_activity()
        self.is_monitoring = False
        self.is_paused     = False
        self._capture_job  = None

        # Stop idle detector so _running resets to False.
        # Without this, the next idle_detector.start() returns immediately
        # (thinks it's already running) and never resets _last_input —
        # causing permanent idle on the next clock-in cycle.
        self.idle_detector.stop()

        # Clear ONLY monitoring-tagged jobs (capture, watchdog, idle, activity).
        # The 'sync' job must survive so we can detect the next clock-in event
        # without requiring a manual action or full app restart.
        schedule.clear('monitoring')

        if self.on_status_changed:
            self.on_status_changed()
        print("[Monitor] Stopped")

    def pause_monitoring(self):
        if not self.is_monitoring or self.is_paused:
            return
        print("[Monitor] Pausing (lunch)...")
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

    # ── Scheduler loop ───────────────────────────────────────────────────
    def run_scheduler(self):
        print("[Scheduler] Loop started")
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                print(f"[Scheduler] Error: {e}")
            time.sleep(1)


monitor = ScreenshotMonitor()
