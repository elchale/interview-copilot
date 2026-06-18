"""Entry point for the cloud capture agent exe (PyInstaller)."""

import sys

if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)

from cloud.agent import main

if __name__ == "__main__":
    main()
