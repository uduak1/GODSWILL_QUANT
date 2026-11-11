"""GODSWILL entry point."""
from __future__ import annotations

import argparse
import sys
import matplotlib.pyplot as plt

from configuration.settings import Settings, resolve_config_path
from database.connection import Database
from app_logging.setup import configure_logging
from core.enums import Timeframe
from core.exceptions import MarketDataError, MT5ConnectionError

VERSION = "0.4.4"   # bumped: Global dark theme applied to QApplication


def _load() -> tuple[Settings, Database, "logging.Logger"]:
    path = resolve_config_path()
    try:
        settings = Settings.load(path)
    except Exception as exc:
        print(f"[FATAL] Config load failed: {exc}", file=sys.stderr)
        sys.exit(2)
    settings.app.data_dir.mkdir(parents=True, exist_ok=True)
    logger = configure_logging(settings.app.data_dir, settings.app.log_level)
    db = Database(settings.database.path)
    db.initialize()
    logger.info("Config loaded from %s; DB schema v%s", path, db.schema_version())
    return settings, db, logger


# --------------------------------------------------------------------------- #
# Utility commands
# --------------------------------------------------------------------------- #

def cmd_doctor(args):
    print(f"GODSWILL {VERSION} — environment check")
    missing = []
    for mod in ("pydantic", "pandas", "numpy", "PySide6", "matplotlib",
                "pyqtgraph", "MetaTrader5"):
        try:
            __import__(mod)
            print(f"  \u2713 {mod}")
        except ImportError:
            missing.append(mod)
            print(f"  \u2717 {mod} MISSING")
    settings, db, _ = _load()
    print(f"  \u2713 database at {db.db_path} (schema v{db.schema_version()})")
    if missing:
        print(f"\nInstall: pip install {' '.join(missing)}")
        return 1
    print("\nEnvironment OK.")
    return 0


def cmd_discover(args):
    from market_data.mt5_discovery import discover_terminal_paths
    paths = discover_terminal_paths()
    if not paths:
        print("No MT5 terminals detected.")
        return 1
    print(f"Detected {len(paths)} terminal(s):")
    for i, p in enumerate(paths, 1):
        print(f"  [{i}] {p}")
    return 0


def cmd_version(args):
    _, db, _ = _load()
    print(f"GODSWILL {VERSION} — schema v{db.schema_version()}")
    return 0


def cmd_run(args):
    """Launch the tabbed PySide6 trading terminal with Settings editor."""
    from PySide6.QtWidgets import QApplication
    from dashboard.main_window import MainWindow
    from dashboard.theme import apply_dark_theme   # <-- ADDED

    settings, db, _ = _load()
    app = QApplication(sys.argv)
    apply_dark_theme(app)                          # <-- ADDED
    win = MainWindow(
        settings=settings,
        db=db,
        db_version=db.schema_version(),
    )
    win.show()
    return app.exec()


# --------------------------------------------------------------------------- #
# Data commands
# --------------------------------------------------------------------------- #

def cmd_data(args):
    from market_data.mt5_provider import MT5MarketDataProvider
    from market_data.validation import validate_ohlcv
    settings, db, _ = _load()
    provider = MT5MarketDataProvider(
        settings.mt5, db,
        symbol_suffix=args.suffix, symbol_prefix=args.prefix,
    )
    try:
        tf = Timeframe(args.timeframe)
    except ValueError:
        print(f"[FATAL] Unknown timeframe: {args.timeframe}")
        return 2
    try:
        df = provider.get_candles(args.symbol, tf, count=args.count)
    except (MarketDataError, MT5ConnectionError) as exc:
        print(f"[MT5 ERROR] {exc}")
        return 3
    print(validate_ohlcv(df, args.symbol, tf).summary())
    return 0


def cmd_specs(args):
    from market_data.mt5_provider import MT5MarketDataProvider
    settings, db, _ = _load()
    provider = MT5MarketDataProvider(
        settings.mt5, db,
        symbol_suffix=args.suffix, symbol_prefix=args.prefix,
    )
    try:
        specs = provider.get_symbol_specs(args.symbol)
    except (MarketDataError, MT5ConnectionError) as exc:
        print(f"[MT5 ERROR] {exc}")
        return 3
    width = max(len(k) for k in specs)
    print(f"Specs for {args.symbol}:")
    for k, v in specs.items():
        print(f"  {k:<{width}} : {v}")
    return 0


