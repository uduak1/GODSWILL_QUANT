"""Diagnostic: check if strategies generate signals on current data."""
from configuration.settings import Settings, resolve_config_path
from market_data.mt5_gateway import MT5Gateway
from core.enums import Timeframe
from strategies.s05_supply_demand import SupplyDemand
from strategies.s07_trend_continuation import TrendContinuation
from strategies.s03_choch_reversal import CHOCHReversal

COMBOS = [
    ("XAUUSD", "M15", "S05"),
    ("GBPUSD", "H4",  "S07"),
    ("UKOIL",  "M30", "S05"),
    ("USDCHF", "D1",  "S03"),
    ("GER40",  "H4",  "S07"),
    ("XAGUSD", "M30", "S05"),
    ("GER40",  "H1",  "S05"),
    ("USOIL",  "H1",  "S05"),
    ("EURUSD", "M15", "S05"),
    ("GER40",  "M15", "S05"),
    ("EURGBP", "H1",  "S05"),
    ("XAUUSD", "M30", "S07"),
    ("XAUUSD", "H1",  "S05"),
]

STRATS = {
    "S03": CHOCHReversal(),
    "S05": SupplyDemand(),
    "S07": TrendContinuation(),
}


def main():
    settings = Settings.load(resolve_config_path())
    gateway = MT5Gateway(settings.mt5)

    print(f"{'Combo':<25} {'Bars':<6} {'Total':<7} {'Last100':<8} {'Verdict'}")
    print("-" * 75)

    with gateway.connection() as gw:
        for symbol, tf_str, sid in COMBOS:
            try:
                tf = Timeframe(tf_str)
                df = gw.get_rates(symbol, tf, count=300)
                if df is None or len(df) < 50:
                    print(f"{symbol} {tf_str} {sid:<4}  INSUFFICIENT DATA")
                    continue

                # Test on last closed bar (like live engine does)
                df_closed = df.iloc[:-1]
                strat = STRATS.get(sid)
                all_signals = strat.generate_signals(df_closed, symbol, tf_str)

                # Also test on recent window to see signal rate
                df_test = df_closed.iloc[-100:]
                recent_signals = strat.generate_signals(df_test, symbol, tf_str)

                last_ts = df_closed.index[-1]
                signals_on_last = [
                    s for s in all_signals
                    if s.created_at == last_ts.to_pydatetime()
                ]

                if signals_on_last:
                    verdict = f"LIVE: {signals_on_last[0].direction.value}"
                elif recent_signals:
                    verdict = f"quiet now (had {len(recent_signals)} in last 100 bars)"
                else:
                    verdict = "NO SIGNALS in 300 bars — check strategy"

                print(
                    f"{symbol} {tf_str} {sid:<4}  {len(df):<6} "
                    f"{len(all_signals):<7} {len(recent_signals):<8} {verdict}"
                )
            except Exception as exc:
                print(f"{symbol} {tf_str} {sid:<4}  ERROR: {exc}")


if __name__ == "__main__":
    main()