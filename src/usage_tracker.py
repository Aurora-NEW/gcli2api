"""
In-memory usage tracker for panel dashboards.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


def _safe_int(value: Any) -> int:
    try:
        ivalue = int(value or 0)
        return ivalue if ivalue > 0 else 0
    except Exception:
        return 0


def normalize_token_stats(tokens: Optional[Dict[str, Any]]) -> Dict[str, int]:
    token_data = tokens or {}
    input_tokens = _safe_int(
        token_data.get("input_tokens")
        or token_data.get("prompt_tokens")
        or token_data.get("inputTokens")
    )
    output_tokens = _safe_int(
        token_data.get("output_tokens")
        or token_data.get("completion_tokens")
        or token_data.get("outputTokens")
    )
    reasoning_tokens = _safe_int(
        token_data.get("reasoning_tokens")
        or token_data.get("thoughts_tokens")
        or token_data.get("reasoningTokens")
    )
    cached_tokens = _safe_int(
        token_data.get("cached_tokens")
        or token_data.get("cache_read_input_tokens")
        or token_data.get("cachedTokens")
    )
    total_tokens = _safe_int(
        token_data.get("total_tokens")
        or token_data.get("totalTokenCount")
        or token_data.get("totalTokens")
    )
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens + reasoning_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": total_tokens,
    }


class UsageTracker:
    def __init__(self, max_details: int = 50000):
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max_details)
        self._lock = threading.RLock()

    def record(
        self,
        api: str,
        model: str,
        source: str,
        auth_index: str,
        failed: bool,
        tokens: Optional[Dict[str, Any]] = None,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        event = {
            "api": (api or "unknown").strip() or "unknown",
            "model": (model or "unknown").strip() or "unknown",
            "source": (source or "unknown").strip() or "unknown",
            "auth_index": (auth_index or source or "-").strip() or "-",
            "failed": bool(failed),
            "status_code": _safe_int(status_code) if status_code is not None else 0,
            "error_message": (error_message or "").strip(),
            "tokens": normalize_token_stats(tokens),
            "timestamp": float(timestamp if timestamp is not None else time.time()),
        }
        with self._lock:
            self._events.append(event)

    def reset(self, source: Optional[str] = None) -> int:
        with self._lock:
            if not source:
                removed = len(self._events)
                self._events.clear()
                return removed

            target = source.strip()
            if not target:
                return 0

            before = len(self._events)
            kept = [e for e in self._events if e.get("source") != target]
            self._events = deque(kept, maxlen=self._events.maxlen)
            return before - len(self._events)

    def _snapshot_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def get_stats_24h(self) -> Dict[str, Dict[str, int]]:
        events = self._snapshot_events()
        cutoff = time.time() - 24 * 3600
        stats: Dict[str, Dict[str, int]] = {}
        for event in events:
            if event["timestamp"] < cutoff:
                continue
            source = event["source"]
            item = stats.setdefault(
                source,
                {
                    "calls_24h": 0,
                    "success_24h": 0,
                    "failed_24h": 0,
                    "tokens_24h": 0,
                },
            )
            item["calls_24h"] += 1
            if event["failed"]:
                item["failed_24h"] += 1
            else:
                item["success_24h"] += 1
            item["tokens_24h"] += event["tokens"]["total_tokens"]
        return stats

    def get_aggregated_24h(self) -> Dict[str, float]:
        stats = self.get_stats_24h()
        total_calls = sum(item["calls_24h"] for item in stats.values())
        total_files = len(stats)
        avg_calls = (total_calls / total_files) if total_files else 0.0
        return {
            "total_calls_24h": total_calls,
            "total_files": total_files,
            "avg_calls_per_file": avg_calls,
        }

    def snapshot(self) -> Dict[str, Any]:
        events = self._snapshot_events()

        total_requests = len(events)
        success_count = 0
        failure_count = 0
        total_tokens = 0

        apis: Dict[str, Dict[str, Any]] = {}
        requests_by_day: Dict[str, int] = {}
        requests_by_hour: Dict[str, int] = {}
        tokens_by_day: Dict[str, int] = {}
        tokens_by_hour: Dict[str, int] = {}

        for event in events:
            ts = float(event["timestamp"])
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            day_key = dt.strftime("%Y-%m-%d")
            hour_key = dt.strftime("%H")

            token_total = _safe_int(event["tokens"].get("total_tokens"))
            total_tokens += token_total

            if event["failed"]:
                failure_count += 1
            else:
                success_count += 1

            requests_by_day[day_key] = requests_by_day.get(day_key, 0) + 1
            requests_by_hour[hour_key] = requests_by_hour.get(hour_key, 0) + 1
            tokens_by_day[day_key] = tokens_by_day.get(day_key, 0) + token_total
            tokens_by_hour[hour_key] = tokens_by_hour.get(hour_key, 0) + token_total

            api_name = event["api"]
            model_name = event["model"]
            api_data = apis.setdefault(
                api_name,
                {
                    "total_requests": 0,
                    "total_tokens": 0,
                    "models": {},
                },
            )
            api_data["total_requests"] += 1
            api_data["total_tokens"] += token_total

            model_data = api_data["models"].setdefault(
                model_name,
                {
                    "total_requests": 0,
                    "total_tokens": 0,
                    "details": [],
                },
            )
            model_data["total_requests"] += 1
            model_data["total_tokens"] += token_total
            model_data["details"].append(
                {
                    "timestamp": dt.isoformat().replace("+00:00", "Z"),
                    "source": event["source"],
                    "auth_index": event["auth_index"],
                    "tokens": {
                        "input_tokens": event["tokens"]["input_tokens"],
                        "output_tokens": event["tokens"]["output_tokens"],
                        "reasoning_tokens": event["tokens"]["reasoning_tokens"],
                        "cached_tokens": event["tokens"]["cached_tokens"],
                        "total_tokens": event["tokens"]["total_tokens"],
                    },
                    "failed": bool(event["failed"]),
                }
            )

        return {
            "total_requests": total_requests,
            "success_count": success_count,
            "failure_count": failure_count,
            "total_tokens": total_tokens,
            "apis": apis,
            "requests_by_day": requests_by_day,
            "requests_by_hour": requests_by_hour,
            "tokens_by_day": tokens_by_day,
            "tokens_by_hour": tokens_by_hour,
        }


_usage_tracker = UsageTracker()


def get_usage_tracker() -> UsageTracker:
    return _usage_tracker
