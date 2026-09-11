#!/usr/bin/env python3
"""
GHV Monitor — GUI
Dark theme. Status screen includes clock actions, elapsed timer, and idle banner.
"""

import tkinter as tk
import customtkinter as ctk
import threading
from datetime import datetime, timezone
from main import monitor, CONFIG

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = "#0d0d0d"
BG_CARD     = "#181818"
BG_INPUT    = "#111111"
BG_HEADER   = "#071407"
GREEN       = "#05ac13"
GREEN_DIM   = "#037d0e"
GREEN_GLOW  = "#19c728"
YELLOW      = "#eab308"
YELLOW_DIM  = "#a37e06"
RED         = "#e74c3c"
RED_DIM     = "#c0392b"
TEAL        = "#14b8a6"
TEAL_DIM    = "#0d8a7e"
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
        self.root.geometry("380x680")
        self.root.resizable(False, False)
        self.root.configure(fg_color=BG)

        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  - 380) // 2
        y = (self.root.winfo_screenheight() - 680) // 2
        self.root.geometry(f"380x680+{x}+{y}")

        # All callbacks marshal to main thread via root.after
        monitor.on_status_changed      = lambda: self.root.after(0, self.update_status)
        monitor.on_screenshot_captured = lambda s: self.root.after(0, lambda: self.on_screenshot(s))
        monitor.on_update_required     = self._on_update_required
        monitor.on_idle_started        = lambda secs: self.root.after(0, lambda: self._show_idle_banner(secs))
        monitor.on_idle_ended          = lambda: self.root.after(0, self._hide_idle_banner)

        self._show_login()
        threading.Thread(target=monitor.run_scheduler, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────────────────────
    # FORCE UPDATE
    # ─────────────────────────────────────────────────────────────────────────
    def _on_update_required(self, min_version: str):
        self.root.after(0, lambda: self._show_force_update(min_version))

    def _show_force_update(self, min_version: str):
        if hasattr(self, '_update_dialog') and self._update_dialog.winfo_exists():
            return
        from version import VERSION
        import webbrowser

        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Update Required")
        dlg.geometry("340x280")
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.update_idletasks()
        px, py = self.root.winfo_x(), self.root.winfo_y()
        dlg.geometry(f"340x280+{px+20}+{py+200}")
        self._update_dialog = dlg

        ctk.CTkLabel(dlg, text="🔄", font=self._font(36)).pack(pady=(28, 0))
        ctk.CTkLabel(dlg, text="Update Required",
                     font=self._font(16, "bold"), text_color=TEXT).pack(pady=(6, 0))
        ctk.CTkLabel(dlg, text=f"Version {min_version} is required.\nYou are running {VERSION}.",
                     font=self._font(12), text_color=TEXT_SUB,
                     justify="center").pack(pady=(8, 0))

        def _open():
            webbrowser.open("https://github.com/invectors/ghv-monitor/releases/latest")

        ctk.CTkButton(dlg, text="⬇  Download Update", height=44, corner_radius=10,
                      fg_color=GREEN, hover_color=GREEN_DIM,
                      font=self._font(13, "bold"), text_color=TEXT,
                      command=_open).pack(fill="x", padx=28, pady=(18, 0))
        ctk.CTkButton(dlg, text="Quit App", height=36, corner_radius=10,
                      fg_color="transparent", border_color=BORDER, border_width=1,
                      hover_color="#1a1a1a", text_color=TEXT_MUTED,
                      font=self._font(12), command=self._on_close
                      ).pack(fill="x", padx=28, pady=(8, 0))

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
                MonitorGUI._poppins_checked = "Poppins" in tk.font.families(self.root)
            except Exception:
                MonitorGUI._poppins_checked = False
        return MonitorGUI._poppins_checked

    # ─────────────────────────────────────────────────────────────────────────
    # LOGIN
    # ─────────────────────────────────────────────────────────────────────────
    def _show_login(self):
        self._clear()
        self.root.geometry("380x540")

        logo = ctk.CTkFrame(self.root, height=180, fg_color=BG_HEADER, corner_radius=0)
        logo.pack(fill="x")
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="GHV", font=self._font(44, "bold"), text_color=TEXT).pack(pady=(24, 0))
        ctk.CTkLabel(logo, text="Monitor", font=self._font(18), text_color=GREEN).pack()
        ctk.CTkLabel(logo, text="Employee Login", font=self._font(12), text_color=TEXT_SUB).pack(pady=(4, 0))

        form = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        form.pack(fill="both", expand=True, padx=32)

        ctk.CTkLabel(form, text="Username", font=self._font(11, "bold"),
                     text_color=TEXT_SUB, anchor="w").pack(fill="x", pady=(20, 4))
        self._user_entry = ctk.CTkEntry(form, placeholder_text="your@email.com",
                                        height=44, corner_radius=8,
                                        fg_color=BG_INPUT, border_color=BORDER, border_width=1,
                                        text_color=TEXT, placeholder_text_color=TEXT_MUTED,
                                        font=self._font(13))
        self._user_entry.pack(fill="x")
        if monitor.credentials and monitor.credentials.get("username"):
            self._user_entry.insert(0, monitor.credentials["username"])

        ctk.CTkLabel(form, text="Password", font=self._font(11, "bold"),
                     text_color=TEXT_SUB, anchor="w").pack(fill="x", pady=(14, 4))
        pw_row = ctk.CTkFrame(form, fg_color="transparent")
        pw_row.pack(fill="x")
        self._pw_entry = ctk.CTkEntry(pw_row, placeholder_text="••••••••",
                                      height=44, corner_radius=8, show="•",
                                      fg_color=BG_INPUT, border_color=BORDER, border_width=1,
                                      text_color=TEXT, placeholder_text_color=TEXT_MUTED,
                                      font=self._font(13))
        self._pw_entry.pack(side="left", fill="x", expand=True)
        self._pw_visible = False
        ctk.CTkButton(pw_row, text="👁", width=40, height=44,
                      fg_color=BG_INPUT, hover_color=BG_CARD, corner_radius=8,
                      text_color=TEXT_SUB, font=self._font(14),
                      command=self._toggle_pw).pack(side="left", padx=(4, 0))

        self._pw_entry.bind("<Return>", lambda e: self._do_login())

        self._login_btn = ctk.CTkButton(form, text="Login", height=48, corner_radius=10,
                                        fg_color=GREEN, hover_color=GREEN_DIM,
                                        font=self._font(14, "bold"), text_color=TEXT,
                                        command=self._do_login)
        self._login_btn.pack(fill="x", pady=(18, 0))

        sep = ctk.CTkFrame(form, height=1, fg_color=BORDER)
        sep.pack(fill="x", pady=(20, 10))
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

        def _t():
            result = monitor.login(username, password)
            self.root.after(0, lambda: self._handle_login(result))

        threading.Thread(target=_t, daemon=True).start()

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
        self.root.geometry("380x680")

        # ── Header ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self.root, height=56, fg_color=BG_CARD, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Monitor Status", font=self._font(15, "bold"),
                     text_color=TEXT).place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="⎋  Logout", width=85, height=30,
                      corner_radius=8, fg_color="transparent",
                      border_color=BORDER, border_width=1,
                      hover_color="#2a2a2a", text_color=TEXT_SUB,
                      font=self._font(11), command=self._do_logout
                      ).place(relx=1, x=-14, rely=0.5, anchor="e")

        # ── Main status card (ring + text) ────────────────────────────────
        card = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        card.pack(fill="x", padx=16, pady=(12, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=16, pady=(14, 10), fill="x")

        left = ctk.CTkFrame(inner, fg_color="transparent", width=80)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._ring_canvas = tk.Canvas(left, width=72, height=72,
                                      bg=BG_CARD, highlightthickness=0)
        self._ring_canvas.pack(anchor="center", expand=True)

        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True, padx=(14, 0))
        self._status_title = ctk.CTkLabel(right, text="Not Active",
                                          font=self._font(14, "bold"),
                                          text_color=TEXT, anchor="w")
        self._status_title.pack(fill="x")
        self._status_sub = ctk.CTkLabel(right, text="Waiting for clock in",
                                        font=self._font(10), text_color=TEXT_SUB,
                                        anchor="w", wraplength=190)
        self._status_sub.pack(fill="x", pady=(2, 6))
        self._badge = ctk.CTkLabel(right, text="  OFFLINE  ",
                                   font=self._font(9, "bold"),
                                   fg_color="#2a2a2a", text_color=TEXT_MUTED,
                                   corner_radius=10, width=70, height=20)
        self._badge.pack(anchor="w")

        # ── Elapsed timer + shift info ────────────────────────────────────
        info_card = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        info_card.pack(fill="x", padx=16, pady=(10, 0))
        info_row = ctk.CTkFrame(info_card, fg_color="transparent")
        info_row.pack(fill="x", padx=16, pady=10)

        # Left: elapsed
        el_col = ctk.CTkFrame(info_row, fg_color="transparent")
        el_col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(el_col, text="⏱  ELAPSED", font=self._font(9, "bold"),
                     text_color=TEXT_MUTED).pack(anchor="w")
        self._elapsed_lbl = ctk.CTkLabel(el_col, text="--:--:--",
                                         font=self._font(20, "bold"),
                                         text_color=GREEN)
        self._elapsed_lbl.pack(anchor="w")
        self._clockin_lbl = ctk.CTkLabel(el_col, text="",
                                         font=self._font(10), text_color=TEXT_MUTED)
        self._clockin_lbl.pack(anchor="w")

        # Divider
        ctk.CTkFrame(info_row, width=1, fg_color=BORDER).pack(side="left",
                                                               fill="y", padx=12)
        # Right: lunch remaining
        lunch_col = ctk.CTkFrame(info_row, fg_color="transparent")
        lunch_col.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(lunch_col, text="🍴  LUNCH LEFT", font=self._font(9, "bold"),
                     text_color=TEXT_MUTED).pack(anchor="w")
        self._lunch_lbl = ctk.CTkLabel(lunch_col, text="--",
                                       font=self._font(20, "bold"),
                                       text_color=TEAL)
        self._lunch_lbl.pack(anchor="w")
        self._lunch_sub = ctk.CTkLabel(lunch_col, text="remaining",
                                       font=self._font(10), text_color=TEXT_MUTED)
        self._lunch_sub.pack(anchor="w")

        # ── IDLE BANNER (hidden by default) ──────────────────────────────
        self._idle_banner = ctk.CTkFrame(self.root, fg_color="#2d1a00",
                                         corner_radius=10, border_color=YELLOW,
                                         border_width=1)
        # Not packed initially — shown only when idle
        idle_row = ctk.CTkFrame(self._idle_banner, fg_color="transparent")
        idle_row.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(idle_row, text="⚠", font=self._font(16, "bold"),
                     text_color=YELLOW).pack(side="left", padx=(0, 8))
        idle_text = ctk.CTkFrame(idle_row, fg_color="transparent")
        idle_text.pack(side="left", fill="x", expand=True)
        self._idle_banner_title = ctk.CTkLabel(idle_text, text="You are Idle",
                                               font=self._font(12, "bold"),
                                               text_color=YELLOW, anchor="w")
        self._idle_banner_title.pack(fill="x")
        self._idle_banner_sub = ctk.CTkLabel(idle_text,
                                             text="No activity detected. Move your mouse or type to resume.",
                                             font=self._font(9), text_color="#c8a96e",
                                             anchor="w", wraplength=220)
        self._idle_banner_sub.pack(fill="x")

        # ── CLOCK ACTION BUTTONS ──────────────────────────────────────────
        btn_card = ctk.CTkFrame(self.root, fg_color=BG_CARD, corner_radius=14)
        btn_card.pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(btn_card, text="Time Tracker", font=self._font(11, "bold"),
                     text_color=TEXT_MUTED).pack(anchor="w", padx=16, pady=(12, 6))

        row1 = ctk.CTkFrame(btn_card, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(0, 4))
        row2 = ctk.CTkFrame(btn_card, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 12))

        btn_cfg = dict(height=38, corner_radius=8,
                       font=self._font(11, "bold"), text_color=TEXT)

        self._btn_clock_in = ctk.CTkButton(row1, text="▶  Clock In",
                                           fg_color=GREEN, hover_color=GREEN_DIM,
                                           command=lambda: self._clock("clock_in"),
                                           **btn_cfg)
        self._btn_clock_in.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self._btn_lunch_out = ctk.CTkButton(row1, text="🍴  Lunch Out",
                                            fg_color=YELLOW, hover_color=YELLOW_DIM,
                                            command=lambda: self._clock("lunch_out"),
                                            **btn_cfg)
        self._btn_lunch_out.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self._btn_lunch_in = ctk.CTkButton(row2, text="☕  Lunch In",
                                           fg_color=TEAL, hover_color=TEAL_DIM,
                                           command=lambda: self._clock("lunch_in"),
                                           **btn_cfg)
        self._btn_lunch_in.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self._btn_clock_out = ctk.CTkButton(row2, text="■  Clock Out",
                                            fg_color=RED, hover_color=RED_DIM,
                                            command=lambda: self._clock("clock_out"),
                                            **btn_cfg)
        self._btn_clock_out.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # ── Footer ────────────────────────────────────────────────────────
        foot = ctk.CTkFrame(self.root, fg_color="transparent")
        foot.pack(fill="x", pady=(10, 8))
        ctk.CTkLabel(foot, text="🛡  Secure. Private. Transparent.",
                     font=self._font(9, "bold"), text_color=TEXT_MUTED).pack()
        ctk.CTkLabel(foot, text="GoHireVirtual Monitoring System",
                     font=self._font(8), text_color="#333333").pack(pady=(1, 0))

        self._elapsed_start_ts = None
        self._tick_elapsed()
        self.update_status()

    # ─────────────────────────────────────────────────────────────────────────
    # RING CANVAS
    # ─────────────────────────────────────────────────────────────────────────
    def _draw_ring(self, color):
        try:
            c = self._ring_canvas
            c.delete("all")
            cx, cy, r = 36, 36, 30
            c.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#2a2a2a", width=7)
            c.create_arc(cx-r, cy-r, cx+r, cy+r,
                         start=90, extent=-359.9,
                         outline=color, width=7, style="arc")
            c.create_text(cx, cy, text="▶", fill=color,
                          font=("Segoe UI Symbol", 14))
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # STATUS UPDATE
    # ─────────────────────────────────────────────────────────────────────────
    def update_status(self):
        try:
            if not hasattr(self, "_status_title"):
                return

            interval        = CONFIG.get("CAPTURE_INTERVAL_MINUTES", 10)
            is_clocked_in   = monitor.clocked_in
            is_on_lunch     = monitor.on_lunch
            is_clocked_out  = not is_clocked_in and not is_on_lunch

            # ── Ring + status text ────────────────────────────────────────
            if monitor.is_monitoring:
                if monitor.is_paused:
                    self._draw_ring(YELLOW)
                    self._status_title.configure(text="On Lunch Break")
                    self._status_sub.configure(text="Monitoring paused. Resumes when you return.")
                    self._badge.configure(text="  PAUSED  ",
                                          fg_color="#2d2600", text_color=YELLOW)
                elif monitor.is_idle:
                    self._draw_ring(YELLOW)
                    self._status_title.configure(text="Idle Detected")
                    self._status_sub.configure(text=f"Capturing every {interval} min when active")
                    self._badge.configure(text="  IDLE  ",
                                          fg_color="#2d2600", text_color=YELLOW)
                else:
                    self._draw_ring(GREEN_GLOW)
                    self._status_title.configure(text="Monitoring Active")
                    self._status_sub.configure(text=f"Capturing screenshots every {interval} min")
                    self._badge.configure(text="  ACTIVE  ",
                                          fg_color="#071407", text_color=GREEN_GLOW)
            else:
                self._draw_ring("#333333")
                self._status_title.configure(text="Not Active")
                self._status_sub.configure(text="Waiting for you to clock in")
                self._badge.configure(text="  OFFLINE  ",
                                      fg_color="#1a1a1a", text_color=TEXT_MUTED)

            # ── Clock-in time label ───────────────────────────────────────
            if monitor.clock_in_time and hasattr(self, "_clockin_lbl"):
                self._clockin_lbl.configure(text=f"Clocked in: {monitor.clock_in_time}")
            elif hasattr(self, "_clockin_lbl"):
                self._clockin_lbl.configure(text="")

            # ── Elapsed timer anchor (use UTC time for continuity after restart) ──
            if monitor.clocked_in and monitor.clock_in_time_utc:
                try:
                    self._elapsed_start_ts = datetime.strptime(
                        monitor.clock_in_time_utc, '%Y-%m-%d %H:%M:%S'
                    ).replace(tzinfo=timezone.utc)
                except Exception:
                    if self._elapsed_start_ts is None:
                        self._elapsed_start_ts = datetime.now(timezone.utc)
            elif not monitor.clocked_in:
                self._elapsed_start_ts = None
                if hasattr(self, "_elapsed_lbl"):
                    self._elapsed_lbl.configure(text="--:--:--", text_color=TEXT_MUTED)

            # ── Lunch remaining display ───────────────────────────────────
            if hasattr(self, "_lunch_lbl"):
                rem = monitor.lunch_remaining_seconds
                if not monitor.clocked_in and not monitor.on_lunch:
                    self._lunch_lbl.configure(text="--", text_color=TEXT_MUTED)
                    self._lunch_sub.configure(text="not clocked in")
                elif monitor.lunch_exhausted:
                    self._lunch_lbl.configure(text="0m", text_color=RED)
                    self._lunch_sub.configure(text="no time left")
                else:
                    m = rem // 60
                    s = rem % 60
                    display = f"{m}m" if s == 0 else f"{m}m {s}s"
                    color = YELLOW if rem < 600 else TEAL  # warn when <10 min left
                    self._lunch_lbl.configure(text=display, text_color=color)
                    self._lunch_sub.configure(text="remaining")

            # ── Clock buttons state ───────────────────────────────────────
            self._update_clock_buttons(is_clocked_in, is_on_lunch)

        except Exception:
            pass

    def _update_clock_buttons(self, is_clocked_in, is_on_lunch):
        try:
            EN  = "normal"
            DIS = "disabled"
            ci_state = EN if not is_clocked_in and not is_on_lunch else DIS
            # Lunch Out disabled when: not clocked in, already on lunch, OR lunch exhausted
            lo_state = EN if (is_clocked_in and not is_on_lunch
                              and not monitor.lunch_exhausted) else DIS
            li_state = EN if is_on_lunch else DIS
            co_state = EN if is_clocked_in or is_on_lunch else DIS

            self._btn_clock_in.configure(state=ci_state)
            self._btn_lunch_out.configure(state=lo_state)
            self._btn_lunch_in.configure(state=li_state)
            self._btn_clock_out.configure(state=co_state)

            # Visual hint on Lunch Out when exhausted
            if monitor.lunch_exhausted and is_clocked_in:
                self._btn_lunch_out.configure(text="🍴  No Lunch Left")
            else:
                self._btn_lunch_out.configure(text="🍴  Lunch Out")
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # ELAPSED TICKER
    # ─────────────────────────────────────────────────────────────────────────
    def _tick_elapsed(self):
        """Runs every second on the main thread to update the elapsed display."""
        try:
            if hasattr(self, "_elapsed_lbl") and self._elapsed_start_ts:
                now     = datetime.now(timezone.utc)
                elapsed = int((now - self._elapsed_start_ts).total_seconds())
                elapsed = max(0, elapsed)
                h = elapsed // 3600
                m = (elapsed % 3600) // 60
                s = elapsed % 60
                self._elapsed_lbl.configure(
                    text=f"{h:02d}:{m:02d}:{s:02d}",
                    text_color=GREEN if monitor.is_monitoring and not monitor.is_paused
                               else TEXT_MUTED)
        except Exception:
            pass
        self.root.after(1000, self._tick_elapsed)

    # ─────────────────────────────────────────────────────────────────────────
    # IDLE BANNER
    # ─────────────────────────────────────────────────────────────────────────
    def _show_idle_banner(self, idle_seconds=0):
        try:
            mins = int(idle_seconds // 60)
            msg  = (f"No activity for {mins} min. " if mins >= 1 else "No activity detected. ")
            msg += "Move your mouse or type to resume."
            self._idle_banner_sub.configure(text=msg)
            self._idle_banner.pack(fill="x", padx=16, pady=(6, 0),
                                   before=self._idle_banner.master.winfo_children()[0]
                                   if False else None)
            # Insert banner right after the info card
            self._idle_banner.pack(fill="x", padx=16, pady=(8, 0))
        except Exception:
            pass

    def _hide_idle_banner(self):
        try:
            self._idle_banner.pack_forget()
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # CLOCK ACTIONS
    # ─────────────────────────────────────────────────────────────────────────
    def _clock(self, action):
        """Called from clock buttons — sends action to hub in a background thread."""
        btns = [self._btn_clock_in, self._btn_lunch_out,
                self._btn_lunch_in, self._btn_clock_out]
        for b in btns:
            try: b.configure(state="disabled")
            except Exception: pass

        def _do():
            result = monitor.clock_action(action)
            self.root.after(0, lambda: self._on_clock_result(result, btns))

        threading.Thread(target=_do, daemon=True).start()

    def _on_clock_result(self, result, btns):
        if not result.get('success'):
            if result.get('already_active'):
                # Informational — shift is still running, just sync to correct state
                # Don't show red error, just quietly refresh
                pass
            else:
                msg = result.get('message', 'Action failed')
                self._status_sub.configure(text=f"⚠ {msg[:50]}", text_color=RED)
                self.root.after(3000, lambda: self.update_status())
        self.update_status()

    # ─────────────────────────────────────────────────────────────────────────
    # SCREENSHOT CALLBACK
    # ─────────────────────────────────────────────────────────────────────────
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
