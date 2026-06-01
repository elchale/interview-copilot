"""Entry point for PyInstaller — avoids relative import issues."""

import sys
import os

if getattr(sys, "frozen", False):
    # Running as PyInstaller exe — add the bundle dir to path
    sys.path.insert(0, sys._MEIPASS)

from src.main import main

if __name__ == "__main__":
    main()
