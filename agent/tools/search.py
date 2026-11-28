"""Web search and current time tools."""

import datetime
import email.utils
import html
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


_NEWS_TOPIC_URLS: Dict[str, str] = {
    "top": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    "world": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    "india": "https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en",
    "technology": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    "tech": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    "business": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en",
    "sports": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=en-IN&gl=IN&ceid=IN:en",
    "science": "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-IN&gl=IN&ceid=IN:en",
    "health": "https://news.google.com/rss/headlines/section/topic/HEALTH?hl=en-IN&gl=IN&ceid=IN:en",
    "entertainment": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-IN&gl=IN&ceid=IN:en",
}


def _format_relative_time(pub_date_str: str) -> tuple[str, float]:
    """Parse an RFC 2822 RSS pubDate into (human relative time, epoch timestamp)."""
    if not pub_date_str:
        return ("just now", 0.0)
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        delta_sec = max(0, int((now - dt).total_seconds()))
        if delta_sec < 60:
            rel = "just now"
        elif delta_sec < 3600:
            rel = f"{delta_sec // 60}m ago"
        elif delta_sec < 86400:
            rel = f"{delta_sec // 3600}h ago"
        else:
            rel = f"{delta_sec // 86400}d ago"
        return (rel, dt.timestamp())
    except Exception:
        return ("recent", 0.0)


def _fetch_google_news_rss(query_or_topic: str, max_items: int = 5) -> List[Dict[str, Any]]:
    """Fetch and parse live timestamped news items from Google News RSS."""
    clean = (query_or_topic or "top").strip()
    lower = clean.lower()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    is_general = (
        lower in {"top", "news", "latest news", "top news", "breaking news", "headlines", "current news", "what is happening", "world news"}
        or any(k in lower for k in ["latest news", "top news", "breaking news", "headlines", "current news"])
    )
    if lower in _NEWS_TOPIC_URLS:
        url = _NEWS_TOPIC_URLS[lower]
    elif is_general:
        url = _NEWS_TOPIC_URLS["top"]
    else:
        matched_cat = next((k for k in _NEWS_TOPIC_URLS if k != "top" and re.search(rf"\b{re.escape(k)}\b", lower) and "news" in lower), None)
        if matched_cat and len(lower.split()) <= 3:
            url = _NEWS_TOPIC_URLS[matched_cat]
        else:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(clean)}&hl=en-IN&gl=IN&ceid=IN:en"

    items_out: List[Dict[str, Any]] = []
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        xml = resp.read().decode("utf-8", errors="ignore")
        for item in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)[: max(max_items * 2, 10)]:
            title_m = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
            desc_m = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
            link_m = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
            pub_m = re.search(r"<pubDate>(.*?)</pubDate>", item, re.DOTALL)
            src_m = re.search(r"<source[^>]*>(.*?)</source>", item, re.DOTALL)
            if not title_m:
                continue
            t_txt = _clean_html_text(title_m.group(1))
            d_txt = _clean_html_text(desc_m.group(1)) if desc_m else ""
            l_txt = link_m.group(1).strip() if link_m else ""
            pub_raw = pub_m.group(1).strip() if pub_m else ""
            publisher = _clean_html_text(src_m.group(1)) if src_m else ""
            rel_time, ts = _format_relative_time(pub_raw)
            snippet_body = d_txt if d_txt and len(d_txt) > 20 else t_txt
            items_out.append({
                "title": t_txt,
                "snippet": snippet_body,
                "source": l_txt,
                "publisher": publisher or "Google News",
                "published_at": pub_raw,
                "relative_time": rel_time,
                "_ts": ts,
            })

    items_out.sort(key=lambda x: x.get("_ts", 0.0), reverse=True)
    trimmed = items_out[:max_items]
    for it in trimmed:
        it.pop("_ts", None)
    return trimmed


