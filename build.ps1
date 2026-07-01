Write-Host "Installing PyInstaller..."
pip install pyinstaller

Write-Host "Installing Inno Setup..."
choco install innosetup -y

Write-Host "Running PyInstaller..."
# We use --noconfirm to overwrite previous builds and --noconsole to hide the terminal window in the final product.
python -m PyInstaller --name "INDRA" --noconfirm --noconsole --distpath "build_dist" `
    --add-data "assets;assets" `
    --add-data "logo;logo" `
    --add-data "core;core" `
    --hidden-import "PyQt6" `
    --hidden-import "psutil" `
    --hidden-import "cv2" `
    --hidden-import "mss" `
    --hidden-import "pyautogui" `
    --hidden-import "pyperclip" `
    --hidden-import "winreg" `
    --hidden-import "webrtcvad" `
    main.py

Write-Host "Building Setup.exe with Inno Setup..."
# choco installs to C:\Program Files (x86)\Inno Setup 6\iscc.exe
if (Test-Path "C:\Program Files (x86)\Inno Setup 6\iscc.exe") {
    & "C:\Program Files (x86)\Inno Setup 6\iscc.exe" "installer.iss"
    Write-Host "Build Complete! Installer located in dist\INDRA_Setup_v1.1.exe"
} else {
    Write-Host "ERROR: iscc.exe not found! Please compile installer.iss manually."
}
