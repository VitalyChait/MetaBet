import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

# Base URLs
DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


class PolymarketAnalyzer:
    """
    Goal:
      - Pull HISTORICAL markets in a specified endDate window (e.g., 2020–2024)
      - Identify "settled" binary markets (winner inferable) using outcomePrices ≈ {1,0}
      - Pull trades from Data-API for each conditionId
      - Flag "suspicious" traders: contrarian vs majority + late entry + win (when winner known)

    Important:
      - 'endDate' is NOT "resolved at" time. It's the event horizon / close time.
      - 'umaResolutionStatus' can be present but not always a reliable "fully settled" indicator by itself.
      - For a hackathon-grade label, we treat a binary market as "settled" if outcomePrices are ~1 and ~0.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    # --------------------------
    # Safe parsers
    # --------------------------
    @staticmethod
    def safe_float(value, default=0.0) -> float:
        try:
            return float(value) if value is not None and value != "" else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def safe_timestamp(value) -> Optional[datetime]:
        """
        Convert timestamp-ish value to timezone-aware datetime (UTC).
        Handles:
          - ISO strings like "2025-01-01T00:00:00Z"
          - unix seconds as str/int/float
          - datetime objects
        """
        try:
            if value is None or value == "":
                return None

            if isinstance(value, datetime):
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value, tz=timezone.utc)

            if isinstance(value, str):
                s = value.strip()
                # ISO-ish
                if "T" in s or "-" in s:
                    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                # unix seconds string
                return datetime.fromtimestamp(int(s), tz=timezone.utc)
        except Exception:
            return None

        return None

    # --------------------------
    # Gamma helpers
    # --------------------------
    @staticmethod
    def _looks_closed(m: Dict[str, Any]) -> bool:
        # closed can be bool|null; active can be bool|null; closedTime may exist
        if m.get("closed") is True:
            return True
        if m.get("active") is False:
            return True
        if m.get("closedTime"):
            return True
        return False

    @staticmethod
    def _resolution_status(m: Dict[str, Any]) -> str:
        return str(m.get("umaResolutionStatus") or "").strip().lower()

    @staticmethod
    def is_binary_market(m: Dict[str, Any]) -> bool:
        outs = m.get("outcomes")
        return isinstance(outs, list) and len(outs) == 2

    @staticmethod
    def is_binary_settled(m: Dict[str, Any], hi: float = 0.98, lo: float = 0.02) -> bool:
        """
        Hackathon-grade "settled" test:
          - outcomePrices exists
          - two prices
          - one is ~1 and the other ~0
        """
        ps = m.get("outcomePrices")
        if not isinstance(ps, list) or len(ps) != 2:
            return False
        try:
            a, b = float(ps[0]), float(ps[1])
        except Exception:
            return False
        return (a >= hi and b <= lo) or (b >= hi and a <= lo)

    @staticmethod
    def infer_winner_from_outcome_prices(m: Dict[str, Any]) -> Optional[str]:
        """
        Infer winner using outcomes + outcomePrices.
        For binary markets with settled prices, this yields 'yes'/'no' most of the time.
        """
        outcomes = m.get("outcomes")
        prices = m.get("outcomePrices")

        if not isinstance(outcomes, list) or not isinstance(prices, list):
            return None
        if len(outcomes) != len(prices) or len(outcomes) == 0:
            return None

        try:
            p = [float(x) for x in prices]
        except Exception:
            return None

        idx = max(range(len(p)), key=lambda i: p[i])
        winner = str(outcomes[idx]).strip().lower()

        # normalize common yes/no
        if winner in {"yes", "no"}:
            return winner
        return winner  # for multi-outcome markets, keep label

    # --------------------------
    # Gamma: markets retrieval (HISTORICAL by endDate window)
    # --------------------------
    def get_markets_by_end_date_range(
        self,
        start_iso: str,
        end_iso: str,
        limit: int = 100,
        max_pages: int = 50,
        debug: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fetch markets whose endDate lies in [start_iso, end_iso].
        Uses server-side filters if supported; ALWAYS enforces client-side filter too.
        """
        url = f"{GAMMA_API}/markets"

        s_dt = self.safe_timestamp(start_iso)
        e_dt = self.safe_timestamp(end_iso)
        if not s_dt or not e_dt:
            raise ValueError("start_iso/end_iso must be valid ISO timestamps like 2020-01-01T00:00:00Z")

        all_markets: List[Dict[str, Any]] = []
        offset = 0

        for page in range(max_pages):
            params = {
                "limit": limit,
                "offset": offset,
                "order": "endDate",
                "ascending": False,
                # Try server-side range filtering (may vary by deployment)
                "end_date_min": start_iso,
                "end_date_max": end_iso,
            }

            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            batch = resp.json() or []

            if debug:
                print(f"DEBUG: page={page+1}, offset={offset}, returned={len(batch)}")

            if not batch:
                break

            all_markets.extend(batch)
            offset += limit

        # Client-side strict filter (works even if server ignores end_date_max/min)
        filtered = []
        for m in all_markets:
            end_dt = self.safe_timestamp(m.get("endDate") or m.get("endDateIso") or m.get("closedTime"))
            if end_dt and (s_dt <= end_dt <= e_dt):
                filtered.append(m)

        if debug:
            print(f"DEBUG: total_fetched={len(all_markets)} in_range={len(filtered)}")

        return filtered

    def filter_historical_settled_binary_markets(
        self,
        markets: List[Dict[str, Any]],
        require_closed_signal: bool = False,
        debug: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Keep binary markets where outcomePrices look settled (~1/~0).
        Optionally require a 'closed' signal.
        """
        kept = []
        for m in markets:
            if not self.is_binary_market(m):
                continue
            if require_closed_signal and (not self._looks_closed(m)):
                continue
            if not self.is_binary_settled(m):
                continue
            kept.append(m)

        if debug:
            print(f"DEBUG: binary_settled_markets={len(kept)} / input={len(markets)}")

        return kept

    # --------------------------
    # Data-API: trades retrieval
    # --------------------------
    @staticmethod
    def _unwrap_trades(resp_json: Any) -> List[Dict[str, Any]]:
        if resp_json is None:
            return []
        if isinstance(resp_json, list):
            return resp_json
        if isinstance(resp_json, dict) and isinstance(resp_json.get("trades"), list):
            return resp_json["trades"]
        return []

    def get_market_trades(self, condition_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get trades for a specific market by conditionId.
        """
        url = f"{DATA_API}/trades"
        params = {"market": condition_id, "limit": limit}
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return self._unwrap_trades(resp.json())
        except Exception as e:
            print(f"Error fetching market trades for {condition_id[:10]}...: {e}")
            return []

    # --------------------------
    # Analytics
    # --------------------------
    def analyze_trade_timing(self, trades: List[Dict[str, Any]], end_time: Any) -> Optional[Dict[str, Any]]:
        """
        Timing relative to END TIME (market's endDate/close horizon).
        """
        if not trades or not end_time:
            return None

        end_dt = self.safe_timestamp(end_time)
        if not end_dt:
            return None

        trade_times = []
        for t in trades:
            tt = self.safe_timestamp(t.get("timestamp") or t.get("transactionTime"))
            if tt:
                trade_times.append(tt)

        if not trade_times:
            return None

        first_trade = min(trade_times)
        last_trade = max(trade_times)
        hours_before_end = (end_dt - last_trade).total_seconds() / 3600
        hours_active = (last_trade - first_trade).total_seconds() / 3600

        return {
            "first_trade": first_trade,
            "last_trade": last_trade,
            "end_time": end_dt,
            "hours_before_end": hours_before_end,
            "hours_active": hours_active,
            "num_trades": len(trades),
            "late_entry": hours_before_end < 24,
            "early_exit": hours_before_end > 168,
        }

    def find_suspicious_traders(
        self,
        condition_id: str,
        market_data: Dict[str, Any],
        debug: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Suspicious heuristic for *settled binary markets*:
          - contrarian vs majority outcome volume
          - late entry (within 24h of endDate)
          - and WON (winner inferable from outcomePrices)
        """
        # winner must be inferable
        winner = self.infer_winner_from_outcome_prices(market_data)
        if winner not in {"yes", "no"}:
            return []

        trades = self.get_market_trades(condition_id)
        if not trades:
            return []

        end_time = market_data.get("endDate") or market_data.get("endDateIso") or market_data.get("closedTime")

        user_data = defaultdict(lambda: {
            "trades": [],
            "total_volume": 0.0,
            "yes_volume": 0.0,
            "no_volume": 0.0
        })

        for tr in trades:
            user = tr.get("proxyWallet") or tr.get("maker")
            if not user:
                continue

            size = self.safe_float(tr.get("size", 0))
            outcome = str(tr.get("outcome") or "").strip().lower()

            user_data[user]["trades"].append(tr)
            user_data[user]["total_volume"] += size
            if outcome == "yes":
                user_data[user]["yes_volume"] += size
            elif outcome == "no":
                user_data[user]["no_volume"] += size

        if not user_data:
            return []

        total_yes = sum(u["yes_volume"] for u in user_data.values())
        total_no = sum(u["no_volume"] for u in user_data.values())
        majority_outcome = "yes" if total_yes >= total_no else "no"

        results = []
        for user, d in user_data.items():
            user_position = "yes" if d["yes_volume"] >= d["no_volume"] else "no"
            is_contrarian = user_position != majority_outcome
            timing = self.analyze_trade_timing(d["trades"], end_time)
            won = (user_position == winner)

            results.append({
                "user": user,
                "position": user_position,
                "is_contrarian": is_contrarian,
                "won": won,
                "volume": d["total_volume"],
                "num_trades": len(d["trades"]),
                "timing": timing,
            })

        suspicious = [
            r for r in results
            if r["is_contrarian"]
            and r["won"]
            and r["timing"]
            and r["timing"]["late_entry"]
        ]

        suspicious_sorted = sorted(suspicious, key=lambda x: x["volume"], reverse=True)

        if debug:
            print(
                f"DEBUG: users={len(user_data)} suspicious={len(suspicious_sorted)} "
                f"majority={majority_outcome} winner={winner}"
            )

        return suspicious_sorted


if __name__ == "__main__":
    analyzer = PolymarketAnalyzer()

    # --------------------------
    # HISTORICAL WINDOW (YOU ASKED: 2020–2024)
    # --------------------------
    START_ISO = "2020-01-01T00:00:00Z"
    END_ISO = "2024-12-31T23:59:59Z"

    print(f"Fetching markets with endDate in [{START_ISO}, {END_ISO}] ...")
    markets = analyzer.get_markets_by_end_date_range(
        start_iso=START_ISO,
        end_iso=END_ISO,
        limit=100,
        max_pages=80,   # increase if you want more coverage
        debug=True
    )

    print("\nFiltering to settled binary markets (winner inferable via outcomePrices ~1/~0)...")
    settled_binary = analyzer.filter_historical_settled_binary_markets(
        markets,
        require_closed_signal=False,  # set True if you want stricter filtering
        debug=True
    )

    print(f"\nFound {len(settled_binary)} settled binary markets in 2020–2024.\n")

    # Analyze first few markets
    for i, market in enumerate(settled_binary[:3]):
        print(f"\n{'='*80}")
        print(f"Market {i+1}: {market.get('question', 'N/A')}")
        cid = market.get("conditionId", "N/A")
        print(f"Condition ID: {cid}")

        volume = analyzer.safe_float(market.get("volume", 0))
        print(f"Volume: ${volume:,.2f}")

        end_dt = analyzer.safe_timestamp(market.get("endDate") or market.get("endDateIso") or market.get("closedTime"))
        if end_dt:
            print(f"End date (UTC): {end_dt.strftime('%Y-%m-%d %H:%M')}")

        print(f"UMA status: {market.get('umaResolutionStatus', 'N/A')}")
        print(f"outcomes: {market.get('outcomes')}")
        print(f"outcomePrices: {market.get('outcomePrices')}")

        winner = analyzer.infer_winner_from_outcome_prices(market)
        print(f"Winner (inferred): {winner if winner else 'N/A'}")

        print("\nAnalyzing traders...")
        if cid != "N/A":
            suspicious = analyzer.find_suspicious_traders(cid, market, debug=False)

            if suspicious:
                print(f"\nFound {len(suspicious)} suspicious traders (contrarian + late entry + win):")
                for j, trader in enumerate(suspicious[:5], 1):
                    print(f"\n  {j}. User: {str(trader['user'])[:10]}...")
                    print(f"     Volume: ${trader['volume']:,.2f}")
                    print(f"     Position: {trader['position'].upper()} (contrarian)")
                    if trader["timing"]:
                        t = trader["timing"]
                        print(f"     Last trade: {t['hours_before_end']:.1f}h before end")
                        print(f"     Trading window: {t['hours_active']:.1f}h")
                        print(f"     Number of trades: {t['num_trades']}")
            else:
                print("  No suspicious patterns found")

    print("\n" + "=" * 80)
    print("\nAnalysis complete!")
    print("\nNext steps:")
    print("1. Expand max_pages / adjust window to increase sample size")
    print("2. Cache markets and trades locally (CSV/parquet) to avoid re-hitting APIs")
    print("3. Compute cross-market user features (consistency, timing edge, domain concentration)")
