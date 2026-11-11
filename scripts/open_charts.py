"""Print the 13 charts you need to open manually in MT5.

The MT5 Python package cannot open charts programmatically — this script
just prints the exact (symbol, timeframe) list so you can open them by
hand in the terminal.

After opening, save the layout as a profile:
    File -> Profiles -> Save As -> GODSWILL_LIVE
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from research.validation import FROZEN_PORTFOLIO


# Deduplicate (symbol, timeframe) pairs — one chart per combo
CHART_SPECS = sorted(
    {(symbol, tf) for symbol, tf, _sid in FROZEN_PORTFOLIO},
    key=lambda x: (x[0], ["M1","M5","M15","M30","H1","H4","D1","W1"].index(x[1])),
)


def main() -> int:
    print()
    print("=" * 60)
    print(" MT5 CHARTS TO OPEN MANUALLY")
    print("=" * 60)
    print()
    print(f" Total charts: {len(CHART_SPECS)}")
    print()
    print(" Open each one in MT5:")
    print("   Ctrl+N -> type symbol -> Enter")
    print("   Then click the timeframe button (M15, M30, H1, H4, D1)")
    print()
    print(" Your FROZEN_PORTFOLIO combos:")
    print()
    print(f" {'#':<4} {'Symbol':<12} {'TF':<5} {'Strategy'}")
    print(" " + "-" * 45)
    for i, (symbol, tf) in enumerate(CHART_SPECS, 1):
        # Find which strategy this combo uses
        strat = next(
            sid for sym, tframe, sid in FROZEN_PORTFOLIO
            if sym == symbol and tframe == tf
        )
        print(f" {i:<4} {symbol:<12} {tf:<5} {strat}")
    print()
    print("=" * 60)
    print(" AFTER OPENING ALL CHARTS")
    print("=" * 60)
    print("  1. View -> Auto Arrange  (tiles them in a grid)")
    print("  2. File -> Profiles -> Save As -> GODSWILL_LIVE")
    print("     (so charts restore automatically next MT5 launch)")
    print("  3. Run the live engine:")
    print("     python main.py live --poll 60")
    print()
    print(" Note: MT5 Python API has NO chart manipulation functions.")
    print("       Arrows on charts require an MQL5 EA (see mql5/ folder).")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())