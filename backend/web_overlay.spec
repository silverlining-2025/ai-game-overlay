# web_overlay.spec — PyInstaller spec for the AI companion overlay
#
# Build: cd backend && pyinstaller web_overlay.spec --clean --noconfirm
# Output: dist/ai-companion/ (one-dir mode for faster startup)
#
# After build, copy dist/ai-companion/ to frontend/src-tauri/bin/
# Then run: cd frontend && npm run tauri build

from PyInstaller.utils.hooks import collect_submodules
import sys
import os

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
hidden += collect_submodules('yaml')
hidden += [
    'ctypes.wintypes',
    'PIL.Image',
    'cv2',
    'numpy',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'sniffio',
    'edge_tts',
    'pygame',
    'sqlite3',
    # Google Gemini SDK (optional, for multi-API support)
    'google.genai',
    'google.genai.types',
    # OpenAI SDK (optional)
    'openai',
]

a = Analysis(
    ['tools/web_overlay.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        # Data files needed at runtime
        ('data/*.yaml', 'backend/data'),
        ('data/*.txt', 'backend/data'),
        ('data/games/*.yaml', 'backend/data/games'),
        ('static/*', 'backend/static'),
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=['runtime_hook_comtypes.py'],
    excludes=[
        # Heavy ML deps — not needed for cloud-only API mode
        'torch', 'transformers', 'accelerate', 'torchao', 'torchvision',
        'easyocr', 'scipy', 'scikit-learn', 'sklearn',
        # Dev/test deps
        'tkinter', 'pytest', 'pytest_asyncio',
        # Training pipeline tools (not needed at runtime)
        'yt_dlp', 'imagehash',
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
    name='ai-companion',
    debug=False,
    strip=False,
    upx=True,
    console=False,  # No console window in production
    icon='../frontend/src-tauri/icons/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='ai-companion',
)
