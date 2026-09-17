# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

TARGET_ARCH = os.environ.get('GHV_TARGET_ARCH') or None

import customtkinter
CTK_PATH = os.path.dirname(customtkinter.__file__)

# ── PE Version Info (Windows) ─────────────────────────────────────────────────
# Embedding publisher metadata significantly reduces Windows Defender's
# Bearfoos.A!ml ML false-positive score on PyInstaller executables.
# Anonymous EXEs with no PE version info look far more suspicious to the
# heuristic. This block is harmless on macOS — PyInstaller simply ignores it.
try:
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
        StringStruct, VarFileInfo, VarStruct
    )
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(1, 11, 0, 0),
            prodvers=(1, 11, 0, 0),
            mask=0x3f, flags=0x0, OS=0x4,
            fileType=0x1, subtype=0x0,
            date=(0, 0)
        ),
        kids=[
            StringFileInfo([
                StringTable(
                    u'040904B0',
                    [
                        StringStruct(u'CompanyName',      u'GoHireVirtual'),
                        StringStruct(u'FileDescription',  u'GHV Monitor - Employee Screenshot Monitoring'),
                        StringStruct(u'FileVersion',      u'1.11.0.0'),
                        StringStruct(u'InternalName',     u'GHV-Monitor'),
                        StringStruct(u'LegalCopyright',   u'Copyright GoHireVirtual'),
                        StringStruct(u'OriginalFilename', u'GHV-Monitor.exe'),
                        StringStruct(u'ProductName',      u'GHV Monitor'),
                        StringStruct(u'ProductVersion',   u'1.11.0'),
                    ]
                )
            ]),
            VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
        ]
    )
except Exception:
    version_info = None

import sys as _sys

# psutil is used by the Linux/Windows activity tracking branch of _active_window().
# PyInstaller finds it via static analysis even on macOS (where it's never called),
# and then tries to lipo it into a universal2 fat binary — which fails because the
# macOS pip wheel is ARM64-only. Excluding it on macOS is safe: macOS uses AppKit.
_excludes = ['psutil'] if _sys.platform == 'darwin' else []

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
        'zoneinfo',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
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
    # UPX disabled — UPX compression is the single biggest trigger for
    # Windows Defender's Bearfoos.A!ml ML heuristic on PyInstaller EXEs.
    # Disabling it costs ~5-10 MB in file size but eliminates the false positive.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=TARGET_ARCH,
    codesign_identity=None,
    entitlements_file=None,
    version=version_info,
)

app = BUNDLE(
    exe,
    name='GHV Monitor.app',
    bundle_identifier='net.gohirevirtual.monitor',
)
