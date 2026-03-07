#!/usr/bin/env python3
"""
Smoke test: Pull real fantasy questions from Reddit and fire them at the backend.
Reports success/failure/latency for each.
"""

import json
import os
import time
import urllib.request
import urllib.error
import sys
from datetime import datetime, timezone

API_BASE = "https://backend.benchgoblins.com"

# Subreddit -> sport mapping
SUBREDDITS = {
    "fantasyfootball": "nfl",
    "fantasybball": "nba",
    "fantasybaseball": "mlb",
    "fantasyhockey": "nhl",
    "FantasyPL": "soccer",
}

RISK_MODES = ["floor", "median", "ceiling"]


def fetch_reddit_titles(subreddit: str, limit: int = 50) -> list[str]:
    """Fetch post titles from a subreddit using public JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "BenchGoblins-Test/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        titles = []
        for post in data.get("data", {}).get("children", []):
            title = post["data"]["title"]
            # Filter: skip meta/mod posts, keep question-like titles
            if any(skip in title.lower() for skip in [
                "index", "megathread", "game thread", "official",
                "mod", "rule", "weekly", "daily", "[meta]",
                "upvote", "discord", "podcast"
            ]):
                continue
            titles.append(title)
        return titles
    except Exception as e:
        print(f"  Failed to fetch r/{subreddit}: {e}")
        return []


def make_question(title: str) -> str:
    """Convert a Reddit title into a question if it isn't already."""
    title = title.strip()
    if title.endswith("?"):
        return title
    # Common fantasy patterns that are implicitly questions
    return title


