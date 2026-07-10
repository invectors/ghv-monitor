# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# Allow CI to pin the macOS architecture (e.g. 'x86_64' or 'arm64').
# Falls back to None = "build for the current runner" when unset.
TARGET_ARCH = os.environ.get('GHV_TARGET_ARCH') or None

# customtkinter ships its own theme JSON files that must be bundled.
import customtkinter
CTK_PATH = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        (CTK_PATH, 'customtkinter'),
        ('version.py', '.'),
    ],
    hiddenimports=[
        'PIL._tkinter_finder',
        'schedule',
        'Quartz',
        'customtkinter',
        'customtkinter.windows',
        'customtkinter.windows.widgets',
        'customtkinter.windows.widgets.appearance_mode',
        'customtkinter.windows.widgets.scaling',
        'customtkinter.windows.widgets.font',
        'version',
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
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='GHV Monitor.app',
    bundle_identifier='net.gohirevirtual.monitor',
)
