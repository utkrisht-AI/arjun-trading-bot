import os
import logging
import upstox_client
from .base import BrokerBase, Order, Position

logger = logging.getLogger(__name__)


class UpstoxBroker(BrokerBase):

    def __init__(self):
        configuration = upstox_client.Configuration()
        configuration.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
        self.api_client = upstox_client.ApiClient(configuration)
        self.market_api = upstox_client.MarketQuoteApi(self.api_client)
        self.order_api = upstox_client.OrderApi(self.api_client)
        self.portfolio_api = upstox_client.PortfolioApi(self.api_client)

    def _instrument_key(self, symbol: str) -> str:
        return f"NSE_EQ|{symbol}"

    def get_live_price(self, symbol: str) -> float:
        resp = self.market_api.get_full_market_quote([self._instrument_key(symbol)], "2.0")
        data = resp.data[self._instrument_key(symbol)]
        return data.last_price

    def place_limit_order(self, symbol: str, qty: int, price: float, transaction_type: str) -> Order:
        body = upstox_client.PlaceOrderRequest(
            quantity=qty,
            product="D",  # Delivery
            validity="DAY",
            price=price,
            instrument_token=self._instrument_key(symbol),
            order_type="LIMIT",
            transaction_type=transaction_type,
            disclosed_quantity=0,
            trigger_price=0,
            is_amo=False,
        )
        resp = self.order_api.place_order(body, "2.0")
        order_id = resp.data.order_id
        logger.info(f"LIMIT order placed: {transaction_type} {qty} {symbol} @ ₹{price} | ID={order_id}")
        return Order(order_id=order_id, symbol=symbol, qty=qty, price=price,
                     transaction_type=transaction_type, status="OPEN")

    def place_sl_order(self, symbol: str, qty: int, trigger_price: float, transaction_type: str) -> Order:
        limit_price = round(trigger_price * 0.99, 1)
        body = upstox_client.PlaceOrderRequest(
            quantity=qty,
            product="D",
            validity="DAY",
            price=limit_price,
            instrument_token=self._instrument_key(symbol),
            order_type="SL",
            transaction_type=transaction_type,
            disclosed_quantity=0,
            trigger_price=trigger_price,
            is_amo=False,
        )
        resp = self.order_api.place_order(body, "2.0")
        order_id = resp.data.order_id
        logger.info(f"SL order placed: {symbol} trigger=₹{trigger_price} | ID={order_id}")
        return Order(order_id=order_id, symbol=symbol, qty=qty, price=limit_price,
                     transaction_type=transaction_type, status="TRIGGER_PENDING")

    def place_market_order(self, symbol: str, qty: int, transaction_type: str) -> Order:
        body = upstox_client.PlaceOrderRequest(
            quantity=qty,
            product="D",
            validity="DAY",
            price=0,
            instrument_token=self._instrument_key(symbol),
            order_type="MARKET",
            transaction_type=transaction_type,
            disclosed_quantity=0,
            trigger_price=0,
            is_amo=False,
        )
        resp = self.order_api.place_order(body, "2.0")
        order_id = resp.data.order_id
        logger.info(f"MARKET order placed: {transaction_type} {qty} {symbol} | ID={order_id}")
        return Order(order_id=order_id, symbol=symbol, qty=qty, price=0,
                     transaction_type=transaction_type, status="OPEN")

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.order_api.cancel_order(order_id, "2.0")
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    def modify_sl_order(self, order_id: str, new_trigger_price: float) -> Order:
        new_limit = round(new_trigger_price * 0.99, 1)
        body = upstox_client.ModifyOrderRequest(
            quantity=0,
            validity="DAY",
            price=new_limit,
            order_type="SL",
            trigger_price=new_trigger_price,
            disclosed_quantity=0,
        )
        self.order_api.modify_order(body, order_id, "2.0")
        logger.info(f"SL order {order_id} modified → trigger=₹{new_trigger_price}")
        return Order(order_id=order_id, symbol="", qty=0, price=new_limit,
                     transaction_type="SELL", status="TRIGGER_PENDING")

    def get_order_status(self, order_id: str) -> Order:
        resp = self.order_api.get_order_details(order_id, "2.0")
        o = resp.data
        return Order(order_id=o.order_id, symbol=o.tradingsymbol, qty=o.quantity,
                     price=o.price, transaction_type=o.transaction_type, status=o.status)

    def get_open_positions(self) -> list[Position]:
        resp = self.portfolio_api.get_positions("2.0")
        positions = []
        for p in (resp.data or []):
            if p.quantity != 0:
                entry = p.average_price
                current = self.get_live_price(p.tradingsymbol)
                pnl = (current - entry) * p.quantity
                pnl_pct = (current - entry) / entry if entry else 0
                positions.append(Position(
                    symbol=p.tradingsymbol,
                    qty=p.quantity,
                    entry_price=entry,
                    current_price=current,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                ))
        return positions

    def get_holdings(self) -> list:
        resp = self.portfolio_api.get_holdings("2.0")
        return resp.data or []
