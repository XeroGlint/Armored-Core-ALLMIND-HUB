@echo off
REM Builds a standalone ArmoredCoreLauncher.exe (no Python needed to run it)
REM Prefers Python 3.13/3.12/3.11 (very new Python versions can lack package wheels)
set PYV=
for %%v in (3.13 3.12 3.11) do (py -%%v --version >nul 2>&1 && if not defined PYV set PYV=-%%v)
echo Using: py %PYV%

REM Close a running copy and clear the old build so Windows doesn't block the overwrite
taskkill /f /im ArmoredCoreLauncher.exe >nul 2>&1
timeout /t 2 /nobreak >nul
if exist dist\ArmoredCoreLauncher.exe del /f /q dist\ArmoredCoreLauncher.exe
if exist dist\ArmoredCoreLauncher.exe (
  echo.
  echo Could not delete dist\ArmoredCoreLauncher.exe - it is locked.
  echo Close the launcher, wait a few seconds for antivirus, then run this again.
  pause & exit /b 1
)

py %PYV% -m pip install -r requirements.txt || goto :err
py %PYV% -m PyInstaller --noconfirm --clean --onefile --windowed --name ArmoredCoreLauncher ac_launcher.py || goto :err
echo.
echo Done: dist\ArmoredCoreLauncher.exe
pause & exit /b 0
:err
echo Build failed. & pause & exit /b 1