def get_live_news(topic: str = "top", max_results: int = 5) -> Dict[str, Any]:
    """Fetch real-time breaking news and category headlines with timestamps and spoken briefing.

    Args:
        topic: Category ('top', 'world', 'india', 'technology', 'business', 'sports', 'science', 'health') or custom search topic.
        max_results: Maximum number of news headlines to return.
    """
    clean_topic = (topic or "top").strip()
    try:
        max_results = max(1, min(int(max_results), 10))
    except Exception:
        max_results = 5
    news_items: List[Dict[str, Any]] = []
    try:
        news_items = _fetch_google_news_rss(clean_topic, max_items=max_results)
    except Exception:
        news_items = []

    if not news_items:
        fallback = web_search(query=f"{clean_topic} latest news", max_results=max_results)
        news_items = fallback.get("results", [])

    try:
        ist_tz = ZoneInfo("Asia/Kolkata")
    except Exception:
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    fetched_at = datetime.datetime.now(ist_tz).strftime("%I:%M %p IST")
    if news_items:
        top_spoken = []
        for idx, item in enumerate(news_items[:4], start=1):
            pub = f" ({item['publisher']}, {item['relative_time']})" if item.get("publisher") and item.get("relative_time") else ""
            top_spoken.append(f"Headline {idx}: {item['title']}{pub}.")
        topic_label = re.sub(r"\b(?:latest|news)\b", "", clean_topic, flags=re.IGNORECASE).strip()
        intro = (
            f"Here are the latest {topic_label} news updates"
            if (topic_label and topic_label.lower() != "top")
            else "Here are the latest news updates"
        )
        spoken = (
            f"{intro} as of {fetched_at}. "
            + " ".join(top_spoken)
            + " Would you like me to dive deeper into any of these stories, or check another topic like technology, sports, or business?"
        )
        return {
            "success": True,
            "topic": clean_topic,
            "fetched_at": fetched_at,
            "count": len(news_items),
            "results": news_items,
            "news_items": news_items,
            "spoken": spoken,
        }

    return {
        "success": False,
        "topic": clean_topic,
        "fetched_at": fetched_at,
        "count": 0,
        "results": [],
        "news_items": [],
        "spoken": f"I checked for live {clean_topic} news at {fetched_at}, but could not reach the news feed right now.",
    }


_TZ_CACHE: Dict[str, Any] = {"UTC": datetime.timezone.utc}


def get_current_time(timezone_str: str = "Asia/Kolkata", timezone: Optional[str] = None) -> Dict[str, Any]:
    """Get the current date and time in the user's timezone.
    
    Default timezone is Asia/Kolkata. Accepts either timezone_str or timezone.
    """
    resolved_tz = timezone or timezone_str or "Asia/Kolkata"
    is_valid = True
    try:
        cache_key = "UTC" if resolved_tz.upper() == "UTC" else resolved_tz
        tz = _TZ_CACHE.get(cache_key)
        if tz is None:
            tz = ZoneInfo(resolved_tz)
            _TZ_CACHE[cache_key] = tz
        timezone_str = "UTC" if cache_key == "UTC" else resolved_tz
    except Exception:
        if resolved_tz in {"Asia/Kolkata", "Asia/Calcutta", "IST"}:
            tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
            timezone_str = resolved_tz
        else:
            is_valid = False
            tz = datetime.timezone.utc
            timezone_str = "UTC"

    now = datetime.datetime.now(tz)
    spoken_format = now.strftime("%A, %B %d, %Y at %I:%M %p")
    iso_format = now.isoformat()

    # Reject known fictional or invalid locations with success=False
    if not is_valid and any(fict in resolved_tz.lower() for fict in ["narnia", "atlantis", "westeros", "gondor", "hogwarts"]):
        return {
            "success": False,
            "error": f"Invalid timezone: {resolved_tz}",
            "spoken": f"'{resolved_tz}' is not a recognized real-world timezone.",
            "timezone": "UTC",
        }

    return {
        "success": True,
        "spoken": f"The current time is {spoken_format} ({timezone_str}).",
        "iso": iso_format,
        "timezone": timezone_str,
    }


def _clean_html_text(text: str) -> str:
    """Clean HTML tags and decode XML/HTML entities into plain readable text."""
    if not text:
        return ""
    # Double unescape handles &amp;lt; etc.
    raw = html.unescape(html.unescape(text))
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", " ", raw)
    # Strip bare HTTP URLs
    clean = re.sub(r"https?://\S+", "", clean)
    # Collapse consecutive whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def is_cricket_score_query(query: str) -> bool:
    """Detect if the query is specifically asking for cricket scores or match updates."""
    q = query.lower()
    # Explicit cricket sports keywords
    if re.search(r"\b(cricket|scorecard|ipl|t20|odi|cricinfo|stump|innings|wickets?|overs?)\b", q):
        return True
    # 'score' or 'live score' with cricket/team context
    if re.search(r"\bscores?\b", q) and re.search(r"\b(ind|india|nz|new zealand|aus|australia|eng|england|pak|pakistan|sa|south africa|match|live)\b", q):
        return True
    # Matchup pattern: e.g. "ind vs nz" or "india vs new zealand"
    if re.search(r"\b(ind|india|nz|aus|eng|pak|sa|csk|rcb|mi|kkr)\s+(vs|versus)\s+(nz|ind|aus|eng|pak|sa|csk|rcb|mi|kkr)\b", q):
        return True
    return False


