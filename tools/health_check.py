#!/usr/bin/env python3
"""Health check tool for the Tent of Trials platform (issue #193: retry policy)."""

import argparse
import contextlib
import io as _io
import json
import os
import random
import re as _re
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

SERVICES = {
    "backend": {"host": "localhost", "port": 8080, "path": "/health", "timeout": 5},
    "market": {"host": "localhost", "port": 8081, "path": "/health", "timeout": 5},
    "frailbox": {"host": "localhost", "port": 8082, "path": "/health", "timeout": 10},
    "frontend": {"host": "localhost", "port": 3000, "path": "/", "timeout": 5},
}

INFRASTRUCTURE = {
    "postgresql": {"host": os.environ.get("DB_HOST", "localhost"), "port": int(os.environ.get("DB_PORT", "5432")), "timeout": 5},
    "redis": {"host": os.environ.get("REDIS_HOST", "localhost"), "port": int(os.environ.get("REDIS_PORT", "6379")), "timeout": 5},
    "kafka": {"host": os.environ.get("KAFKA_HOST", "localhost"), "port": int(os.environ.get("KAFKA_PORT", "9092")), "timeout": 5},
}

DISK_THRESHOLD_WARNING = 80
DISK_THRESHOLD_CRITICAL = 90
MEMORY_THRESHOLD_WARNING = 80
MEMORY_THRESHOLD_CRITICAL = 90

DEFAULT_RETRIES = 2
DEFAULT_TIMEOUT_SECS = 5
DEFAULT_BACKOFF_SECS = 0.5

_RETRYABLE_EXCEPTIONS = (
    socket.timeout, TimeoutError, ConnectionError,
    socket.gaierror, socket.herror, OSError,
)


def _is_retryable_http_status(status):
    return 500 <= status <= 599


def _log_attempt(attempt, max_attempts, elapsed_ms, reason):
    sys.stderr.write(
        f"[health_check] attempt {attempt}/{max_attempts} failed after {elapsed_ms:.0f}ms: {reason}\n"
    )
    sys.stderr.flush()


def _sleep_backoff(attempt, base_backoff):
    if base_backoff <= 0:
        return
    delay = base_backoff * (2 ** (attempt - 1))
    delay += random.uniform(0, delay * 0.25)
    time.sleep(delay)


def check_http_service(host, port, path, timeout,
                       retries=DEFAULT_RETRIES,
                       backoff_secs=DEFAULT_BACKOFF_SECS):
    """Probe HTTP with retry on transient errors (timeouts, conn errors, 5xx).
    Does NOT retry 4xx (deterministic client errors)."""
    import http.client
    max_attempts = max(1, retries + 1)
    last_result = ("CRITICAL", "no attempt made", 0)
    for attempt in range(1, max_attempts + 1):
        start = time.perf_counter()
        try:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
            try:
                conn.request("GET", path)
                resp = conn.getresponse()
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")[:200]
            finally:
                conn.close()
            elapsed_ms = (time.perf_counter() - start) * 1000
            if status == 200:
                if attempt > 1:
                    _log_attempt(attempt, max_attempts, elapsed_ms,
                                 f"recovered with HTTP {status}")
                return ("OK", f"HTTP {status}", status)
            if _is_retryable_http_status(status):
                last_result = ("CRITICAL", f"HTTP {status}: {body[:100]}", status)
                if attempt < max_attempts:
                    _log_attempt(attempt, max_attempts, elapsed_ms,
                                 f"HTTP {status} (transient)")
                    _sleep_backoff(attempt, backoff_secs)
                    continue
                return last_result
            return ("WARNING", f"HTTP {status}: {body[:100]}", status)
        except _RETRYABLE_EXCEPTIONS as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            reason = f"{type(e).__name__}: {e}"
            last_result = ("CRITICAL", str(e), 0)
            if attempt < max_attempts:
                _log_attempt(attempt, max_attempts, elapsed_ms, reason)
                _sleep_backoff(attempt, backoff_secs)
                continue
            _log_attempt(attempt, max_attempts, elapsed_ms, reason)
            return last_result
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            last_result = ("CRITICAL", str(e), 0)
            _log_attempt(attempt, max_attempts, elapsed_ms,
                         f"{type(e).__name__}: {e}")
            return last_result
    return last_result


