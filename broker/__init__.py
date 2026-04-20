import os
from .base import BrokerBase, Order, Position


def get_broker() -> BrokerBase:
    broker = os.getenv("BROKER", "zerodha").lower()
    if broker == "zerodha":
        from .zerodha import ZerodhaBroker
        return ZerodhaBroker()
    elif broker == "upstox":
        from .upstox import UpstoxBroker
        return UpstoxBroker()
    else:
        raise ValueError(f"Unsupported broker: {broker}")
