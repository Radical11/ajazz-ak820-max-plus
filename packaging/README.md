# AK820 Studio packaging

Build the app folder (PyInstaller, onedir) with `packaging\build.bat` from the project root.
It runs `npm run build` in `ui/`, installs PyInstaller into `venv` if missing, and writes
`dist-app\AK820Studio\AK820Studio.exe`.

To make the installer, install Inno Setup 6 and run `iscc packaging\installer.iss` from the project root.
The installer is written to `dist-installer\AK820Studio-Setup-2.0.0.exe`.
It installs per user into `%LOCALAPPDATA%\Programs\AK820 Studio` and needs no admin rights.

Optional installer tasks: desktop icon, and "Start with Windows" (HKCU Run entry, starts with `--minimized`).

Build intermediates go to `build-app\` and can be deleted at any time.
Spec: `packaging\ak820studio.spec`. Excluded: PyQt5/6, tkinter, matplotlib, GPUtil, pynput.