def check_tcp_port(host, port, timeout,
                   retries=DEFAULT_RETRIES,
                   backoff_secs=DEFAULT_BACKOFF_SECS):
    """Probe TCP with retry on transient errors."""
    max_attempts = max(1, retries + 1)
    last_result = ("CRITICAL", "no attempt made", 0.0)
    for attempt in range(1, max_attempts + 1):
        start = time.perf_counter()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            latency = (time.perf_counter() - start) * 1000
            if attempt > 1:
                _log_attempt(attempt, max_attempts, latency,
                             "recovered: connection established")
            return ("OK", f"Connected ({latency:.1f}ms)", latency)
        except socket.timeout:
            elapsed_ms = (time.perf_counter() - start) * 1000
            last_result = ("CRITICAL", f"Connection timeout ({timeout}s)", 0.0)
            if attempt < max_attempts:
                _log_attempt(attempt, max_attempts, elapsed_ms, "timeout")
                _sleep_backoff(attempt, backoff_secs)
                continue
            _log_attempt(attempt, max_attempts, elapsed_ms, "timeout")
            return last_result
        except ConnectionRefusedError:
            elapsed_ms = (time.perf_counter() - start) * 1000
            last_result = ("CRITICAL", "Connection refused", 0.0)
            if attempt < max_attempts:
                _log_attempt(attempt, max_attempts, elapsed_ms, "ConnectionRefusedError")
                _sleep_backoff(attempt, backoff_secs)
                continue
            _log_attempt(attempt, max_attempts, elapsed_ms, "ConnectionRefusedError")
            return last_result
        except _RETRYABLE_EXCEPTIONS as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            reason = f"{type(e).__name__}: {e}"
            last_result = ("CRITICAL", str(e), 0.0)
            if attempt < max_attempts:
                _log_attempt(attempt, max_attempts, elapsed_ms, reason)
                _sleep_backoff(attempt, backoff_secs)
                continue
            _log_attempt(attempt, max_attempts, elapsed_ms, reason)
            return last_result
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            last_result = ("CRITICAL", str(e), 0.0)
            _log_attempt(attempt, max_attempts, elapsed_ms,
                         f"{type(e).__name__}: {e}")
            return last_result
    return last_result


def check_certificate_expiry(host, port=443):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return "WARNING", "No certificate found", 0
                from datetime import datetime as dt
                expires = dt.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                days_left = (expires - dt.now()).days
                if days_left > 30:
                    return "OK", f"Certificate expires in {days_left} days", days_left
                elif days_left > 7:
                    return "WARNING", f"Certificate expires in {days_left} days", days_left
                else:
                    return "CRITICAL", f"Certificate expires in {days_left} days", days_left
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_disk_usage(path="/"):
    try:
        stat = os.statvfs(path)
        total = stat.f_frsize * stat.f_blocks
        free = stat.f_frsize * stat.f_bavail
        used = total - free
        pct = (used / total) * 100
        if pct < DISK_THRESHOLD_WARNING:
            return "OK", f"{pct:.1f}% used", pct
        elif pct < DISK_THRESHOLD_CRITICAL:
            return "WARNING", f"{pct:.1f}% used", pct
        else:
            return "CRITICAL", f"{pct:.1f}% used", pct
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_memory_usage():
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    try:
                        meminfo[parts[0].strip()] = int(parts[1].strip().replace(" kB", "")) * 1024
                    except ValueError:
                        pass
        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", 0)
        used = total - available
        pct = (used / total) * 100 if total > 0 else 0
        if pct < MEMORY_THRESHOLD_WARNING:
            return "OK", f"{pct:.1f}% used", pct
        elif pct < MEMORY_THRESHOLD_CRITICAL:
            return "WARNING", f"{pct:.1f}% used", pct
        else:
            return "CRITICAL", f"{pct:.1f}% used", pct
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def check_load_average():
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().strip().split()
            load = float(parts[0])
            cpu_count = os.cpu_count() or 1
            load_pct = (load / cpu_count) * 100
            if load_pct < 70:
                return "OK", f"Load: {load}", load
            elif load_pct < 90:
                return "WARNING", f"Load: {load}", load
            else:
                return "CRITICAL", f"Load: {load}", load
    except Exception as e:
        return "WARNING", f"Cannot check: {e}", 0


