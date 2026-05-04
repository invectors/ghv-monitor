#!/usr/bin/env python3
"""
GHV Monitor - Main Application
Runs GUI and system tray together
"""

import threading
from gui import MonitorGUI
from tray import TrayIcon

def main():
    # Create GUI
    app = MonitorGUI()
    
    # Create and run tray icon in background
    tray = TrayIcon(gui_app=app)
    tray_thread = threading.Thread(target=tray.run, daemon=True)
    tray_thread.start()
    
    # Run GUI (blocks until closed)
    app.run()

if __name__ == '__main__':
    main()
