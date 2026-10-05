# -*- mode: python ; coding: utf-8 -*-
# 神机 MT5 桌面版打包（PyInstaller onedir）
# 构建：pyinstaller ShenjiMT5.spec --noconfirm
# 产物：dist/ShenjiMT5/ShenjiMT5.exe（onedir 需整目录分发）

import os

REPO = os.path.abspath(SPECPATH)

a = Analysis(
    ['tools/run_app.py'],
    pathex=[REPO],
    binaries=[],
    datas=[
        ('web/dist', 'web/dist'),                          # fork 前端 SPA
        ('dashboard/templates', 'dashboard/templates'),
        ('dashboard/static', 'dashboard/static'),
    ],
    hiddenimports=[
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'webview.platforms.edgechromium', 'webview.platforms.winforms',
        'anyio._backends._asyncio',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PyQt5', 'PyQt6'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShenjiMT5',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # 无控制台窗口
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='ShenjiMT5',
)
