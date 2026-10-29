"""Build helper: render the application icon to build/app.ico."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.ui.icons import app_icon  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    pm = app_icon().pixmap(256, 256)
    out = ROOT / "build" / "app.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    ok = pm.save(str(out), "ICO")
    print("icon saved:", out, ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