def cmd_symbols(args):
    from market_data.mt5_provider import MT5MarketDataProvider
    settings, db, _ = _load()
    provider = MT5MarketDataProvider(settings.mt5, db)
    try:
        names = provider.list_available_symbols()
    except (MarketDataError, MT5ConnectionError) as exc:
        print(f"[MT5 ERROR] {exc}")
        return 3
    pattern = (args.pattern or "").upper()
    filtered = [n for n in names if pattern in n.upper()] if pattern else names
    print(f"{len(filtered)} symbols matching '{args.pattern}' (showing {args.limit}):")
    for n in filtered[:args.limit]:
        print(f"  {n}")
    if len(filtered) > args.limit:
        print(f"  ... and {len(filtered) - args.limit} more")
    return 0


# --------------------------------------------------------------------------- #
# Backtest + Scan
# --------------------------------------------------------------------------- #

def _load_strategies():
    from strategies.s01_liquidity_sweep import LiquiditySweepReversal
    from strategies.s02_bos_fvg import BOSFVGStrategy
    from strategies.s03_choch_reversal import CHOCHReversal
    from strategies.s04_order_block import OrderBlockRetest
    from strategies.s05_supply_demand import SupplyDemand
    from strategies.s06_breakout_retest import BreakoutRetest
    from strategies.s07_trend_continuation import TrendContinuation
    from strategies.s08_classical_patterns import DoubleTopBottom
    from strategies.s09_range_reversal import RangeReversal
    from strategies.s10_multi_structure import MultiStructureConfluence
    return {
        "S01": LiquiditySweepReversal(), "S02": BOSFVGStrategy(),
        "S03": CHOCHReversal(), "S04": OrderBlockRetest(),
        "S05": SupplyDemand(), "S06": BreakoutRetest(),
        "S07": TrendContinuation(), "S08": DoubleTopBottom(),
        "S09": RangeReversal(), "S10": MultiStructureConfluence(),
    }


def cmd_backtest(args):
    from market_data.mt5_gateway import MT5Gateway
    from risk_management.engine import RiskManager
    from backtesting.engine import Backtester

    settings, _, _ = _load()
    gateway = MT5Gateway(settings.mt5)

    try:
        tf = Timeframe(args.timeframe)
    except ValueError:
        print(f"[FATAL] {args.timeframe}")
        return 2

    try:
        with gateway.connection() as gw:
            df = gw.get_rates(args.symbol, tf, count=args.count)
            specs = gw.symbol_specs(args.symbol)
    except Exception as exc:
        print(f"[MT5 ERROR] {exc}")
        return 3

    strategies = _load_strategies()
    strat = strategies.get(args.strategy.upper())
    if not strat:
        print("[FATAL] Unknown strategy")
        return 2

    rm = RiskManager(settings.risk)
    if args.fixed_risk > 0:
        rm.config.fixed_risk_amount = args.fixed_risk

    bt = Backtester(strat, rm, initial_balance=args.balance, spread_pips=args.spread)
    result = bt.run(df, args.symbol, specs, timeframe=tf.value)

    print("=" * 50)
    print(f" BACKTEST RESULTS: {result.strategy_id} ")
    print("=" * 50)
    print(f"Initial : ${result.initial_balance:,.2f}")
    print(f"Final   : ${result.final_balance:,.2f}")
    print(f"Net     : ${(result.final_balance - result.initial_balance):,.2f}")
    print(f"Trades  : {result.total_trades}")
    wr = (result.winning_trades / result.total_trades * 100) if result.total_trades else 0
    print(f"Win Rate: {wr:.1f}%")
    print(f"PF      : {result.profit_factor:.2f}")
    print(f"Max DD  : {result.max_drawdown_pct:.2f}%")
    print("=" * 50)

    plt.figure(figsize=(10, 5))
    plt.plot(result.equity_curve, color='#00FF00', linewidth=2)
    plt.title(f"Equity Curve - {result.strategy_id} ({args.symbol})", fontweight='bold')
    plt.xlabel("Trade Number")
    plt.ylabel("Balance ($)")
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.show()
    return 0


