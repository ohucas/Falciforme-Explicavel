# Execute a partir da raiz: python -m PyInstaller empacotar/Falciforme.spec --clean --noconfirm
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

raiz = Path(SPECPATH).parent
datas = [
    (str(raiz / "app.py"), "."),
    (str(raiz / "assets"), "assets"),
    (str(raiz / "exemplos"), "exemplos"),
    (str(raiz / ".streamlit"), ".streamlit"),
    (str(raiz / "src" / "reports"), "src/reports"),
    *[(str(arquivo), "src") for arquivo in (raiz / "src").glob("*.py")],
]
binaries = []
hiddenimports = []
# app.py é executado dinamicamente pelo Streamlit; seus imports precisam constar aqui.
for pacote in ("streamlit", "plotly", "pypdf", "reportlab"):
    dados, binarios, imports = collect_all(pacote)
    datas += dados
    binaries += binarios
    hiddenimports += imports
datas += copy_metadata("streamlit", recursive=True)
hiddenimports += [
    "pandas",
    "matplotlib.backends.backend_agg",
    "src.analise",
    "src.paciente",
    "src.historico",
    "src.documentos",
    "src.importacao_ui",
    "src.reports.pdf",
]

a = Analysis(
    [str(raiz / "iniciar_app.py")],
    pathex=[str(raiz)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    runtime_hooks=[],
    excludes=["src.pesquisa", "pytest", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FalciformeExplicavel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(raiz / "assets" / "icone.ico") if sys.platform == "win32" else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="FalciformeExplicavel",
)
