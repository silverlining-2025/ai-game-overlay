# web_overlay.spec — PyInstaller spec for the AI companion overlay
# Build: cd backend && pyinstaller web_overlay.spec --clean --noconfirm

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hidden = []
hidden += collect_submodules('uvicorn')
hidden += collect_submodules('fastapi')
hidden += collect_submodules('starlette')
hidden += collect_submodules('sse_starlette')
hidden += collect_submodules('dxcam')
hidden += collect_submodules('comtypes')
hidden += collect_submodules('mss')
hidden += collect_submodules('anthropic')
hidden += collect_submodules('httpx')
hidden += collect_submodules('httpcore')
hidden += collect_submodules('h11')
hidden += [
    'ctypes.wintypes',
    'PIL.Image',
    'cv2',
    'numpy',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'sniffio',
]

a = Analysis(
    ['tools/web_overlay.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('data/*.txt', 'backend/data'),
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=['runtime_hook_comtypes.py'],
    excludes=[
        'torch', 'transformers', 'accelerate', 'torchao', 'torchvision',
        'easyocr', 'tkinter', 'pytest', 'pytest_asyncio',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ai-game-overlay',
    debug=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='ai-game-overlay',
)
