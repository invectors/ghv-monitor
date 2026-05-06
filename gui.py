#!/usr/bin/env python3
"""
GHV Monitor - GUI (NO TRAY VERSION)
Regular Tkinter window that shows in taskbar/dock
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from main import monitor

class MonitorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GHV Monitor")
        self.root.geometry("400x450")
        self.root.resizable(False, False)
        
        # Set callbacks
        monitor.on_status_changed = self.update_status
        monitor.on_screenshot_captured = self.on_screenshot
        
        # Create UI
        if monitor.credentials:
            self.show_status_screen()
        else:
            self.show_login_screen()
        
        # Start scheduler in background
        threading.Thread(target=monitor.run_scheduler, daemon=True).start()
        
        # Normal close behavior — just quit the app
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def on_close(self):
        """Normal window close — stop monitoring and quit"""
        monitor.stop_monitoring()
        self.root.destroy()
    
    def show_login_screen(self):
        """Show login screen"""
        self.clear_window()
        
        # Logo frame
        logo_frame = tk.Frame(self.root, bg='#3b82f6', height=120)
        logo_frame.pack(fill=tk.X)
        logo_frame.pack_propagate(False)
        
        tk.Label(logo_frame, text="GHV", font=("Arial", 32, "bold"), 
                bg='#3b82f6', fg='white').pack(pady=20)
        tk.Label(logo_frame, text="Monitor", font=("Arial", 16), 
                bg='#3b82f6', fg='white').pack()
        
        # Form frame
        form_frame = tk.Frame(self.root, padx=40, pady=40)
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        # Username
        tk.Label(form_frame, text="Username", font=("Arial", 10)).pack(anchor=tk.W)
        self.username_entry = tk.Entry(form_frame, font=("Arial", 12))
        self.username_entry.pack(fill=tk.X, pady=(5, 15))
        
        # Pre-fill saved username if exists
        if monitor.credentials and monitor.credentials.get('username'):
            self.username_entry.insert(0, monitor.credentials['username'])
        self.username_entry.focus()
        
        # Password
        tk.Label(form_frame, text="Password", font=("Arial", 10)).pack(anchor=tk.W)
        self.password_entry = tk.Entry(form_frame, font=("Arial", 12), show="*")
        self.password_entry.pack(fill=tk.X, pady=(5, 20))
        
        # Pre-fill saved password if exists
        if monitor.credentials and monitor.credentials.get('password'):
            self.password_entry.insert(0, monitor.credentials['password'])
        
        # Bind Enter key
        self.password_entry.bind('<Return>', lambda e: self.do_login())
        
        # Login button
        self.login_btn = tk.Button(form_frame, text="Login", font=("Arial", 12, "bold"),
                                   bg='#3b82f6', fg='white', cursor='hand2',
                                   command=self.do_login)
        self.login_btn.pack(fill=tk.X, ipady=10)
        
        # Info text
        tk.Label(form_frame, text="Enter your GoHireVirtual hub credentials",
                font=("Arial", 9), fg='#6b7280').pack(pady=(20, 0))
    
    def do_login(self):
        """Handle login"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password")
            return
        
        # Disable button
        self.login_btn.config(state=tk.DISABLED, text="Logging in...")
        
        # Login in background
        def login_thread():
            result = monitor.login(username, password)
            # Update UI in main thread
            self.root.after(0, lambda: self.handle_login_result(result))
        
        threading.Thread(target=login_thread, daemon=True).start()
    
    def handle_login_result(self, result):
        """Handle login result"""
        if result['success']:
            self.show_status_screen()
        else:
            messagebox.showerror("Login Failed", result.get('message', 'Invalid credentials'))
            self.login_btn.config(state=tk.NORMAL, text="Login")
    
    def show_status_screen(self):
        """Show status screen"""
        self.clear_window()
        
        # Header
        header_frame = tk.Frame(self.root, bg='white', padx=20, pady=15)
        header_frame.pack(fill=tk.X)
        
        tk.Label(header_frame, text="Monitor Status", font=("Arial", 16, "bold"),
                bg='white').pack(side=tk.LEFT)
        
        tk.Button(header_frame, text="Logout", font=("Arial", 10),
                 cursor='hand2', command=self.do_logout).pack(side=tk.RIGHT)
        
        # Status card
        status_frame = tk.Frame(self.root, bg='white', padx=20, pady=20)
        status_frame.pack(fill=tk.X, padx=20, pady=(10, 0))
        
        # Status indicator
        indicator_frame = tk.Frame(status_frame, bg='white')
        indicator_frame.pack(fill=tk.X)
        
        self.status_dot = tk.Canvas(indicator_frame, width=20, height=20, 
                                    bg='white', highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 10))
        
        status_text_frame = tk.Frame(indicator_frame, bg='white')
        status_text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.status_title = tk.Label(status_text_frame, text="Not Active",
                                     font=("Arial", 14, "bold"), bg='white')
        self.status_title.pack(anchor=tk.W)
        
        self.status_subtitle = tk.Label(status_text_frame, text="Waiting for clock in",
                                       font=("Arial", 10), fg='#6b7280', bg='white')
        self.status_subtitle.pack(anchor=tk.W)
        
        # Stats
        stats_frame = tk.Frame(self.root)
        stats_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Last capture
        stat1 = tk.Frame(stats_frame, bg='white', padx=15, pady=15)
        stat1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        tk.Label(stat1, text="Last Capture", font=("Arial", 9), fg='#6b7280',
                bg='white').pack(anchor=tk.W)
        self.last_capture_label = tk.Label(stat1, text="Never", font=("Arial", 14, "bold"),
                                          bg='white')
        self.last_capture_label.pack(anchor=tk.W)
        
        # Queue
        stat2 = tk.Frame(stats_frame, bg='white', padx=15, pady=15)
        stat2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        tk.Label(stat2, text="Queue", font=("Arial", 9), fg='#6b7280',
                bg='white').pack(anchor=tk.W)
        self.queue_label = tk.Label(stat2, text="0", font=("Arial", 14, "bold"),
                                    bg='white')
        self.queue_label.pack(anchor=tk.W)
        
        # Info
        info_frame = tk.Frame(self.root, bg='#f9fafb', padx=20, pady=15)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))
        
        tk.Label(info_frame, text="How it works", font=("Arial", 11, "bold"),
                bg='#f9fafb').pack(anchor=tk.W, pady=(0, 10))
        
        for text in [
            "• Automatically starts when you clock in",
            "• Captures desktop every 10 minutes",
            "• Pauses during lunch breaks",
            "• Stops when you clock out"
        ]:
            tk.Label(info_frame, text=text, font=("Arial", 9), fg='#6b7280',
                    bg='#f9fafb').pack(anchor=tk.W, pady=2)
        
        # Update status
        self.update_status()
    
    def update_status(self):
        """Update status display"""
        if not hasattr(self, 'status_dot'):
            return
        
        # Clear canvas
        self.status_dot.delete("all")
        
        if monitor.is_monitoring:
            if monitor.is_paused:
                color = '#eab308'
                self.status_title.config(text="Paused")
                self.status_subtitle.config(text="Lunch break - monitoring paused")
            else:
                color = '#22c55e'
                self.status_title.config(text="Monitoring Active")
                self.status_subtitle.config(text="Capturing screenshots every 10 minutes")
        else:
            color = '#9ca3af'
            self.status_title.config(text="Not Active")
            self.status_subtitle.config(text="Waiting for clock in")
        
        self.status_dot.create_oval(4, 4, 16, 16, fill=color, outline='')
        self.queue_label.config(text=str(len(monitor.upload_queue)))
    
    def on_screenshot(self, status):
        """Screenshot captured callback"""
        if status == 'success':
            self.last_capture_label.config(text="Just now")
        self.update_status()
    
    def do_logout(self):
        """Handle logout"""
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            monitor.logout()
            self.show_login_screen()
    
    def clear_window(self):
        """Clear all widgets"""
        for widget in self.root.winfo_children():
            widget.destroy()
    
    def run(self):
        """Run the GUI"""
        self.root.mainloop()

if __name__ == '__main__':
    app = MonitorGUI()
    app.run()
