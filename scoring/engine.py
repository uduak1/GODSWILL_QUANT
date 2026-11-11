from core.types import Signal
import logging

logger = logging.getLogger("godswill.scoring")

class SignalScorer:
    """
    Evaluates a signal's quality on a scale of 0-100.
    Weights must sum to 1.0.
    """
    WEIGHTS = {
        "market_structure": 0.20,    # Is HTF structure aligned?
        "liquidity_context": 0.15,   # Was there a sweep or imbalance?
        "entry_location": 0.20,      # Is entry at premium/discount or FVG?
        "displacement": 0.10,        # How strong was the breakout candle?
        "confirmation": 0.15,        # Did we get a clean CHOCH/BOS?
        "zone_freshness": 0.10,      # Has the OB/FVG been tested before?
        "risk_reward": 0.10,         # Is the RR acceptable (>1:2)?
    }

    @classmethod
    def score(cls, signal: Signal, context: dict[str, float]) -> float:
        """
        context values must be between 0.0 (fail) and 1.0 (perfect).
        Example context:
        {"market_structure": 1.0, "liquidity_context": 0.5, ...}
        """
        total_score = 0.0
        for feature, weight in cls.WEIGHTS.items():
            # Default to 0.0 if the strategy didn't provide a feature score
            feature_score = context.get(feature, 0.0)
            total_score += (feature_score * weight * 100)

        # Apply a hard penalty if Risk:Reward is below 1.5
        if signal.reward_risk < 1.5:
            total_score -= 20

        final_score = max(0.0, min(100.0, total_score))
        logger.info(f"Scored {signal.strategy_id} signal: {final_score:.1f}/100")
        return final_score