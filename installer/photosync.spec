# PyInstaller spec for the PhotoSync desktop app.
# Build:  desktop\.venv\Scripts\pyinstaller installer\photosync.spec
from pathlib import Path

root = Path(SPECPATH).parent
desktop = root / "desktop"

a = Analysis(
    [str(desktop / "main.py")],
    pathex=[str(desktop)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "zeroconf",
        "qrcode",
        "cryptography",
    ],
    excludes=["tkinter", "flask"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoSync",
    console=False,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="PhotoSync",
)
