@echo off
setlocal
set ROOT=%~dp0

rem Ensure Rust/Cargo and the Windows Resource Compiler are on PATH
set PATH=%USERPROFILE%\.cargo\bin;%PATH%
set PATH=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64;%PATH%

rem Read version from single source of truth
set /p VERSION=<"%ROOT%VERSION"
echo [build] Building Hime v%VERSION%...
echo.

echo [build] Step 1/2: Building backend with PyInstaller...
python "%ROOT%..\scripts\build_backend.py"
if errorlevel 1 (
    echo [build] Backend build FAILED
    exit /b 1
)

echo [build] Step 2/2: Building Tauri app...
cd "%ROOT%frontend"
npm run tauri build
if errorlevel 1 (
    echo [build] Tauri build FAILED
    exit /b 1
)

echo.
echo [build] Done.
echo [build] Installer: frontend\src-tauri\target\release\bundle\nsis\Hime_%VERSION%_x64-setup.exe
