import logging
from configuration.settings import RiskSettings
from core.types import Signal

logger = logging.getLogger("godswill.risk")


class RiskManager:
    """Position-sizing risk manager with hard exposure caps.

    Three independent caps prevent runaway lot sizes:
      1. Broker volume_max
      2. Notional exposure cap (default: 5x account balance per trade)
      3. Risk-per-trade cap (default: 2% of current account)
    """

    # Hard limits applied to every trade regardless of config
    MAX_NOTIONAL_MULTIPLE = 5.0    # 5x account per single position
    MAX_RISK_PCT_PER_TRADE = 2.0   # 2% of account cap (in % terms)

    def __init__(self, config: RiskSettings):
        self.config = config
        self.emergency_stop = False

    def calculate_volume(
        self,
        account_balance: float,
        signal: Signal,
        symbol_specs: dict,
    ) -> float:
        if self.emergency_stop:
            return 0.0
        if account_balance <= 0:
            return 0.0

        # --- 1. Risk amount (dollar) ---
        fixed_risk = getattr(self.config, "fixed_risk_amount", None)
        if fixed_risk is not None and fixed_risk > 0:
            requested_risk = fixed_risk
        else:
            requested_risk = account_balance * (self.config.risk_per_trade_pct / 100.0)

        # Hard cap: never risk more than MAX_RISK_PCT_PER_TRADE of current balance
        absolute_max_risk = account_balance * (self.MAX_RISK_PCT_PER_TRADE / 100.0)
        risk_amount = min(requested_risk, absolute_max_risk)

        # --- 2. Stop distance ---
        stop_distance = abs(signal.entry_price - signal.stop_loss)
        if stop_distance == 0:
            return 0.0

        # --- 3. Value per 1.0 lot at that stop distance ---
        tick_size = symbol_specs.get("tick_size", 0.0001)
        tick_value = symbol_specs.get("tick_value", 1.0)
        risk_per_lot = (stop_distance / tick_size) * tick_value
        if risk_per_lot <= 0:
            return 0.0

        # --- 4. Raw volume from risk ---
        raw_volume = risk_amount / risk_per_lot

        # --- 5. Round to broker step ---
        volume_step = symbol_specs.get("volume_step", 0.01)
        volume = round(raw_volume / volume_step) * volume_step

        # --- 6. Broker min/max ---
        volume_min = symbol_specs.get("volume_min", 0.01)
        volume_max = symbol_specs.get("volume_max", 100.0)

        # --- 7. Notional exposure cap ---
        # Notional = entry_price × contract_size × volume
        contract_size = symbol_specs.get("contract_size", 100_000)
        notional_per_lot = signal.entry_price * contract_size
        if notional_per_lot > 0:
            max_by_notional = (
                account_balance * self.MAX_NOTIONAL_MULTIPLE
            ) / notional_per_lot
        else:
            max_by_notional = volume_max

        # --- 8. Combine all caps ---
        final_volume = min(volume, volume_max, max_by_notional)
        final_volume = max(volume_min, final_volume)

        # --- 9. Reject if even the minimum volume violates risk sanity ---
        # The minimum lot must not risk more than 2x the intended risk
        if final_volume * risk_per_lot > (risk_amount * 2.0):
            logger.warning(
                f"Trade rejected: {final_volume} lots risk "
                f"${final_volume * risk_per_lot:.2f} "
                f"vs allowed ${risk_amount:.2f}"
            )
            return 0.0

        return round(final_volume, 2)

    def approve_trade(
        self,
        signal: Signal,
        current_open_positions: int,
        daily_pnl_pct: float,
    ) -> tuple[bool, str]:
        if self.emergency_stop:
            return False, "Emergency stop is active."

        if current_open_positions >= self.config.max_open_positions:
            return False, f"Max open positions ({self.config.max_open_positions})."

        if daily_pnl_pct <= -self.config.max_daily_loss_pct:
            return False, f"Max daily loss ({self.config.max_daily_loss_pct}%)."

        if signal.reward_risk < self.config.min_reward_risk:
            return False, (
                f"R:R {signal.reward_risk:.2f} < {self.config.min_reward_risk}"
            )

        return True, "Approved"