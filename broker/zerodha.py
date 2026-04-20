import os
import logging
from kiteconnect import KiteConnect
from .base import BrokerBase, Order, Position

logger = logging.getLogger(__name__)


class ZerodhaBroker(BrokerBase):

    def __init__(self):
        self.api_key = os.getenv("KITE_API_KEY")
        self.api_secret = os.getenv("KITE_API_SECRET")
        self.access_token = os.getenv("KITE_ACCESS_TOKEN")
        self.kite = KiteConnect(api_key=self.api_key)
        self.kite.set_access_token(self.access_token)

    def get_live_price(self, symbol: str) -> float:
        data = self.kite.ltp(f"NSE:{symbol}")
        return data[f"NSE:{symbol}"]["last_price"]

    def place_limit_order(self, symbol: str, qty: int, price: float, transaction_type: str) -> Order:
        order_id = self.kite.place_order(
            variety=KiteConnect.VARIETY_REGULAR,
            exchange=KiteConnect.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=transaction_type,
            quantity=qty,
            product=KiteConnect.PRODUCT_CNC,
            order_type=KiteConnect.ORDER_TYPE_LIMIT,
            price=price,
        )
        logger.info(f"LIMIT order placed: {transaction_type} {qty} {symbol} @ ₹{price} | ID={order_id}")
        return Order(order_id=order_id, symbol=symbol, qty=qty, price=price,
                     transaction_type=transaction_type, status="OPEN")

    def place_sl_order(self, symbol: str, qty: int, trigger_price: float, transaction_type: str) -> Order:
        limit_price = round(trigger_price * 0.99, 1)  # 1% below trigger for guaranteed fill
        order_id = self.kite.place_order(
            variety=KiteConnect.VARIETY_REGULAR,
            exchange=KiteConnect.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=transaction_type,
            quantity=qty,
            product=KiteConnect.PRODUCT_CNC,
            order_type=KiteConnect.ORDER_TYPE_SL,
            price=limit_price,
            trigger_price=trigger_price,
        )
        logger.info(f"SL order placed: {symbol} trigger=₹{trigger_price} | ID={order_id}")
        return Order(order_id=order_id, symbol=symbol, qty=qty, price=limit_price,
                     transaction_type=transaction_type, status="TRIGGER_PENDING")

    def place_market_order(self, symbol: str, qty: int, transaction_type: str) -> Order:
        order_id = self.kite.place_order(
            variety=KiteConnect.VARIETY_REGULAR,
            exchange=KiteConnect.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=transaction_type,
            quantity=qty,
            product=KiteConnect.PRODUCT_CNC,
            order_type=KiteConnect.ORDER_TYPE_MARKET,
        )
        logger.info(f"MARKET order placed: {transaction_type} {qty} {symbol} | ID={order_id}")
        return Order(order_id=order_id, symbol=symbol, qty=qty, price=0,
                     transaction_type=transaction_type, status="OPEN")

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.kite.cancel_order(variety=KiteConnect.VARIETY_REGULAR, order_id=order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    def modify_sl_order(self, order_id: str, new_trigger_price: float) -> Order:
        new_limit = round(new_trigger_price * 0.99, 1)
        self.kite.modify_order(
            variety=KiteConnect.VARIETY_REGULAR,
            order_id=order_id,
            trigger_price=new_trigger_price,
            price=new_limit,
        )
        logger.info(f"SL order {order_id} modified → trigger=₹{new_trigger_price}")
        return Order(order_id=order_id, symbol="", qty=0, price=new_limit,
                     transaction_type="SELL", status="TRIGGER_PENDING")

    def get_order_status(self, order_id: str) -> Order:
        orders = self.kite.orders()
        for o in orders:
            if o["order_id"] == order_id:
                return Order(
                    order_id=o["order_id"],
                    symbol=o["tradingsymbol"],
                    qty=o["quantity"],
                    price=o["price"],
                    transaction_type=o["transaction_type"],
                    status=o["status"],
                )
        raise ValueError(f"Order {order_id} not found")

    def get_open_positions(self) -> list[Position]:
        data = self.kite.positions()
        positions = []
        for p in data.get("net", []):
            if p["quantity"] != 0:
                entry = p["average_price"]
                current = self.get_live_price(p["tradingsymbol"])
                pnl = (current - entry) * p["quantity"]
                pnl_pct = (current - entry) / entry if entry else 0
                positions.append(Position(
                    symbol=p["tradingsymbol"],
                    qty=p["quantity"],
                    entry_price=entry,
                    current_price=current,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                ))
        return positions

    def get_holdings(self) -> list:
        return self.kite.holdings()
