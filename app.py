#!/usr/bin/env python3
"""
GHV Monitor - Main Application
Runs GUI and system tray together
"""

import threading
import platform
from gui import MonitorGUI

def main():
    # Create GUI
    app = MonitorGUI()
    
    # Platform-specific tray
    if platform.system() == 'Darwin':
        # macOS: Use rumps in main thread, Tkinter in secondary
        from tray_mac import MacTray
        tray = MacTray(gui_app=app)
        # rumps must run in main thread, so run Tkinter in background
        gui_thread = threading.Thread(target=app.run, daemon=True)
        gui_thread.start()
        tray.run()
    else:
        # Windows/Linux: Use pystray in background thread
        from tray import TrayIcon
        tray = TrayIcon(gui_app=app)
        tray_thread = threading.Thread(target=tray.run, daemon=True)
        tray_thread.start()
        # Run GUI in main thread
        app.run()

if __name__ == '__main__':
    main()
