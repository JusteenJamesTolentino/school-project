# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Justeen/code/school/admin2/scheduling.py'],
    pathex=[
        'C:/Users/Justeen/code/school',
        'C:/Users/Justeen/code/school/admin1',
        'C:/Users/Justeen/code/school/admin2',
    ],
    binaries=[],
    datas=[('C:/Users/Justeen/code/school/admin1/scheduling_system/scheduling.db', 'scheduling_system')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Admin2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
