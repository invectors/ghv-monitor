#!/usr/bin/env python3
"""
GHV Monitor - macOS System Tray (rumps)
Native macOS menu bar that works with Tkinter
"""

import rumps
from main import monitor

class MacTray:
    def __init__(self, gui_app=None):
        self.gui_app = gui_app
        self.app = rumps.App("GHV Monitor", quit_button=None)
        
        # Build menu
        self.app.menu = [
            rumps.MenuItem("Show Window", callback=self.show_window),
            None,  # separator
            rumps.MenuItem("Pause/Resume", callback=self.toggle_pause),
            None,  # separator
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]
        
        # Set callback
        monitor.on_status_changed = self.update_icon
        
        # Initial icon update
        self.update_icon()
    
    def get_status_text(self):
        if monitor.is_monitoring:
            if monitor.is_paused:
                return "⏸ Paused"
            else:
                return "● Recording"
        else:
            return "○ Stopped"
    
    def update_icon(self):
        """Update menu title based on status"""
        self.app.title = self.get_status_text()
    
    def show_window(self, _):
        """Show main window"""
        if self.gui_app:
            self.gui_app.show_window()
    
    def toggle_pause(self, _):
        """Toggle pause/resume"""
        if not monitor.is_monitoring:
            return
        if monitor.is_paused:
            monitor.resume_monitoring()
        else:
            monitor.pause_monitoring()
    
    def quit_app(self, _):
        """Quit application"""
        if self.gui_app:
            self.gui_app.root.quit()
        rumps.quit_application()
    
    def run(self):
        """Run tray (blocks, so must be in main thread)"""
        self.app.run()

if __name__ == '__main__':
    tray = MacTray()
    tray.run()
