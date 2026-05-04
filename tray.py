#!/usr/bin/env python3
"""
GHV Monitor - System Tray
System tray icon with menu
"""

import threading
from PIL import Image, ImageDraw
import pystray
from main import monitor

class TrayIcon:
    def __init__(self, gui_app=None):
        self.gui_app = gui_app
        self.icon = None
        
        # Set callback
        monitor.on_status_changed = self.update_icon
        
        # Create icon
        self.create_icon()
    
    def create_tray_image(self, color):
        """Create tray icon image"""
        # Create 64x64 image
        image = Image.new('RGB', (64, 64), color='white')
        draw = ImageDraw.Draw(image)
        
        # Draw colored circle
        draw.ellipse([12, 12, 52, 52], fill=color)
        
        return image
    
    def get_icon_color(self):
        """Get icon color based on monitoring state"""
        if monitor.is_monitoring:
            if monitor.is_paused:
                return '#eab308'  # Yellow
            else:
                return '#22c55e'  # Green
        else:
            return '#9ca3af'  # Gray
    
    def update_icon(self):
        """Update tray icon"""
        if self.icon:
            color = self.get_icon_color()
            self.icon.icon = self.create_tray_image(color)
            
            # Update title
            if monitor.is_monitoring:
                if monitor.is_paused:
                    status = "Paused (Lunch)"
                else:
                    status = "Monitoring Active"
            else:
                status = "Stopped (Not Clocked In)"
            
            self.icon.title = f"GHV Monitor - {status}"
    
    def show_window(self, icon, item):
        """Show main window"""
        if self.gui_app:
            self.gui_app.show_window()
    
    def toggle_pause(self, icon, item):
        """Toggle pause/resume"""
        if not monitor.is_monitoring:
            return
        
        if monitor.is_paused:
            monitor.resume_monitoring()
        else:
            monitor.pause_monitoring()
    
    def quit_app(self, icon, item):
        """Quit application"""
        icon.stop()
        if self.gui_app:
            self.gui_app.root.quit()
    
    def create_menu(self):
        """Create tray menu"""
        def get_pause_text(item):
            if monitor.is_paused:
                return "Resume Monitoring"
            else:
                return "Pause Monitoring"
        
        def get_pause_enabled(item):
            return monitor.is_monitoring
        
        return pystray.Menu(
            pystray.MenuItem("Show Window", self.show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                get_pause_text,
                self.toggle_pause,
                enabled=get_pause_enabled
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_app)
        )
    
    def create_icon(self):
        """Create system tray icon"""
        color = self.get_icon_color()
        image = self.create_tray_image(color)
        
        self.icon = pystray.Icon(
            "ghv-monitor",
            image,
            "GHV Monitor",
            menu=self.create_menu()
        )
    
    def run(self):
        """Run tray icon"""
        self.icon.run()

if __name__ == '__main__':
    tray = TrayIcon()
    tray.run()
