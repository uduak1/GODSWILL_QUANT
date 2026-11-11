from configuration.settings import Settings, AppSettings, RiskSettings


def test_defaults_are_valid():
    s = Settings()
    assert s.app.environment == "demo"
    assert s.risk.risk_per_trade_pct == 0.5
    assert s.risk.min_reward_risk == 1.5


def test_risk_bounds_reject_bad_values():
    import pytest
    with pytest.raises(Exception):
        RiskSettings(risk_per_trade_pct=10)   # > 5


def test_environment_enum_strict():
    import pytest
    with pytest.raises(Exception):
        AppSettings(environment="production")