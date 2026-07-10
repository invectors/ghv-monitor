#!/usr/bin/env python3
"""
GHV Monitor — GUI
Dark theme redesign using customtkinter.
"""

import tkinter as tk
import customtkinter as ctk
import threading
import math
from datetime import datetime
from main import monitor, CONFIG

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = "#0d0d0d"
BG_CARD     = "#181818"
BG_INPUT    = "#111111"
BG_HEADER   = "#071407"   # very dark green for the logo zone
GREEN       = "#05ac13"
GREEN_DIM   = "#037d0e"
GREEN_GLOW  = "#19c728"
TEXT        = "#ffffff"
TEXT_SUB    = "#aaaaaa"
TEXT_MUTED  = "#555555"
BORDER      = "#2a2a2a"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


class MonitorGUI:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("GHV Monitor")
        self.root.geometry("380x600")
        self.root.resizable(False, False)
        self.root.configure(fg_color=BG)

        # Centre on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  - 380) // 2
        y = (self.root.winfo_screenheight() - 600) // 2
        self.root.geometry(f"380x600+{x}+{y}")

        # These fire from the background scheduler thread (capture_and_upload,
        # start_monitoring, etc. all run there). Tkinter widgets are not
        # thread-safe — touching them off the main thread can silently no-op
        # (this is why "Last Capture" could freeze at "Never" even while
        # real captures were landing successfully). root.after(0, ...)
        # marshals the call onto the main thread where it's safe.
        monitor.on_status_changed      = lambda: self.root.after(0, self.update_status)
        monitor.on_screenshot_captured = lambda status: self.root.after(0, lambda: self.on_screenshot(status))
        monitor.on_update_required     = self._on_update_required

        self._show_login()
        threading.Thread(target=monitor.run_scheduler, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_update_required(self, min_version: str):
        """Called from the monitor thread — marshal to the UI thread."""
        self.root.after(0, lambda: self._show_force_update(min_version))

    def _show_force_update(self, min_version: str):
        """Blocking overlay that prevents use until the user updates."""
        # Only show once — avoid stacking on every 30-second sync
        if hasattr(self, '_update_dialog') and self._update_dialog.winfo_exists():
            return

        from version import VERSION
        import webbrowser

        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Update Required")
        dlg.geometry("340x280")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.grab_set()          # block all other interaction
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent close

        # Centre over parent
        self.root.update_idletasks()
        px = self.root.winfo_x(); py = self.root.winfo_y()
        dlg.geometry(f"340x280+{px+20}+{py+160}")
        self._update_dialog = dlg

        # Content
        ctk.CTkLabel(dlg, text="🔄", font=self._font(36)).pack(pady=(28, 0))
        ctk.CTkLabel(dlg, text="Update Required",
                     font=self._font(16, "bold"), text_color=TEXT).pack(pady=(6, 0))
        ctk.CTkLabel(dlg,
                     text=f"Version {min_version} is required.\nYou are running {VERSION}.",
                     font=self._font(12), text_color=TEXT_SUB,
                     justify="center").pack(pady=(8, 0))
        ctk.CTkLabel(dlg,
                     text="Please install the latest build\nto continue using GHV Monitor.",
                     font=self._font(11), text_color=TEXT_MUTED,
                     justify="center").pack(pady=(4, 0))

        def _open_download():
            webbrowser.open(
                "https://github.com/invectors/ghv-monitor/releases/latest")

        ctk.CTkButton(dlg, text="⬇  Download Update",
                      height=44, corner_radius=10,
                      fg_color=GREEN, hover_color=GREEN_DIM,
                      font=self._font(13, "bold"), text_color=TEXT,
                      command=_open_download).pack(
                          fill="x", padx=28, pady=(18, 0))
        ctk.CTkButton(dlg, text="Quit App",
                      height=36, corner_radius=10,
                      fg_color="transparent", border_color=BORDER, border_width=1,
                      hover_color="#1a1a1a", text_color=TEXT_MUTED,
                      font=self._font(12),
                      command=self._on_close).pack(
                          fill="x", padx=28, pady=(8, 0))

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────
    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _on_close(self):
        monitor.stop_monitoring()
        self.root.destroy()

    def _font(self, size, weight="normal"):
        return ctk.CTkFont(family="Poppins" if self._has_poppins() else "Segoe UI",
                           size=size, weight=weight)

    _poppins_checked = None
    def _has_poppins(self):
        if MonitorGUI._poppins_checked is None:
            try:
                tk.font.families(self.root)
                MonitorGUI._poppins_checked = "Poppins" in tk.font.families(self.root)
            except Exception:
                MonitorGUI._poppins_checked = False
        return MonitorGUI._poppins_checked

    # ─────────────────────────────────────────────────────────────────────────
    # LOGIN SCREEN
    # ─────────────────────────────────────────────────────────────────────────
    def _show_login(self):
        self._clear()
        self.root.geometry("380x600")

        # ── Logo zone ─────────────────────────────────────────────────────
        logo = ctk.CTkFrame(self.root, height=190, fg_color=BG_HEADER,
                            corner_radius=0)
        logo.pack(fill="x")
        logo.pack_propagate(False)

        ctk.CTkLabel(logo, text="GHV", font=self._font(44, "bold"),
                     text_color=TEXT).pack(pady=(28, 0))
        ctk.CTkLabel(logo, text="Monitor", font=self._font(18),
                     text_color=GREEN).pack()
        ctk.CTkLabel(logo, text="Employee Login", font=self._font(12),
                     text_color=TEXT_SUB).pack(pady=(6, 0))

        # ── Form zone ─────────────────────────────────────────────────────
        form = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        form.pack(fill="both", expand=True, padx=32)

        ctk.CTkLabel(form, text="Username", font=self._font(11, "bold"),
                     text_color=TEXT_SUB, anchor="w").pack(fill="x", pady=(24, 4))
        self._user_entry = ctk.CTkEntry(
            form, placeholder_text="Enter your username",
            height=44, corner_radius=8,
            fg_color=BG_INPUT, border_color=BORDER, border_width=1,
            text_color=TEXT, placeholder_text_color=TEXT_MUTED,
            font=self._font(13))
        self._user_entry.pack(fill="x")

        if monitor.credentials and monitor.credentials.get("username"):
            self._user_entry.insert(0, monitor.credentials["username"])

        ctk.CTkLabel(form, text="Password", font=self._font(11, "bold"),
                     text_color=TEXT_SUB, anchor="w").pack(fill="x", pady=(14, 4))

        # Password row with show/hide toggle
        pw_row = ctk.CTkFrame(form, fg_color="transparent")
        pw_row.pack(fill="x")
        self._pw_entry = ctk.CTkEntry(
            pw_row, placeholder_text="Enter your password",
            height=44, corner_radius=8, show="•",
            fg_color=BG_INPUT, border_color=BORDER, border_width=1,
            text_color=TEXT, placeholder_text_color=TEXT_MUTED,
            font=self._font(13))
        self._pw_entry.pack(side="left", fill="x", expand=True)
        self._pw_visible = False
        self._eye_btn = ctk.CTkButton(
            pw_row, text="👁", width=40, height=44,
            fg_color=BG_INPUT, hover_color=BG_CARD, corner_radius=8,
            text_color=TEXT_SUB, font=self._font(14),
            command=self._toggle_pw)
        self._eye_btn.pack(side="left", padx=(4, 0))

        self._pw_entry.bind("<Return>", lambda e: self._do_login())

        # Login button
        self._login_btn = ctk.CTkButton(
            form, text="Login", height=48, corner_radius=10,
            fg_color=GREEN, hover_color=GREEN_DIM,
            font=self._font(14, "bold"), text_color=TEXT,
            command=self._do_login)
        self._login_btn.pack(fill="x", pady=(18, 0))

        # Secure Access footer
        sep = ctk.CTkFrame(form, height=1, fg_color=BORDER)
        sep.pack(fill="x", pady=(20, 12))
        ctk.CTkLabel(form, text="🔒  Secure Access", font=self._font(11, "bold"),
                     text_color=GREEN).pack()
        ctk.CTkLabel(form, text="Enter your GoHireVirtual hub credentials",
                     font=self._font(10), text_color=TEXT_MUTED).pack(pady=(2, 0))

        self._user_entry.focus()

    def _toggle_pw(self):
        self._pw_visible = not self._pw_visible
        self._pw_entry.configure(show="" if self._pw_visible else "•")

    def _do_login(self):
        username = self._user_entry.get().strip()
        password = self._pw_entry.get()
        if not username or not password:
            self._login_btn.configure(text="Enter username & password")
            self.root.after(2000, lambda: self._login_btn.configure(text="Login"))
            return
        self._login_btn.configure(state="disabled", text="Signing in…")

        def _thread():
            result = monitor.login(username, password)
            self.root.after(0, lambda: self._handle_login(result))

        threading.Thread(target=_thread, daemon=True).start()

    def _handle_login(self, result):
        if result["success"]:
            self._show_status()
        else:
            msg = result.get("message", "Invalid credentials")
            self._login_btn.configure(state="normal", text=f"✕  {msg[:38]}")
            self.root.after(3000, lambda: self._login_btn.configure(text="Login"))

    # ─────────────────────────────────────────────────────────────────────────
    # STATUS SCREEN
    # ─────────────────────────────────────────────────────────────────────────
    def _show_status(self):
        self._clear()
        self.root.geometry("380x600")

        # ── Header ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self.root, height=60, fg_color=BG_CARD,
                           corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="Monitor Status", font=self._font(16, "bold"),
                     text_color=TEXT).place(x=20, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="⎋  Logout", width=90, height=32,
                      corner_radius=8, fg_color="transparent",
                      border_color=BORDER, border_width=1,
                      hover_color="#2a2a2a", text_color=TEXT_SUB,
                      font=self._font(11), command=self._do_logout
                      ).place(relx=1, x=-20, rely=0.5, anchor="e")

        # ── Main status card ──────────────────────────────────────────────
        card = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        card.pack(fill="x", padx=20, pady=(16, 0))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=20, pady=(18, 12), fill="x")

        # Left: circular canvas indicator
        left = ctk.CTkFrame(inner, fg_color="transparent", width=88)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._ring_canvas = tk.Canvas(left, width=80, height=80,
                                      bg=BG_CARD, highlightthickness=0)
        self._ring_canvas.pack(anchor="center", expand=True)

        # Right: text block
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True, padx=(16, 0))

        self._status_title = ctk.CTkLabel(
            right, text="Not Active", font=self._font(15, "bold"),
            text_color=TEXT, anchor="w")
        self._status_title.pack(fill="x")

        self._status_sub = ctk.CTkLabel(
            right, text="Waiting for clock in",
            font=self._font(11), text_color=TEXT_SUB, anchor="w",
            wraplength=190)
        self._status_sub.pack(fill="x", pady=(2, 8))

        self._badge = ctk.CTkLabel(
            right, text="  OFFLINE  ", font=self._font(9, "bold"),
            fg_color="#2a2a2a", text_color=TEXT_MUTED,
            corner_radius=10, width=72, height=22)
        self._badge.pack(anchor="w")

        # ── How it works ──────────────────────────────────────────────────
        hw = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        hw.pack(fill="x", padx=20, pady=(16, 16))

        ctk.CTkLabel(hw, text="How it works", font=self._font(12, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(16, 8))

        for line in [
            "Automatically starts when you clock in",
            "Captures desktop on your assigned interval",
            "Pauses during lunch breaks",
            "Stops when you clock out",
        ]:
            row = ctk.CTkFrame(hw, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=3)
            ctk.CTkLabel(row, text="✓", font=self._font(11, "bold"),
                         text_color=GREEN, width=18).pack(side="left")
            ctk.CTkLabel(row, text=line, font=self._font(11),
                         text_color=TEXT_SUB, anchor="w").pack(side="left", padx=(6, 0))
        ctk.CTkFrame(hw, height=14, fg_color="transparent").pack()

        # ── Footer ────────────────────────────────────────────────────────
        foot = ctk.CTkFrame(self.root, fg_color="transparent")
        foot.pack(fill="x", pady=(14, 8))
        ctk.CTkLabel(foot, text="🛡  Secure. Private. Transparent.",
                     font=self._font(10, "bold"), text_color=TEXT_MUTED).pack()
        ctk.CTkLabel(foot, text="GoHireVirtual Monitoring System",
                     font=self._font(9), text_color="#333333").pack(pady=(2, 0))

        self.update_status()

    # ─────────────────────────────────────────────────────────────────────────
    # RING CANVAS
    # ─────────────────────────────────────────────────────────────────────────
    def _draw_ring(self, color):
        c = self._ring_canvas
        c.delete("all")
        cx, cy, r_out, r_in = 40, 40, 36, 26
        # Background ring
        c.create_oval(cx-r_out, cy-r_out, cx+r_out, cy+r_out,
                      outline="#2a2a2a", width=8)
        # Full coloured ring (360°)
        c.create_arc(cx-r_out, cy-r_out, cx+r_out, cy+r_out,
                     start=90, extent=-360,
                     outline=color, width=8, style="arc")
        # Centre play icon
        c.create_text(cx, cy, text="▶", fill=color,
                      font=("Segoe UI Symbol", 16))

    # ─────────────────────────────────────────────────────────────────────────
    # STATUS UPDATE
    # ─────────────────────────────────────────────────────────────────────────
    def update_status(self):
        if not hasattr(self, "_status_title"):
            return

        interval = CONFIG.get("CAPTURE_INTERVAL_MINUTES", 10)

        if monitor.is_monitoring:
            if monitor.is_paused:
                self._draw_ring("#eab308")
                self._status_title.configure(text="On Lunch Break")
                self._status_sub.configure(text="Monitoring paused. Resumes when you return.")
                self._badge.configure(text="  PAUSED  ",
                                      fg_color="#2d2600", text_color="#eab308")
            else:
                self._draw_ring(GREEN_GLOW)
                self._status_title.configure(text="Monitoring Active")
                self._status_sub.configure(
                    text=f"Capturing screenshots every {interval} min")
                self._badge.configure(text="  ACTIVE  ",
                                      fg_color="#071407", text_color=GREEN_GLOW)
        else:
            self._draw_ring("#333333")
            self._status_title.configure(text="Not Active")
            self._status_sub.configure(text="Waiting for you to clock in")
            self._badge.configure(text="  OFFLINE  ",
                                  fg_color="#1a1a1a", text_color=TEXT_MUTED)

    def on_screenshot(self, status):
        self.update_status()

    # ─────────────────────────────────────────────────────────────────────────
    # LOGOUT
    # ─────────────────────────────────────────────────────────────────────────
    def _do_logout(self):
        monitor.logout()
        self._show_login()

    # ─────────────────────────────────────────────────────────────────────────
    # RUN
    # ─────────────────────────────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = MonitorGUI()
    app.run()
