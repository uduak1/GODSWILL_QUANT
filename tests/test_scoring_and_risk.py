import pytest
from datetime import datetime, timezone
from core.types import Signal
from core.enums import SignalDirection, Timeframe
from configuration.settings import RiskSettings
from scoring.engine import SignalScorer
from risk_management.engine import RiskManager

@pytest.fixture
def sample_signal():
    return Signal(
        strategy_id="S01", symbol="XAUUSD", timeframe=Timeframe.H1,
        direction=SignalDirection.LONG, entry_price=2000.0,
        stop_loss=1990.0, take_profit=2030.0,
        created_at=datetime.now(timezone.utc)
    )

@pytest.fixture
def gold_specs():
    # IC Markets XAUUSD specs
    return {
        "contract_size": 100.0,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "volume_step": 0.01,
        "volume_min": 0.01,
        "volume_max": 100.0
    }

def test_signal_scoring(sample_signal):
    # Provide perfect context scores
    context = {k: 1.0 for k in SignalScorer.WEIGHTS.keys()}
    score = SignalScorer.score(sample_signal, context)
    assert score == 100.0
    
    # Provide zero context scores, but good RR (3.0)
    score_zero = SignalScorer.score(sample_signal, {})
    assert score_zero == 0.0

def test_risk_position_sizing(sample_signal, gold_specs):
    config = RiskSettings(risk_per_trade_pct=1.0) # Risk 1%
    rm = RiskManager(config)
    
    # Balance = $10,000. Risk = $100.
    # Stop distance = $10.00 (2000 - 1990).
    # Value of $10.00 move on 1 lot of Gold = (10.0 / 0.01) * 1.0 = $1000.
    # We want to risk $100, so volume = 100 / 1000 = 0.10 lots.
    
    volume = rm.calculate_volume(10000.0, sample_signal, gold_specs)
    assert volume == 0.10

def test_risk_rejection_min_volume(sample_signal, gold_specs):
    # If balance is tiny, min volume might risk too much
    config = RiskSettings(risk_per_trade_pct=1.0)
    rm = RiskManager(config)
    
    # Balance = $100. Risk = $1.
    # Min volume 0.01 risks $10. This is > 1.5x $1, so it should reject (return 0.0)
    volume = rm.calculate_volume(100.0, sample_signal, gold_specs)
    assert volume == 0.0

def test_risk_trade_approval(sample_signal):
    config = RiskSettings(min_reward_risk=1.5)
    rm = RiskManager(config)
    
    # Signal RR is 3.0 (30 / 10) -> Passes
    approved, reason = rm.approve_trade(sample_signal, current_open_positions=2, daily_pnl_pct=0.0)
    assert approved is True
    
    # Test max positions
    approved, reason = rm.approve_trade(sample_signal, current_open_positions=5, daily_pnl_pct=0.0)
    assert approved is False
    assert "Max open positions" in reason
    
    # Test daily loss limit
    approved, reason = rm.approve_trade(sample_signal, current_open_positions=2, daily_pnl_pct=-2.5)
    assert approved is False
    assert "Max daily loss" in reason