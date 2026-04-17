"""
Build script — package Cold Email Writer into a single .exe
Usage: python build.py
"""

import subprocess
import sys
import os

def main():
    print("=" * 50)
    print("  Building Cold Email Writer .exe")
    print("=" * 50)

    # Ensure PyInstaller is installed
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "ColdEmailWriter",
        "--add-data", f"app.py{os.pathsep}.",
        "--hidden-import", "gradio",
        "--hidden-import", "httpx",
        "--collect-all", "gradio",
        "--collect-all", "gradio_client",
        "--noconfirm",
        "--clean",
        "app.py",
    ]

    print("\nRunning PyInstaller...\n")
    subprocess.check_call(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    print("\n" + "=" * 50)
    print("  Build complete!")
    print("  Output: dist/ColdEmailWriter.exe")
    print("=" * 50)


if __name__ == "__main__":
    main()