def cmd_scan_all(args):
    from market_data.mt5_gateway import MT5Gateway
    from risk_management.engine import RiskManager
    from backtesting.engine import Backtester

    settings, _, _ = _load()
    gateway = MT5Gateway(settings.mt5)

    timeframes = [
        Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30,
        Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1,
    ]
    symbols = [
        "XAUUSD", "XAGUSD", "USOIL", "UKOIL",
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
        "#BTCUSD", "#ETHUSD", "GER40",
    ]

    all_strategies = _load_strategies()
    requested = [s.strip().upper() for s in args.strategies.split(",")]
    active = {k: v for k, v in all_strategies.items() if k in requested}
    if not active:
        print("[FATAL] No valid strategies")
        return 2

    def get_spread(s):
        s = s.upper()
        if "XAU" in s: return 0.25
        if "XAG" in s: return 0.03
        if "OIL" in s: return 0.03
        if "BTC" in s: return 30.0
        if "ETH" in s: return 2.5
        if "GER" in s: return 1.0
        if "JPY" in s: return 0.015
        return 0.00015

    rm = RiskManager(settings.risk)
    rm.config.fixed_risk_amount = args.fixed_risk

    try:
        with gateway.connection() as gw:
            for symbol in symbols:
                try:
                    specs = gw.symbol_specs(symbol)
                except Exception:
                    continue
                spread = get_spread(symbol)
                print("=" * 90)
                print(f" SYMBOL: {symbol} (Spread: {spread})")
                print("=" * 90)
                for tf in timeframes:
                    try:
                        df = gw.get_rates(symbol, tf, count=args.count)
                    except Exception:
                        continue
                    results = []
                    for sid, s in active.items():
                        try:
                            bt = Backtester(s, rm, initial_balance=10000.0, spread_pips=spread)
                            res = bt.run(df, symbol, specs, timeframe=tf.value)
                            results.append({
                                "sid": sid,
                                "net": res.final_balance - res.initial_balance,
                                "wr": (res.winning_trades / res.total_trades * 100) if res.total_trades else 0,
                                "pf": res.profit_factor,
                                "dd": res.max_drawdown_pct,
                                "n": res.total_trades,
                            })
                        except Exception:
                            pass
                    if not results:
                        continue
                    results.sort(key=lambda x: x["net"], reverse=True)
                    print(f" [{tf.value}]")
                    for r in results:
                        tag = "OK" if r["net"] > 0 else "LOSS"
                        print(f"   [{tag}] {r['sid']}: ${r['net']:+,.2f} | "
                              f"WR:{r['wr']:.1f}% | PF:{r['pf']:.2f} | "
                              f"DD:{r['dd']:.2f}% | N={r['n']}")
                    print()
    except Exception as exc:
        print(f"[MT5 ERROR] {exc}")
        return 3

    print("SCAN COMPLETE")
    return 0


# --------------------------------------------------------------------------- #
# OOS Validation
# --------------------------------------------------------------------------- #

def cmd_validate(args):
    from market_data.mt5_gateway import MT5Gateway
    from risk_management.engine import RiskManager
    from research.validation import PortfolioValidator
    import os

    settings, _, _ = _load()
    gateway = MT5Gateway(settings.mt5)
    rm = RiskManager(settings.risk)
    rm.config.fixed_risk_amount = args.fixed_risk
    validator = PortfolioValidator(gateway, rm)

    print(f"\nOOS VALIDATION")
    print(f"In-sample skipped: {args.in_sample} recent candles")
    print(f"OOS window: {args.oos} older candles")
    print(f"Risk: ${args.fixed_risk}\n")

    results = validator.validate_all(oos_count=args.oos, in_sample_count=args.in_sample)
    passed = [r for r in results if r.passed]

    print("=" * 105)
    print(f" RESULT: {len(passed)}/{len(results)} combos passed OOS")
    print("=" * 105)
    print(f"{'Sym':<10} {'TF':<4} {'S':<4} {'N':<5} {'PF':<6} "
          f"{'DD%':<6} {'P&L':<13} {'T/day':<7} Verdict")
    print("-" * 105)
    for r in sorted(results, key=lambda x: (not x.passed, -x.oos_pf)):
        tag = "PASS" if r.passed else "FAIL"
        print(f"[{tag}] {r.symbol:<9} {r.timeframe:<3} {r.strategy_id:<3} "
              f"{r.oos_trades:<4} {r.oos_pf:<5.2f} {r.oos_dd:<5.1f} "
              f"${r.oos_net_profit:>+11,.0f} {r.trades_per_day:<6.2f} {r.reason}")

    print("\n" + "=" * 105)
    print(f" DEPLOYABLE PORTFOLIO: {len(passed)} combos")
    total_tpd = sum(r.trades_per_day for r in passed)
    print(f" Expected portfolio frequency: ~{total_tpd:.1f} trades/day")
    print("=" * 105)

    os.makedirs("reports", exist_ok=True)
    validator.save_report(results, "reports/oos_validation.json")
    print(f"\nReport: reports/oos_validation.json")
    return 0


