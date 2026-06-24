# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# Allow CI to pin the macOS architecture (e.g. 'x86_64' or 'arm64').
# Falls back to None = "build for the current runner" when unset.
TARGET_ARCH = os.environ.get('GHV_TARGET_ARCH') or None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PIL._tkinter_finder',
        'schedule',
        'Quartz',
        'main',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GHV-Monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=TARGET_ARCH,
    codesign_identity=None,
    entitlements_file='entitlements.plist' if os.path.exists('entitlements.plist') else None,
)

app = BUNDLE(
    exe,
    name='GHV Monitor.app',
    bundle_identifier='net.gohirevirtual.monitor',
    entitlements_file='entitlements.plist' if os.path.exists('entitlements.plist') else None,
    info_plist={
        'NSScreenCaptureDescription': 'GHV Monitor needs screen recording to capture screenshots for time tracking.',
        'NSHighResolutionCapable': True,
        'LSUIElement': False,
    },
)
