import logging
import time
import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.nseindia.com/",
}


class NSEClient:
    BASE = "https://www.nseindia.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self._ready = False
        self._init_session()

    def _init_session(self):
        try:
            self.session.get(self.BASE, timeout=15)
            time.sleep(2)
            self.session.get(f"{self.BASE}/market-data/live-equity-market", timeout=15)
            time.sleep(1)
            self._ready = True
            logger.info("NSE session initialized")
        except Exception as e:
            logger.warning(f"NSE session init failed: {e}")

    def _get(self, path: str, params: dict = None) -> dict | None:
        if not self._ready:
            return None
        try:
            url = f"{self.BASE}/api/{path}"
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"NSE API {path} failed: {e}")
            return None

    def get_asm_symbols(self) -> set[str]:
        data = self._get("reportASM")
        if not data:
            return set()
        try:
            return {row["symbol"].upper() for row in data.get("data", [])}
        except Exception:
            return set()

    def get_gsm_symbols(self) -> set[str]:
        data = self._get("reportGSM")
        if not data:
            return set()
        try:
            return {row["symbol"].upper() for row in data.get("data", [])}
        except Exception:
            return set()

    def get_delivery_pct(self, symbol: str) -> float | None:
        data = self._get("quote-equity", params={"symbol": symbol})
        if not data:
            return None
        try:
            return float(data["securityInfo"]["deliveryToTradedQuantity"])
        except (KeyError, TypeError, ValueError):
            return None

    def get_nifty_quote(self) -> float | None:
        data = self._get("quote-equity", params={"symbol": "NIFTY 50", "type": "index"})
        if not data:
            return None
        try:
            return float(data["priceInfo"]["lastPrice"])
        except (KeyError, TypeError, ValueError):
            return None


_client: NSEClient | None = None


def get_nse_client() -> NSEClient:
    global _client
    if _client is None:
        _client = NSEClient()
    return _client