def send_decide(query: str, sport: str, risk_mode: str = "median") -> dict:
    """Send a /decide request and return result with timing."""
    payload = json.dumps({
        "sport": sport,
        "query": query[:1000],  # API max_length
        "risk_mode": risk_mode,
    }).encode()

    req = urllib.request.Request(
        f"{API_BASE}/decide",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            elapsed = time.time() - start
            return {
                "status": "ok",
                "code": resp.status,
                "decision": body.get("decision", "")[:80],
                "confidence": body.get("confidence", ""),
                "source": body.get("source", ""),
                "latency": round(elapsed, 2),
            }
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        try:
            detail = json.loads(e.read().decode()).get("detail", str(e))
        except Exception:
            detail = str(e)
        return {
            "status": "error",
            "code": e.code,
            "detail": str(detail)[:120],
            "latency": round(elapsed, 2),
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "status": "error",
            "code": 0,
            "detail": str(e)[:120],
            "latency": round(elapsed, 2),
        }


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    per_sport = target // len(SUBREDDITS)

    print(f"Target: {target} questions ({per_sport} per sport)\n")
    print("Fetching questions from Reddit...")

    all_questions: list[tuple[str, str]] = []  # (query, sport)

    for sub, sport in SUBREDDITS.items():
        titles = fetch_reddit_titles(sub, limit=per_sport + 20)
        questions = [make_question(t) for t in titles[:per_sport]]
        print(f"  r/{sub} ({sport}): {len(questions)} questions")
        all_questions.extend((q, sport) for q in questions)

    # If we didn't get enough from Reddit, pad with generated questions
    fallback_questions = {
        "nfl": [
            "Start Mahomes or Hurts this week?",
            "Is Travis Kelce droppable at this point?",
            "Best waiver wire RB for Week 14?",
            "Trade CeeDee Lamb for Amon-Ra St. Brown?",
            "Flex Jaylen Waddle or Keenan Allen?",
            "Is the Bills defense a good stream this week?",
            "Drop Dalton Kincaid for Sam LaPorta?",
            "Start Breece Hall or De'Von Achane in PPR?",
            "Is Puka Nacua worth keeping through his bye?",
            "Rank these QBs: Stroud, Richardson, Daniels",
        ],
        "nba": [
            "Start LaMelo or Brunson tonight?",
            "Is Wembanyama a sell-high in category leagues?",
            "Best streaming center for blocks this week?",
            "Trade Haliburton for Trae Young straight up?",
            "Sit Kawhi again or risk the DNP?",
            "Top waiver adds in 12-team points leagues?",
            "Is Chet Holmgren droppable in 10-team?",
            "Start Maxey or Ant-Man in a close matchup?",
            "Best punt FG% build this week?",
            "Drop Zion for Draymond Green?",
        ],
        "mlb": [
            "Start Corbin Carroll or Fernando Tatis tonight?",
            "Is Gerrit Cole a must-start against Houston?",
            "Best waiver wire closer for saves?",
            "Trade Juan Soto for Mookie Betts?",
            "Sit Freddie Freeman against a lefty?",
            "Top streaming pitchers for this week?",
            "Is Gunnar Henderson a first-round pick next year?",
            "Drop Tyler Glasnow for Tarik Skubal?",
            "Best DFS stack for tonight's slate?",
            "Rank: Acuna, Ohtani, Soto ROS",
        ],
        "nhl": [
            "Start Shesterkin or Hellebuyck tonight?",
            "Is Connor McDavid in a scoring slump?",
            "Best streaming goalie for the weekend?",
            "Trade Auston Matthews for Leon Draisaitl?",
            "Drop Andrei Vasilevskiy for Ilya Sorokin?",
            "Top fantasy defensemen this week?",
            "Is Makar worth a first-round pick?",
            "Start Kaprizov or Rantanen tonight?",
            "Best waiver wire forwards for points leagues?",
            "Sit Markstrom against Colorado?",
        ],
        "soccer": [
            "Captain Haaland or Salah this gameweek?",
            "Is Saka worth the premium price tag?",
            "Best budget midfielders under 7.0?",
            "Transfer out Son for Palmer?",
            "Triple captain on the DGW?",
            "Best defensive picks for clean sheets?",
            "Is Watkins nailed after the Duran signing?",
            "Start Isak or Cunha this week?",
            "Wildcard template for GW20?",
            "Drop TAA for Saliba?",
        ],
    }

    while len(all_questions) < target:
        for sport, questions in fallback_questions.items():
            for q in questions:
                if len(all_questions) >= target:
                    break
                all_questions.append((q, sport))
            if len(all_questions) >= target:
                break

    all_questions = all_questions[:target]
    print(f"\nTotal questions to test: {len(all_questions)}")
    print("=" * 80)

    # Send questions (sequential to avoid rate limiting)
    results = {"ok": 0, "error": 0, "rate_limited": 0, "off_topic": 0}
    sources = {"claude": 0, "local": 0, "unknown": 0}
    latencies = []
    errors = []

    for i, (query, sport) in enumerate(all_questions):
        risk = RISK_MODES[i % 3]
        result = send_decide(query, sport, risk)

        status_icon = "+" if result["status"] == "ok" else "x"
        line = f"[{i+1:3d}/{len(all_questions)}] [{status_icon}] ({sport:>6s}/{risk:>7s}) "

        if result["status"] == "ok":
            results["ok"] += 1
            src = result.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
            latencies.append(result["latency"])
            line += f'{result["decision"][:60]:60s} [{result["confidence"]:>6s}] {result["latency"]:5.1f}s'
        else:
            code = result.get("code", 0)
            detail = result.get("detail", "")
            if code == 429:
                results["rate_limited"] += 1
                line += f"RATE LIMITED: {detail[:60]}"
            elif "off-topic" in detail.lower() or "fantasy sports questions" in detail.lower() or "built for fantasy" in detail.lower():
                results["off_topic"] += 1
                line += f"OFF-TOPIC: {query[:50]}"
            else:
                results["error"] += 1
                errors.append((query[:50], sport, code, detail[:80]))
                line += f"ERROR {code}: {detail[:60]}"

        print(line)

        # Delay between requests to avoid rate limiting
        if i < len(all_questions) - 1:
            time.sleep(1.0)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total:        {len(all_questions)}")
    print(f"Success:      {results['ok']}")
    print(f"Off-topic:    {results['off_topic']}")
    print(f"Rate limited: {results['rate_limited']}")
    print(f"Errors:       {results['error']}")

    if latencies:
        avg = sum(latencies) / len(latencies)
        p50 = sorted(latencies)[len(latencies) // 2]
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"\nLatency (successful):")
        print(f"  Avg:  {avg:.2f}s")
        print(f"  p50:  {p50:.2f}s")
        print(f"  p95:  {p95:.2f}s")
        print(f"  Min:  {min(latencies):.2f}s")
        print(f"  Max:  {max(latencies):.2f}s")

    print(f"\nSources: {dict(sources)}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for q, sport, code, detail in errors[:10]:
            print(f"  [{sport}] {code}: {q} -> {detail}")

    success_rate = results["ok"] / len(all_questions) * 100 if all_questions else 0
    print(f"\nSuccess rate: {success_rate:.1f}%")

    # Save run to history
    acceptable = results["ok"] + results["off_topic"]
    acceptable_pct = acceptable / len(all_questions) * 100 if all_questions else 0

    run_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(all_questions),
        "success": results["ok"],
        "off_topic": results["off_topic"],
        "rate_limited": results["rate_limited"],
        "errors": results["error"],
        "success_rate_pct": round(success_rate, 1),
        "acceptable_pct": round(acceptable_pct, 1),
        "sources": dict(sources),
    }
    if latencies:
        run_record["latency"] = {
            "avg": round(avg, 2),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "min": round(min(latencies), 2),
            "max": round(max(latencies), 2),
        }

    history_path = os.path.join(os.path.dirname(__file__), "test_results.jsonl")
    with open(history_path, "a") as f:
        f.write(json.dumps(run_record) + "\n")
    print(f"\nRun saved to {history_path}")

    # Exit code: fail if less than 80% acceptable
    if acceptable_pct < 80:
        print("\nFAIL: Less than 80% acceptable responses")
        sys.exit(1)
    else:
        print("\nPASS")


if __name__ == "__main__":
    main()
