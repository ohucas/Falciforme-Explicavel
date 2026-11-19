# Execute este script na pasta do projeto, no Windows, após testar desktop.py.
$ErrorActionPreference = 'Stop'
& .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências.' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name FalciformeExplicavel --icon assets/icone.ico --add-data 'assets;assets' desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o aplicativo.' }
Write-Host 'Saída: dist\FalciformeExplicavel\FalciformeExplicavel.exe. Mantenha a pasta inteira.'
