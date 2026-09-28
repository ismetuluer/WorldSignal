"""Entry point of the packaged program (WorldSignal.exe).

The program runs from the folder the user unpacked it to and updates that folder itself from GitHub
releases (worldsignal/updater.py). User data never lives here: see worldsignal/paths.py.
"""

import sys

from worldsignal.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
