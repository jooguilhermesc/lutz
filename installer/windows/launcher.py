"""
lutz-ui — silent Windows launcher.

Starts `lutz web` as a background process (no visible console window)
and opens the browser. Compiled with PyInstaller --windowed so no
terminal appears when the user double-clicks the Start Menu shortcut.

Build:
    pyinstaller --onefile --windowed --name lutz-ui installer/windows/launcher.py
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PORT = 8765
URL = f"http://localhost:{PORT}"


def main() -> None:
    # lutz.exe lives next to this launcher
    exe_dir = Path(sys.executable).parent
    lutz = exe_dir / "lutz.exe"

    if not lutz.exists():
        import ctypes
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            f"Não foi possível encontrar lutz.exe em:\n{exe_dir}",
            "Lutz Research — erro",
            0x10,  # MB_ICONERROR
        )
        return

    # Start the server detached from this process
    subprocess.Popen(
        [str(lutz), "web", "--port", str(PORT), "--no-browser"],
        creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
        close_fds=True,
    )

    # Give the server a moment to start, then open the browser
    time.sleep(1.5)
    webbrowser.open(URL)


if __name__ == "__main__":
    main()