def _attempt_collector():
    records = []
    def record(name, category, attempt, max_attempts, elapsed_ms, success, failure_reason):
        records.append({
            "target": name, "category": category, "attempt": attempt,
            "max_attempts": max_attempts, "elapsed_ms": round(elapsed_ms, 2),
            "success": success, "failure_reason": failure_reason,
        })
    def finalize(results):
        results["attempts"] = records
    return records, record, finalize


def run_health_checks(service=None, json_output=False,
                       retries=DEFAULT_RETRIES,
                       timeout_secs=DEFAULT_TIMEOUT_SECS,
                       backoff_secs=DEFAULT_BACKOFF_SECS):
    results = {
        "timestamp": datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "services": {},
        "infrastructure": {},
        "system": {},
        "overall_status": "OK",
    }
    _, record_attempt, finalize = _attempt_collector()
    attach_attempts = json_output
    all_ok = True
    for name, config in SERVICES.items():
        if service and name != service:
            continue
        status, detail, code, _ = _check_http_with_attempts(
            config["host"], config["port"], config["path"],
            timeout=timeout_secs if timeout_secs else config["timeout"],
            retries=retries, backoff_secs=backoff_secs,
            on_attempt=lambda *a: record_attempt(name, "service", *a),
        )
        results["services"][name] = {
            "status": status, "detail": detail, "code": code,
            "endpoint": f"http://{config['host']}:{config['port']}{config['path']}",
        }
        if status == "CRITICAL":
            all_ok = False
    for name, config in INFRASTRUCTURE.items():
        if service and name != service:
            continue
        status, detail, latency, _ = _check_tcp_with_attempts(
            config["host"], config["port"],
            timeout=timeout_secs if timeout_secs else config["timeout"],
            retries=retries, backoff_secs=backoff_secs,
            on_attempt=lambda *a: record_attempt(name, "infrastructure", *a),
        )
        results["infrastructure"][name] = {
            "status": status, "detail": detail,
            "endpoint": f"{config['host']}:{config['port']}",
        }
        if status == "CRITICAL":
            all_ok = False
    disk_status, disk_detail, _ = check_disk_usage()
    results["system"]["disk"] = {"status": disk_status, "detail": disk_detail}
    if disk_status == "CRITICAL":
        all_ok = False
    mem_status, mem_detail, _ = check_memory_usage()
    results["system"]["memory"] = {"status": mem_status, "detail": mem_detail}
    if mem_status == "CRITICAL":
        all_ok = False
    load_status, load_detail, _ = check_load_average()
    results["system"]["load"] = {"status": load_status, "detail": load_detail}
    for name, config in SERVICES.items():
        if service and name != service:
            continue
        if config["port"] == 443:
            cert_status, cert_detail, days_left = check_certificate_expiry(config["host"])
            results["services"][name]["certificate"] = {
                "status": cert_status, "detail": cert_detail,
                "days_remaining": days_left,
            }
            if cert_status == "CRITICAL":
                all_ok = False
    results["overall_status"] = "OK" if all_ok else "DEGRADED"
    if attach_attempts:
        finalize(results)
    return results


@contextlib.contextmanager
def _captured_stderr():
    buf = _io.StringIO()
    original = sys.stderr
    class _TeeWriter:
        def write(self, s):
            buf.write(s); original.write(s)
        def flush(self):
            original.flush()
    sys.stderr = _TeeWriter()
    try:
        yield buf
    finally:
        sys.stderr = original


_ATTEMPT_LINE_RE = _re.compile(
    r"\[health_check\] attempt (\d+)/(\d+) failed after (\d+)ms: (.*)$"
)


