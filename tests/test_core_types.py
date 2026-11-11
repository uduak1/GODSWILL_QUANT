from datetime import datetime, timezone
from core.enums import SignalDirection, Timeframe
from core.types import Candle, Signal


def test_candle_immutable():
    c = Candle(datetime.now(timezone.utc), 1.0, 2.0, 0.5, 1.5)
    try:
        c.open = 9.9  # type: ignore[misc]
        assert False, "should have raised"
    except AttributeError:
        pass


def test_reward_risk_calculation():
    s = Signal(
        strategy_id="s01", symbol="XAUUSD", timeframe=Timeframe.M15,
        direction=SignalDirection.LONG,
        entry_price=2000.0, stop_loss=1990.0, take_profit=2030.0,
        created_at=datetime.now(timezone.utc),
    )
    assert s.reward_risk == 3.0


def test_reward_risk_zero_stop():
    s = Signal(
        strategy_id="s01", symbol="XAUUSD", timeframe=Timeframe.M15,
        direction=SignalDirection.LONG,
        entry_price=2000.0, stop_loss=2000.0, take_profit=2030.0,
        created_at=datetime.now(timezone.utc),
    )
    assert s.reward_risk == 0.0