# --------------------------------------------------------------------------- #
# Live signal engine
# --------------------------------------------------------------------------- #

def cmd_live(args):
    from execution.live_engine import LiveEngine
    from research.validation import FROZEN_PORTFOLIO

    settings, db, _ = _load()

    engine = LiveEngine(
        settings=settings,
        db=db,
        portfolio=FROZEN_PORTFOLIO,
        poll_seconds=args.poll,
        dry_run=args.dry_run,
    )

    mode = "DRY RUN (no chart arrows)" if args.dry_run else "FULL (arrows on MT5)"
    print(f"\nLIVE SIGNAL ENGINE")
    print(f"Mode: {mode}")
    print(f"Poll: {args.poll}s | Combos: {len(FROZEN_PORTFOLIO)}")
    if not args.dry_run:
        print(f"NOTE: MT5 Python API has no chart manipulation.")
        print(f"      Signals log to console + DB. Chart arrows need MQL5 EA.")
    print(f"\nPress Ctrl+C to stop.\n")

    try:
        engine.start()
    except KeyboardInterrupt:
        engine.stop()
        print("\nEngine stopped.")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(prog="godswill")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(func=cmd_doctor)
    sub.add_parser("discover").set_defaults(func=cmd_discover)
    sub.add_parser("version").set_defaults(func=cmd_version)
    sub.add_parser("run").set_defaults(func=cmd_run)

    # data
    p = sub.add_parser("data")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--timeframe", default="H1", choices=[t.value for t in Timeframe])
    p.add_argument("--count", type=int, default=1000)
    p.add_argument("--suffix", default="")
    p.add_argument("--prefix", default="")
    p.set_defaults(func=cmd_data)

    # specs
    p = sub.add_parser("specs")
    p.add_argument("--symbol", required=True)
    p.add_argument("--suffix", default="")
    p.add_argument("--prefix", default="")
    p.set_defaults(func=cmd_specs)

    # symbols
    p = sub.add_parser("symbols")
    p.add_argument("--pattern", default="")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_symbols)

    # backtest
    p = sub.add_parser("backtest")
    p.add_argument("--strategy", default="S05")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="H1")
    p.add_argument("--count", type=int, default=5000)
    p.add_argument("--balance", type=float, default=10000.0)
    p.add_argument("--spread", type=float, default=0.0)
    p.add_argument("--fixed-risk", type=float, default=0.0)
    p.set_defaults(func=cmd_backtest)

    # scan-all
    p = sub.add_parser("scan-all")
    p.add_argument("--strategies", default="S01,S02,S03,S04,S05,S06,S07,S08,S09,S10")
    p.add_argument("--count", type=int, default=3000)
    p.add_argument("--fixed-risk", type=float, default=100.0)
    p.set_defaults(func=cmd_scan_all)

    # validate
    p = sub.add_parser("validate")
    p.add_argument("--oos", type=int, default=2000)
    p.add_argument("--in-sample", type=int, default=1000)
    p.add_argument("--fixed-risk", type=float, default=100.0)
    p.set_defaults(func=cmd_validate)

    # live
    p = sub.add_parser("live")
    p.add_argument("--poll", type=int, default=60,
                   help="seconds between market polls")
    p.add_argument("--dry-run", action="store_true",
                   help="run without annotating MT5 charts (DB + logs only)")
    p.set_defaults(func=cmd_live)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())