def _parse_attempt_lines(buf, max_attempts, on_attempt, succeeded):
    for raw in buf.getvalue().splitlines():
        m = _ATTEMPT_LINE_RE.match(raw)
        if not m:
            continue
        attempt = int(m.group(1))
        elapsed_ms = float(m.group(3))
        reason = m.group(4)
        if reason.startswith("recovered"):
            on_attempt(attempt, max_attempts, elapsed_ms, True, reason)
        else:
            on_attempt(attempt, max_attempts, elapsed_ms, False, reason)


def _check_http_with_attempts(host, port, path, timeout, retries, backoff_secs, on_attempt):
    max_attempts = max(1, retries + 1)
    with _captured_stderr() as buf:
        status, detail, code = check_http_service(
            host, port, path, timeout=timeout,
            retries=retries, backoff_secs=backoff_secs,
        )
    _parse_attempt_lines(buf, max_attempts, on_attempt, succeeded=(status == "OK"))
    return status, detail, code, max_attempts


def _check_tcp_with_attempts(host, port, timeout, retries, backoff_secs, on_attempt):
    max_attempts = max(1, retries + 1)
    with _captured_stderr() as buf:
        status, detail, latency = check_tcp_port(
            host, port, timeout=timeout,
            retries=retries, backoff_secs=backoff_secs,
        )
    _parse_attempt_lines(buf, max_attempts, on_attempt, succeeded=(status == "OK"))
    return status, detail, latency, max_attempts


def print_health_report(results):
    print(f"\n{'='*60}")
    print(f"  HEALTH CHECK REPORT")
    print(f"  Host: {results['hostname']}")
    print(f"  Time: {results['timestamp']}")
    print(f"  Overall: {results['overall_status']}")
    print(f"{'='*60}")
    for category, items in [("Services", results["services"]),
                             ("Infrastructure", results["infrastructure"]),
                             ("System", results["system"])]:
        if items:
            print(f"\n  {category}:")
            for name, check in items.items():
                if isinstance(check, dict) and "status" in check:
                    icon = {"OK": "v", "WARNING": "!", "CRITICAL": "x"}.get(check["status"], "?")
                    print(f"    {icon} {name}: {check['detail']}")
                else:
                    print(f"    {name}:")
                    for sub_name, sub_check in check.items():
                        if isinstance(sub_check, dict) and "status" in sub_check:
                            icon = {"OK": "v", "WARNING": "!", "CRITICAL": "x"}.get(sub_check["status"], "?")
                            print(f"      {icon} {sub_name}: {sub_check['detail']}")
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="Health check tool")
    parser.add_argument("--service", "-s", help="Check specific service only")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output (includes per-attempt details)")
    parser.add_argument("--watch", "-w", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--retries", "-r", type=int, default=DEFAULT_RETRIES,
                        help=f"Number of retries on transient failure (default: {DEFAULT_RETRIES})")
    parser.add_argument("--timeout-secs", "-t", type=int, default=None,
                        help=f"Per-attempt timeout in seconds (default: {DEFAULT_TIMEOUT_SECS})")
    parser.add_argument("--backoff-secs", "-b", type=float, default=DEFAULT_BACKOFF_SECS,
                        help=f"Initial backoff in seconds between retries (default: {DEFAULT_BACKOFF_SECS})")
    return parser.parse_args()


def main():
    args = parse_args()
    timeout_secs = args.timeout_secs if args.timeout_secs is not None else DEFAULT_TIMEOUT_SECS
    if args.retries < 0 or timeout_secs <= 0 or args.backoff_secs < 0:
        print("error: invalid retry/timeout/backoff arguments", file=sys.stderr)
        return 2
    if args.watch:
        print(f"Continuous monitoring (interval: {args.interval}s). Ctrl+C to stop.")
        try:
            while True:
                results = run_health_checks(
                    service=args.service, json_output=args.json,
                    retries=args.retries, timeout_secs=timeout_secs,
                    backoff_secs=args.backoff_secs,
                )
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    print_health_report(results)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
    else:
        results = run_health_checks(
            service=args.service, json_output=args.json,
            retries=args.retries, timeout_secs=timeout_secs,
            backoff_secs=args.backoff_secs,
        )
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_health_report(results)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Report saved to {args.output}")
        if results["overall_status"] == "DEGRADED":
            return 1
    return 0


if __name__ == "__main__":
    main()