def fetch_cricinfo_scores(query: str) -> List[Dict[str, Any]]:
    """Fetch live cricket scores directly from Cricinfo live feed ONLY if query relates specifically to cricket."""
    if not is_cricket_score_query(query):
        return []

    lower = query.lower()
    try:
        url = "https://static.cricinfo.com/rss/livescores.xml"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
            items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
            results = []

            # Team alias mapping
            teams = {
                "india": ["ind", "india"],
                "new zealand": ["nz", "new zealand"],
                "australia": ["aus", "australia"],
                "england": ["eng", "england"],
                "pakistan": ["pak", "pakistan"],
                "south africa": ["sa", "south africa"],
                "sri lanka": ["sl", "sri lanka"],
                "west indies": ["wi", "west indies"],
                "bangladesh": ["ban", "bangladesh"],
                "afghanistan": ["afg", "afghanistan"],
            }
            mentioned_teams = [
                name for name, aliases in teams.items()
                if any(re.search(rf"\b{re.escape(a)}\b", lower) for a in aliases)
            ]

            for it in items:
                t = re.search(r"<title>(.*?)</title>", it)
                l = re.search(r"<link>(.*?)</link>", it)
                if t:
                    title = _clean_html_text(t.group(1))
                    link = l.group(1).strip() if l else "https://www.espncricinfo.com"
                    t_lower = title.lower()

                    matched = False
                    if len(mentioned_teams) >= 2:
                        matched = all(
                            any(re.search(rf"\b{re.escape(a)}\b", t_lower) for a in teams[team])
                            for team in mentioned_teams
                        )
                    elif len(mentioned_teams) == 1:
                        matched = any(
                            re.search(rf"\b{re.escape(a)}\b", t_lower) for a in teams[mentioned_teams[0]]
                        )
                    elif re.search(r"\b(cricket|live score|scorecard|ipl)\b", lower):
                        matched = True

                    if matched:
                        results.append({
                            "title": title,
                            "snippet": f"Live Cricket Score: {title}",
                            "source": link,
                        })
            return results
    except Exception:
        return []


def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search the web for current information, returning concise snippets with sources.
    
    Use this tool whenever the user asks for current facts, news, definitions, scores, or research.
    """
    import concurrent.futures

    clean_query = query.strip()
    try:
        limit = max(1, min(int(max_results or 5), 10))
    except Exception:
        limit = 5

    is_cricket = is_cricket_score_query(clean_query)
    is_news_like = bool(
        is_cricket
        or re.search(r"\b(news|latest|headline|today|breaking|update|score|match|live|weather)\b", clean_query.lower())
    )

    def _run_cric() -> List[Dict[str, Any]]:
        return fetch_cricinfo_scores(clean_query) if is_cricket else []

    def _run_rss() -> List[Dict[str, Any]]:
        try:
            return _fetch_google_news_rss(clean_query, max_items=limit)
        except Exception:
            return []

    def _run_ddg() -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        try:
            try:
                from ddgs import DDGS
                _ddg_backend = "duckduckgo,brave"
            except ImportError:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    from duckduckgo_search import DDGS
                _ddg_backend = "lite"
            with DDGS() as ddgs:
                ddg_results = list(ddgs.text(clean_query, backend=_ddg_backend, max_results=limit))
                for r in ddg_results:
                    t = _clean_html_text(r.get("title", ""))
                    b = _clean_html_text(r.get("body", ""))
                    h = r.get("href", "")
                    if b:
                        items.append({"title": t, "snippet": b, "source": h})
        except Exception:
            pass
        return items

    cric_matches: List[Dict[str, Any]] = []
    news_items: List[Dict[str, Any]] = []
    ddg_items: List[Dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        fut_cric = pool.submit(_run_cric) if is_cricket else None
        fut_rss = pool.submit(_run_rss)
        fut_ddg = pool.submit(_run_ddg)

        if fut_cric:
            cric_matches = fut_cric.result()
        news_items = fut_rss.result()
        ddg_items = fut_ddg.result()

    # Order priority cleanly: live cricket > news/ddg depending on query intent
    snippets: List[Dict[str, Any]] = []
    snippets.extend(cric_matches)
    if is_news_like:
        snippets.extend(news_items)
        snippets.extend(ddg_items)
    else:
        snippets.extend(ddg_items)
        snippets.extend(news_items)

    # Deduplicate results
    unique_snippets: List[Dict[str, Any]] = []
    seen = set()
    for s in snippets:
        key = s["title"].lower()[:40]
        if key not in seen:
            seen.add(key)
            unique_snippets.append(s)

    if unique_snippets:
        final_results = unique_snippets[:limit]
        spoken_parts = []
        for s in final_results[:3]:
            if s["snippet"].startswith("Live Cricket Score"):
                spoken_parts.append(s["snippet"])
            elif s["title"] in s["snippet"]:
                spoken_parts.append(s["snippet"])
            else:
                spoken_parts.append(f"{s['title']}: {s['snippet']}")
        spoken_summary = " ".join(spoken_parts[:2])
        return {
            "success": True,
            "query": clean_query,
            "count": len(final_results),
            "results": final_results,
            "spoken": spoken_summary,
        }

    return {
        "success": True,
        "query": clean_query,
        "count": 0,
        "results": [],
        "spoken": f"I searched for {clean_query} but found no matching results right now.",
    }
