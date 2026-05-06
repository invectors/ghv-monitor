#!/usr/bin/env python3
"""
GHV Monitor - Main Application
Regular windowed app, no system tray
"""

from gui import MonitorGUI

def main():
    app = MonitorGUI()
    app.run()

if __name__ == '__main__':
    main()
