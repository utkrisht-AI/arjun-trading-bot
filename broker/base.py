from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    order_id: str
    symbol: str
    qty: int
    price: float
    transaction_type: str  # BUY or SELL
    status: str


@dataclass
class Position:
    symbol: str
    qty: int
    entry_price: float
    current_price: float
    pnl: float
    pnl_pct: float


class BrokerBase(ABC):

    @abstractmethod
    def get_live_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    def place_limit_order(self, symbol: str, qty: int, price: float, transaction_type: str) -> Order:
        pass

    @abstractmethod
    def place_sl_order(self, symbol: str, qty: int, trigger_price: float, transaction_type: str) -> Order:
        pass

    @abstractmethod
    def place_market_order(self, symbol: str, qty: int, transaction_type: str) -> Order:
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    def modify_sl_order(self, order_id: str, new_trigger_price: float) -> Order:
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Order:
        pass

    @abstractmethod
    def get_open_positions(self) -> list[Position]:
        pass

    @abstractmethod
    def get_holdings(self) -> list:
        pass
