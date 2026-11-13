import logging
from configuration.settings import RiskSettings
from core.types import Signal

logger = logging.getLogger("godswill.risk")


class RiskManager:
    """Position-sizing risk manager with hard exposure caps."""

    MAX_NOTIONAL_MULTIPLE = 5.0    
    MAX_RISK_PCT_PER_TRADE = 2.0   

    def __init__(self, config: RiskSettings):
        self.config = config
        self.emergency_stop = False

    def calculate_volume(
        self,
        account_balance: float,
        signal: Signal,
        symbol_specs: dict,
        tier_multiplier: float = 1.0, 
    ) -> float:
        if self.emergency_stop:
            return 0.0
        if account_balance <= 0:
            return 0.0

        volume_min = symbol_specs.get("volume_min", 0.01)

        # --- PROBATION BYPASS ---
        # If this is a probation strategy (tier risk < 1.0), 
        # just return the broker minimum so it can trade and be observed.
        if tier_multiplier < 1.0:
            return volume_min

        # --- NORMAL WINNER MATH ---
        fixed_risk = getattr(self.config, "fixed_risk_amount", None)
        if fixed_risk is not None and fixed_risk > 0:
            requested_risk = fixed_risk * tier_multiplier
        else:
            requested_risk = account_balance * (self.config.risk_per_trade_pct / 100.0) * tier_multiplier

        absolute_max_risk = account_balance * (self.MAX_RISK_PCT_PER_TRADE / 100.0)
        risk_amount = min(requested_risk, absolute_max_risk)

        stop_distance = abs(signal.entry_price - signal.stop_loss)
        if stop_distance == 0:
            return 0.0

        tick_size = symbol_specs.get("tick_size", 0.0001)
        tick_value = symbol_specs.get("tick_value", 1.0)
        risk_per_lot = (stop_distance / tick_size) * tick_value
        if risk_per_lot <= 0:
            return 0.0

        raw_volume = risk_amount / risk_per_lot

        volume_step = symbol_specs.get("volume_step", 0.01)
        volume = round(raw_volume / volume_step) * volume_step

        volume_max = symbol_specs.get("volume_max", 100.0)

        contract_size = symbol_specs.get("contract_size", 100_000)
        notional_per_lot = signal.entry_price * contract_size
        if notional_per_lot > 0:
            max_by_notional = (account_balance * self.MAX_NOTIONAL_MULTIPLE) / notional_per_lot
        else:
            max_by_notional = volume_max

        final_volume = min(volume, volume_max, max_by_notional)
        if final_volume < volume_min:
            final_volume = volume_min

        # Standard safety check for normal trades
        if final_volume * risk_per_lot > (risk_amount * 2.0):
            logger.warning(
                f"Trade rejected: {final_volume} lots risk "
                f"${final_volume * risk_per_lot:.2f} "
                f"vs allowed ${risk_amount:.2f}"
            )
            return 0.0

        return round(final_volume, 2)

    def approve_trade(self, signal, current_open_positions, daily_pnl_pct):
        if self.emergency_stop:
            return False, "Emergency stop is active."
        if current_open_positions >= self.config.max_open_positions:
            return False, f"Max open positions ({self.config.max_open_positions})."
        if daily_pnl_pct <= -self.config.max_daily_loss_pct:
            return False, f"Max daily loss ({self.config.max_daily_loss_pct}%)."
        if signal.reward_risk < self.config.min_reward_risk:
            return False, f"R:R {signal.reward_risk:.2f} < {self.config.min_reward_risk}"
        return True, "Approved"