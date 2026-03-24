@echo off
setlocal
set ROOT=%~dp0

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
echo [build] Installer: frontend\src-tauri\target\release\bundle\nsis\Hime_0.1.0_x64-setup.exe
