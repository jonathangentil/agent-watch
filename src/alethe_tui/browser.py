"""Abre a interface local no navegador do sistema, incluindo Windows via WSL."""
import platform
import shutil
import subprocess
import webbrowser


def open_browser(url):
    if "microsoft" in platform.release().lower():
        powershell = shutil.which("powershell.exe")
        if powershell:
            try:
                result = subprocess.run(
                    [powershell, "-NoProfile", "-NonInteractive", "-Command",
                     "$ErrorActionPreference = 'Stop'; Start-Process -FilePath ([Console]::In.ReadToEnd())"],
                    input=url, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                )
                return result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                return False
    return webbrowser.open(url)
