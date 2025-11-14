# -*- mode: python ; coding: utf-8 -*-

# This is a PyInstaller spec file.
# To build your app, run: pyinstaller ReceiptPrinterApp.spec

import os
import escpos  # Import escpos to find its data file

# --- Find escpos data file ---
# This finds the 'capabilities.json' file regardless of where
# python or the package is installed.
try:
    escpos_dir = os.path.dirname(escpos.__file__)
    escpos_json = os.path.join(escpos_dir, 'capabilities.json')
    escpos_data = (escpos_json, 'escpos')
    print(f"Found escpos data file at: {escpos_json}")
except Exception as e:
    print(f"WARNING: Could not find escpos/capabilities.json. {e}")
    print("If printing fails, you may need to add it manually.")
    escpos_data = None

# --- Bundled Data ---
# Create a list of data files and directories to bundle.
# The format is a list of tuples:
# ('source_path_on_disk', 'destination_path_in_bundle')
bundled_data = [
    ('config.json', '.'),      # Bundles config.json to the root
    ('receipts.csv', '.'),     # Bundles receipts.csv to the root
    ('static', 'static'),      # Bundles the entire 'static' folder
    ('templates', 'templates') # Bundles the entire 'templates' folder
]

# Add the escpos data file if we found it
if escpos_data:
    bundled_data.append(escpos_data)

# --- Hidden Imports ---
# List of libraries that PyInstaller might miss, especially
# dependencies of escpos.
hidden_imports = [
    'escpos.printer',
    'serial',    # For Serial printer connection
    'usb.core',  # For USB printer connection (in case)
    'qrcode',    # For barcodes (escpos dependency)
    'PIL',       # For images (escpos dependency)
]

# --- Main Analysis ---
# This block analyzes your app.py to find all its dependencies.
a = Analysis(
    ['app.py'],  # Your main application script
    pathex=[],
    binaries=[],
    datas=bundled_data,      # Add our data files here
    hiddenimports=hidden_imports,  # Add libraries PyInstaller might miss
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# --- Executable Configuration ---
# This block defines the final executable.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,  # Include the data files from the Analysis
    [],
    name='ReceiptPrinterApp',  # The name of your .exe file
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,         # True = shows a console window (good for servers)
                          # False = hides console (good for GUI apps)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='static/favicon.png' # You can set your app icon here
)

# --- One-Dir Bundle (Alternative) ---
# If you prefer a folder with all files instead of a single .exe,
# comment out the 'exe' block above and uncomment this 'coll' block.
# coll = COLLECT(
#     exe,
#     a.scripts,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='ReceiptPrinterApp_folder',
# )