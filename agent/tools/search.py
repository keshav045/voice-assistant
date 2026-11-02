"""Web search and current time tools."""

import datetime
import html
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List
from zoneinfo import ZoneInfo


def get_current_time(timezone_str: str = "Asia/Kolkata") -> Dict[str, Any]:
    """Get the current date and time in the user's timezone.
    
    Default timezone is Asia/Kolkata.
    """
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        tz = datetime.timezone.utc
        timezone_str = "UTC"

    now = datetime.datetime.now(tz)
    spoken_format = now.strftime("%A, %B %d, %Y at %I:%M %p")
    iso_format = now.isoformat()

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
    clean_query = query.strip()
    snippets: List[Dict[str, Any]] = []

    # 1. Check live cricket scores ONLY if explicitly asked for cricket/match scores
    if is_cricket_score_query(clean_query):
        cric_matches = fetch_cricinfo_scores(clean_query)
        if cric_matches:
            snippets.extend(cric_matches)

    # 2. Query Google News RSS (real-time live news, headlines, search)
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        is_general_news = any(k in clean_query.lower() for k in ["latest news", "top news", "breaking news", "headlines", "current news"]) or clean_query.lower() in ["news", "what is happening", "world news"]
        if is_general_news:
            url = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
        else:
            encoded = urllib.parse.quote(clean_query)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
            for item in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)[:5]:
                title_m = re.search(r"<title>(.*?)</title>", item)
                desc_m = re.search(r"<description>(.*?)</description>", item)
                link_m = re.search(r"<link>(.*?)</link>", item)
                if title_m:
                    t_txt = _clean_html_text(title_m.group(1))
                    d_txt = _clean_html_text(desc_m.group(1)) if desc_m else ""
                    l_txt = link_m.group(1).strip() if link_m else ""
                    # Use substantive description if available, else headline
                    snippet_body = d_txt if d_txt and len(d_txt) > 20 else t_txt
                    snippets.append({"title": t_txt, "snippet": snippet_body, "source": l_txt})
    except Exception:
        pass

    # 3. DuckDuckGo Search (Lite backend)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            ddg_results = list(ddgs.text(clean_query, backend="lite", max_results=3))
            for r in ddg_results:
                t = _clean_html_text(r.get("title", ""))
                b = _clean_html_text(r.get("body", ""))
                h = r.get("href", "")
                if b and not any(s["title"] == t for s in snippets):
                    snippets.append({"title": t, "snippet": b, "source": h})
    except Exception:
        pass

    # Deduplicate results
    unique_snippets = []
    seen = set()
    for s in snippets:
        key = s["title"].lower()[:40]
        if key not in seen:
            seen.add(key)
            unique_snippets.append(s)

    if unique_snippets:
        spoken_parts = []
        for s in unique_snippets[:3]:
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
            "count": len(unique_snippets),
            "results": unique_snippets[:max_results],
            "spoken": spoken_summary,
        }

    return {
        "success": True,
        "query": clean_query,
        "count": 1,
        "results": [{"title": clean_query, "snippet": f"No live search results available for {clean_query}.", "source": "Web Search"}],
        "spoken": f"I searched for {clean_query} but could not find live updates right now.",
    }
