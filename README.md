# GHV Monitor - Python Desktop App

**Simple, lightweight desktop screenshot monitor for GoHireVirtual employees.**

Built with Python - **much easier to install and run than Electron!**

---

## ✨ Features

✅ **Full Desktop Capture** - Captures entire screen every 10 minutes  
✅ **Auto-Start/Stop** - Syncs with time tracker  
✅ **Lunch Detection** - Auto-pauses during lunch  
✅ **System Tray** - Runs quietly in background  
✅ **Offline Queue** - Uploads when reconnected  
✅ **Lightweight** - ~20MB vs 100MB+ for Electron  
✅ **Cross-Platform** - Works on Linux, Windows, Mac  

---

## 🚀 Quick Start (Linux)

### **1. Install** (One Command!)

```bash
chmod +x install.sh
./install.sh
```

This installs everything automatically!

### **2. Run**

```bash
./app.py
```

Or search for "GHV Monitor" in your applications menu.

### **3. Login**

Enter your hub credentials and you're done!

---

## 📋 Manual Installation

If the install script doesn't work:

### **Step 1: Install Python Dependencies**

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-tk

# Fedora
sudo dnf install python3 python3-tkinter

# Arch
sudo pacman -S python tk
```

### **Step 2: Install Python Packages**

```bash
pip3 install -r requirements.txt
```

### **Step 3: Run**

```bash
python3 app.py
```

---

## 📦 Dependencies

Minimal dependencies (all Python packages):

- **mss** - Fast screenshot capture
- **Pillow** - Image processing
- **requests** - HTTP uploads
- **schedule** - Job scheduling
- **pystray** - System tray icon

Plus **tkinter** (usually pre-installed on Linux)

---

## 🎯 How It Works

1. **Login** with hub credentials
2. **Clock in** on the hub
3. App **automatically starts** monitoring
4. Screenshots captured **every 10 minutes**
5. **Pauses** during lunch
6. **Stops** when you clock out

---

## 🔧 Configuration

Edit `main.py` to change settings:

```python
CONFIG = {
    'UPLOAD_URL': 'https://hub.gohirevirtual.net/api/screenshots/upload.php',
    'STATUS_URL': 'https://hub.gohirevirtual.net/api/screenshots/status.php',
    'CAPTURE_INTERVAL_MINUTES': 10,  # Change frequency here
    'IMAGE_QUALITY': 85,              # JPEG quality (1-100)
    'MAX_IMAGE_WIDTH': 1920,          # Max screenshot width
}
```

---

## 🐛 Troubleshooting

### **"No module named 'tkinter'"**

```bash
# Ubuntu/Debian
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter
```

### **"Permission denied" when running app.py**

```bash
chmod +x app.py
./app.py
```

### **Screenshot capture fails**

```bash
# Install X11 libraries
sudo apt install libx11-6 libxtst6
```

### **Tray icon doesn't show**

Some desktop environments need:

```bash
sudo apt install gir1.2-appindicator3-0.1
```

---

## 💡 Features Comparison

| Feature | Python App | Electron App |
|---------|-----------|--------------|
| **Installation** | ✅ Super easy | ❌ Complex |
| **Dependencies** | ✅ 5 packages | ❌ 100+ packages |
| **Size** | ✅ ~20MB | ❌ ~100MB |
| **Memory** | ✅ ~50MB | ❌ ~150MB |
| **Linux Support** | ✅ Perfect | ⚠️ Tricky |
| **Screenshot Capture** | ✅ Full desktop | ✅ Full desktop |
| **Speed** | ✅ Fast | ✅ Fast |

**Winner: Python! 🐍**

---

## 📁 File Structure

```
ghv-monitor-python/
├── app.py              # Main launcher
├── main.py             # Core logic (screenshot, upload)
├── gui.py              # Tkinter GUI
├── tray.py             # System tray icon
├── requirements.txt    # Python dependencies
├── install.sh          # Installation script
└── README.md           # This file
```

---

## 🔒 Security

- Credentials stored in `~/.ghv-monitor/config.json`
- HTTPS encryption for uploads
- No external dependencies
- Open source - audit the code yourself!

---

## 🆘 Support

**Issues?** Check:
1. Python 3.7+ installed (`python3 --version`)
2. All dependencies installed (`pip3 install -r requirements.txt`)
3. X11 libraries present (for screenshots)

**Still stuck?** Contact IT support: support@gohirevirtual.net

---

## 📜 License

© 2026 GoHireVirtual. All rights reserved.

---

## 🎉 Why Python is Better

- **Simpler** - No Node.js, no npm, no compilation
- **Smaller** - 5 packages vs 100+
- **Faster to install** - Minutes vs hours
- **Easier to debug** - Clear Python errors
- **Better for Linux** - Native support
- **More reliable** - Fewer moving parts

**Just works!** ™️
