"""Entry point used by the build script (PyInstaller) and for running from source."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))

from winiso.app import main  # noqa: E402

if __name__ == "__main__":
    main()
