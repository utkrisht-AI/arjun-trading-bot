import logging
import feedparser
import anthropic
import os

logger = logging.getLogger(__name__)

RSS_SOURCES = [
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://economictimes.indiatimes.com/markets/rss.cms",
    "https://www.business-standard.com/rss/markets-106.rss",
]


def fetch_headlines() -> list[str]:
    headlines = []
    for url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                headlines.append(entry.title)
        except Exception as e:
            logger.warning(f"RSS fetch failed for {url}: {e}")
    logger.info(f"Fetched {len(headlines)} headlines")
    return headlines


def classify_sentiment_batch(headlines: list[str], symbols: list[str]) -> dict[str, str]:
    if not headlines or not symbols:
        return {s: "neutral" for s in symbols}

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""You are a financial news analyst for Indian equity markets.

Headlines:
{chr(10).join(f'- {h}' for h in headlines[:40])}

Stocks to analyze: {', '.join(symbols)}

For each stock, classify the overall sentiment from the headlines as:
- "positive": good news for the stock
- "negative": bad news for the stock
- "neutral": no relevant news or mixed signals

Respond ONLY as a JSON object like: {{"RELIANCE": "positive", "TCS": "neutral"}}
Include all stocks in the response."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = response.content[0].text.strip()
        result = json.loads(text)
        logger.info(f"Sentiment classified for {len(result)} stocks")
        return result
    except Exception as e:
        logger.error(f"Sentiment classification failed: {e}")
        return {s: "neutral" for s in symbols}


def run_sentiment_scan(candidates: list[dict]) -> dict[str, str]:
    symbols = [c["symbol"] for c in candidates]
    headlines = fetch_headlines()
    sentiments = classify_sentiment_batch(headlines, symbols)
    for symbol, sentiment in sentiments.items():
        logger.info(f"Sentiment {symbol}: {sentiment}")
    return sentiments
