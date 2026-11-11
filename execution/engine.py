"""MetaTrader 5 Execution Engine — places market orders with SL/TP."""
import logging
from core.types import Signal
from core.enums import SignalDirection
from market_data.mt5_gateway import MT5Gateway

logger = logging.getLogger("godswill.execution.engine")


class ExecutionEngine:
    def __init__(self, gateway: MT5Gateway):
        self.gateway = gateway

    def execute_signal(self, signal: Signal, volume: float) -> bool:
        if volume <= 0:
            return False

        mt5 = self.gateway._mt5
        if not mt5:
            logger.error("[EXEC] MT5 not connected")
            return False

        symbol = signal.symbol
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"[EXEC] Symbol {symbol} not found.")
            return False

        # 1. Determine Order Type and Current Market Price
        order_type = mt5.ORDER_TYPE_BUY if signal.direction == SignalDirection.LONG else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"[EXEC] Failed to get tick data for {symbol}")
            return False
            
        current_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

        # 2. Recalculate SL and TP based on ACTUAL market entry
        # (Prevents the R:R distortion seen in your previous trade)
        original_risk = abs(signal.entry_price - signal.stop_loss)
        original_reward = abs(signal.take_profit - signal.entry_price)
        rr_ratio = original_reward / original_risk if original_risk > 0 else 2.0

        sl = signal.stop_loss
        tp = signal.take_profit

        # If market price moved past the SL, the trade is invalid.
        if order_type == mt5.ORDER_TYPE_BUY and current_price <= sl:
            logger.warning(f"[EXEC] Rejected: Market price {current_price} is below/at SL {sl} for LONG")
            return False
        if order_type == mt5.ORDER_TYPE_SELL and current_price >= sl:
            logger.warning(f"[EXEC] Rejected: Market price {current_price} is above/at SL {sl} for SHORT")
            return False

        # Recalculate TP to maintain the exact R:R based on actual entry
        if order_type == mt5.ORDER_TYPE_BUY:
            tp = current_price + (abs(current_price - sl) * rr_ratio)
        else:
            tp = current_price - (abs(sl - current_price) * rr_ratio)

        # 3. Enforce Broker Minimum Stop Level (Fixes Error 10016)
        stops_level = getattr(symbol_info, 'trade_stops_level', 0)
        point = symbol_info.point
        min_dist = (stops_level + 2) * point  # +2 points buffer to prevent rejection due to spread

        if order_type == mt5.ORDER_TYPE_BUY:
            if (current_price - sl) < min_dist:
                sl = current_price - min_dist
            if (tp - current_price) < min_dist:
                tp = current_price + min_dist
        else:
            if (sl - current_price) < min_dist:
                sl = current_price + min_dist
            if (current_price - tp) < min_dist:
                tp = current_price - min_dist

        # 4. Normalize Prices (Fixes Error 10016)
        digits = symbol_info.digits
        price = round(current_price, digits)
        sl = round(sl, digits)
        tp = round(tp, digits)

        # 5. Determine filling mode
        filling_type = mt5.ORDER_FILLING_IOC
        if hasattr(symbol_info, 'filling_mode'):
            # If FOK is supported and IOC isn't, switch.
            if (symbol_info.filling_mode & 1) == 1:
                filling_type = mt5.ORDER_FILLING_FOK

        # 6. Build Request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,        # Allow 20 points of slippage
            "magic": 999999,        # Magic number to identify our trades
            "comment": signal.strategy_id,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }

        # 7. Send Order
        logger.info(f"[EXEC] Sending order: {symbol} {signal.direction.value} {volume} lots | Entry: {price} | SL: {sl} | TP: {tp} | R:R: {rr_ratio:.2f}")
        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"[EXEC] Order failed: [{result.retcode}] {result.comment}")
            return False

        logger.info(f"[EXEC] ✅ Order {result.order} successfully executed on {symbol}")
        return True