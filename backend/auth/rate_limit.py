import time

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 15 * 60

# In-memory: resets on restart, single-process only (documented limitation, SPEC §4.3).
_attempts = {}


def check_rate_limit(ip):
    prune_expired_attempts()
    record = _attempts.get(ip)
    if record is None:
        return True
    return record["count"] < MAX_ATTEMPTS


def record_failed_attempt(ip):
    now = time.time()
    record = _attempts.get(ip)
    if record is None or now - record["window_start"] > WINDOW_SECONDS:
        _attempts[ip] = {"count": 1, "window_start": now}
        return
    record["count"] += 1


def clear_attempts(ip):
    _attempts.pop(ip, None)


def reset_attempts():
    _attempts.clear()


#---

def prune_expired_attempts():
    now = time.time()
    for ip in list(_attempts):
        if now - _attempts[ip]["window_start"] > WINDOW_SECONDS:
            del _attempts[ip]
