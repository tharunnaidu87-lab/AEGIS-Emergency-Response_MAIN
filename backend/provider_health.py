"""Last observed provider result, never a claim that configured means healthy."""
from datetime import datetime, timezone
from threading import Lock
import time

_lock = Lock()
_state = {}


def record(provider, success, reason=None, status=None):
    with _lock:
        failures = 0 if success else _state.get(provider, {}).get('consecutive_failures', 0) + 1
        _state[provider] = {'status': 'LAST_REQUEST_SUCCEEDED' if success else 'DEGRADED',
            'checked_at': datetime.now(timezone.utc).isoformat(), 'reason': reason, 'http_status': status,
            'consecutive_failures': failures, 'retry_after': time.time() + 60 if failures >= 3 else 0}


def paused(provider):
    with _lock:
        return _state.get(provider, {}).get('retry_after', 0) > time.time()


def snapshot():
    with _lock:
        return {name: dict(_state.get(name, {'status': 'NOT_PROBED'})) for name in ['speech', 'nlp']}
