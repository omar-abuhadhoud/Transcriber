# -*- mode: python ; coding: utf-8 -*-
import glob
import os
import site
import sys
from PyInstaller.utils.hooks import collect_all

sys.path.insert(0, os.path.abspath('.'))
from transcriber.version import VERSION_TUPLE, __version__

# Stamps the exe so Explorer's Details tab and any installer can read the version.
VERSION_RESOURCE = os.path.join('build', 'file_version_info.txt')
os.makedirs('build', exist_ok=True)
with open(VERSION_RESOURCE, 'w', encoding='utf-8') as _f:
    _f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={VERSION_TUPLE}, prodvers={VERSION_TUPLE},
                    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', 'Transcriber'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'Transcriber'),
      StringStruct('OriginalFilename', 'Transcriber.exe'),
      StringStruct('ProductName', 'Transcriber'),
      StringStruct('ProductVersion', '{__version__}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ]
)
""")

datas = [
    ('icon.ico', '.'),
    # Silero VAD weights, loaded at runtime to split long audio.
    (os.path.join('transcriber', 'assets', 'silero_vad_v6.onnx'),
     os.path.join('transcriber', 'assets')),
]
binaries = []

for site_dir in site.getsitepackages():
    for pattern in (
        os.path.join(site_dir, 'nvidia', '**', 'bin', '*.dll'),
        os.path.join(site_dir, 'torch', 'lib', '*.dll'),
    ):
        for dll_path in glob.glob(pattern, recursive=True):
            binaries.append((dll_path, '.'))

hiddenimports = [
    # Engines are resolved at runtime via importlib, so PyInstaller cannot see them.
    'transcriber.engines.qwen_asr',
]
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('transformers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # torch and nvidia stay in: the Qwen3-ASR engines run on them.
    excludes=['torchaudio', 'torchvision', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Transcriber',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
    version=VERSION_RESOURCE,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Transcriber',
)
