#!/bin/bash
# GHV Monitor - Installation Script for Linux

set -e

echo "========================================="
echo "  GHV Monitor - Installation"
echo "========================================="
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed!"
    echo "Install it with: sudo apt install python3 python3-pip python3-tk"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION found"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed!"
    echo "Install it with: sudo apt install python3-pip"
    exit 1
fi

echo "✅ pip3 found"

# Install system dependencies (Ubuntu/Debian)
if command -v apt &> /dev/null; then
    echo ""
    echo "Installing system dependencies..."
    sudo apt update
    sudo apt install -y python3-tk python3-pil python3-pil.imagetk
    echo "✅ System dependencies installed"
fi

# Install Python packages
echo ""
echo "Installing Python packages..."
pip3 install -r requirements.txt
echo "✅ Python packages installed"

# Make scripts executable
chmod +x app.py gui.py main.py tray.py

# Create desktop entry
echo ""
echo "Creating desktop shortcut..."
mkdir -p ~/.local/share/applications

cat > ~/.local/share/applications/ghv-monitor.desktop << 'EOF'
[Desktop Entry]
Name=GHV Monitor
Comment=Desktop Screenshot Monitor
Exec=FULL_PATH/app.py
Icon=computer
Terminal=false
Type=Application
Categories=Utility;
EOF

# Replace FULL_PATH with actual path
INSTALL_DIR=$(pwd)
sed -i "s|FULL_PATH|$INSTALL_DIR|g" ~/.local/share/applications/ghv-monitor.desktop

echo "✅ Desktop shortcut created"

# Create autostart entry
echo ""
read -p "Enable auto-start on boot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    mkdir -p ~/.config/autostart
    cp ~/.local/share/applications/ghv-monitor.desktop ~/.config/autostart/
    echo "✅ Auto-start enabled"
fi

echo ""
echo "========================================="
echo "  Installation Complete! 🎉"
echo "========================================="
echo ""
echo "To run the app:"
echo "  ./app.py"
echo ""
echo "Or search for 'GHV Monitor' in your applications menu"
echo ""
