from __future__ import annotations

import re
from datetime import datetime

import yfinance as yf

from stock_autopilot.collectors.cache import cache_get_json, cache_set_json
from stock_autopilot.models.schemas import NewsItem

_NEWS_TTL = 1800

POSITIVE = {
    "beat", "surge", "growth", "partnership", "collaboration", "deal", "acquisition",
    "upgrade", "record", "profit", "expansion", "launch", "approval", "contract",
    "dividend", "buyback", "innovation", "breakthrough",
}
NEGATIVE = {
    "miss", "decline", "lawsuit", "investigation", "downgrade", "cut", "layoff",
    "recall", "fraud", "bankruptcy", "warning", "loss", "delay", "fine", "probe",
    "sanction", "halt", "crash",
}
THEME_PATTERNS = {
    "partnership": re.compile(r"partner|collaborat|joint venture|alliance|deal with", re.I),
    "m_and_a": re.compile(r"acqui|merger|buyout|takeover", re.I),
    "earnings": re.compile(r"earnings|quarter|revenue|profit|guidance", re.I),
    "regulatory": re.compile(r"SEC|regulator|antitrust|FDA|approval", re.I),
    "macro": re.compile(r"fed|inflation|rate|tariff|geopolit", re.I),
}


def _sentiment(title: str) -> float:
    words = set(re.findall(r"[a-z]+", title.lower()))
    pos = len(words & POSITIVE)
    neg = len(words & NEGATIVE)
    if pos + neg == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(pos + neg, 1)))


def _themes(title: str) -> list[str]:
    found = []
    for name, pattern in THEME_PATTERNS.items():
        if pattern.search(title):
            found.append(name)
    return found


def fetch_news_for_symbol(symbol: str, limit: int = 8) -> list[NewsItem]:
    cache_key = f"news:{symbol}:{limit}"
    hit = cache_get_json(cache_key)
    if isinstance(hit, list):
        try:
            return [NewsItem(**x) for x in hit]
        except Exception:
            pass

    items: list[NewsItem] = []
    try:
        raw = yf.Ticker(symbol).news or []
        for entry in raw[:limit]:
            content = entry.get("content") or entry
            title = content.get("title") or entry.get("title") or ""
            if not title:
                continue
            pub = content.get("pubDate") or entry.get("providerPublishTime") or ""
            if isinstance(pub, (int, float)):
                pub = datetime.utcfromtimestamp(pub).isoformat()
            link = ""
            if content.get("canonicalUrl"):
                link = content["canonicalUrl"].get("url", "")
            elif content.get("clickThroughUrl"):
                link = content["clickThroughUrl"].get("url", "")
            publisher = (content.get("provider") or {}).get("displayName") or entry.get("publisher", "Unknown")
            items.append(
                NewsItem(
                    symbol=symbol,
                    title=title,
                    publisher=publisher,
                    link=link,
                    published=str(pub),
                    sentiment=_sentiment(title),
                    themes=_themes(title),
                )
            )
    except Exception:
        pass
    if items:
        cache_set_json(cache_key, [i.model_dump() for i in items], _NEWS_TTL)
    return items


def aggregate_news_sentiment(news: list[NewsItem]) -> tuple[float, list[str], list[str]]:
    if not news:
        return 0.0, [], []
    avg = sum(n.sentiment for n in news) / len(news)
    highlights = [n.title for n in sorted(news, key=lambda x: abs(x.sentiment), reverse=True)[:3]]
    themes: list[str] = []
    for n in news:
        themes.extend(n.themes)
    unique_themes = sorted(set(themes))
    return avg, highlights, unique_themes
