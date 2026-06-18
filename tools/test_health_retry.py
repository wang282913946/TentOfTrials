#!/usr/bin/env python3
"""Tests for issue #193: retry / backoff behaviour in tools/health_check.py."""

from __future__ import annotations

import contextlib
import http.server
import io
import json
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
import unittest
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import health_check  # noqa: E402


class _FlakyHTTPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that fails the first N requests, then returns 200."""

    fail_count: int = 0
    fail_status: int = 503
    always_status: int = 0
    request_log: List[Tuple[str, int]] = []

    def do_GET(self):  # noqa: N802
        self.__class__.request_log.append((self.path, int(time.time() * 1000)))
        if self.__class__.always_status:
            self._send(self.__class__.always_status, b'{"error":"forced"}')
            return
        if len(self.__class__.request_log) <= self.__class__.fail_count:
            self._send(self.__class__.fail_status, b'{"error":"transient"}')
            return
        self._send(200, b'{"status":"ok"}')

    def _send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class _ReusingThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


@contextlib.contextmanager
def start_mock_http_server(fail_count=0, fail_status=503, always_status=0):
    _FlakyHTTPHandler.fail_count = fail_count
    _FlakyHTTPHandler.fail_status = fail_status
    _FlakyHTTPHandler.always_status = always_status
    _FlakyHTTPHandler.request_log = []
    server = _ReusingThreadedServer(("127.0.0.1", 0), _FlakyHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield host, port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@contextlib.contextmanager
def start_delayed_tcp_server(delay_secs):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    state = {"server": None, "host": "127.0.0.1", "port": port}

    def _serve():
        time.sleep(delay_secs)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(8)
        state["server"] = srv
        try:
            while True:
                try:
                    client, _ = srv.accept()
                    client.close()
                except OSError:
                    return
        except Exception:
            return

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    try:
        deadline = time.time() + delay_secs + 0.5
        while time.time() < deadline and state["server"] is None:
            time.sleep(0.01)
        yield state["host"], state["port"]
    finally:
        if state["server"] is not None:
            with contextlib.suppress(OSError):
                state["server"].close()


class HealthCheckRetryTests(unittest.TestCase):

    def test_http_recovers_after_transient_failures(self):
        with start_mock_http_server(fail_count=2, fail_status=503) as (host, port):
            status, detail, code = health_check.check_http_service(
                host, port, "/health",
                timeout=2, retries=2, backoff_secs=0.05,
            )
        self.assertEqual(status, "OK", f"expected OK, got {status}: {detail}")
        self.assertEqual(code, 200)
        self.assertEqual(len(_FlakyHTTPHandler.request_log), 3)

    def test_http_exhausts_retries(self):
        with start_mock_http_server(always_status=503) as (host, port):
            status, detail, code = health_check.check_http_service(
                host, port, "/health",
                timeout=2, retries=1, backoff_secs=0.01,
            )
        self.assertEqual(status, "CRITICAL", f"expected CRITICAL, got {status}: {detail}")
        self.assertEqual(code, 503)
        self.assertEqual(len(_FlakyHTTPHandler.request_log), 2)

    def test_http_4xx_is_not_retried(self):
        with start_mock_http_server(always_status=404) as (host, port):
            status, detail, code = health_check.check_http_service(
                host, port, "/health",
                timeout=2, retries=5, backoff_secs=0.01,
            )
        self.assertEqual(status, "WARNING", f"expected WARNING, got {status}: {detail}")
        self.assertEqual(code, 404)
        self.assertEqual(len(_FlakyHTTPHandler.request_log), 1,
                         "4xx must not trigger retries")

    def test_http_5xx_eventually_recovers(self):
        with start_mock_http_server(fail_count=1, fail_status=502) as (host, port):
            status, detail, code = health_check.check_http_service(
                host, port, "/health",
                timeout=2, retries=2, backoff_secs=0.05,
            )
        self.assertEqual(status, "OK", f"expected OK, got {status}: {detail}")
        self.assertEqual(code, 200)
        self.assertEqual(len(_FlakyHTTPHandler.request_log), 2)

    def test_http_connection_refused_is_retried(self):
        status, detail, code = health_check.check_http_service(
            "127.0.0.1", 1, "/health",
            timeout=1, retries=1, backoff_secs=0.01,
        )
        self.assertEqual(status, "CRITICAL")
        detail_l = detail.lower()
        self.assertTrue(
            "refused" in detail_l or "timeout" in detail_l or "timed out" in detail_l,
            f"expected refused/timeout in detail, got: {detail!r}",
        )

    def test_tcp_recovers_after_delay(self):
        with start_delayed_tcp_server(delay_secs=0.2) as (host, port):
            status, detail, latency = health_check.check_tcp_port(
                host, port, timeout=1,
                retries=3, backoff_secs=0.1,
            )
        self.assertEqual(status, "OK", f"expected OK, got {status}: {detail}")
        self.assertGreater(latency, 0, f"expected latency > 0, got {latency}")

    def test_tcp_exhausts_retries(self):
        status, detail, latency = health_check.check_tcp_port(
            "127.0.0.1", 1,
            timeout=0.5, retries=0, backoff_secs=0.0,
        )
        self.assertEqual(status, "CRITICAL")
        self.assertEqual(latency, 0)

    def test_per_attempt_logging_emits_to_stderr(self):
        with start_mock_http_server(always_status=503) as (host, port):
            buf = io.StringIO()
            real_stderr = sys.stderr
            sys.stderr = buf
            try:
                health_check.check_http_service(
                    host, port, "/health",
                    timeout=2, retries=2, backoff_secs=0.01,
                )
            finally:
                sys.stderr = real_stderr
        log_output = buf.getvalue()
        self.assertIn("[health_check] attempt", log_output)
        self.assertGreaterEqual(log_output.count("failed after"), 2,
                                f"expected >=2 failure log lines, got: {log_output!r}")

    def test_json_output_contains_attempts(self):
        with start_mock_http_server(fail_count=1, fail_status=503) as (host, port):
            original_backend = dict(health_check.SERVICES["backend"])
            health_check.SERVICES["backend"] = {
                "host": host, "port": port, "path": "/health", "timeout": 2,
            }
            try:
                results = health_check.run_health_checks(
                    service="backend", json_output=True,
                    retries=2, timeout_secs=2, backoff_secs=0.05,
                )
            finally:
                health_check.SERVICES["backend"] = original_backend

        self.assertIn("attempts", results, "json_output=True must include 'attempts' key")
        attempts = results["attempts"]
        self.assertGreaterEqual(len(attempts), 1)
        for rec in attempts:
            for key in ("target", "category", "attempt", "max_attempts",
                        "elapsed_ms", "success", "failure_reason"):
                self.assertIn(key, rec, f"attempt record missing key {key}: {rec}")
        failed = [r for r in attempts if not r["success"]]
        self.assertGreaterEqual(len(failed), 1,
                                f"expected at least one failed attempt, got: {attempts}")


def _run_cli_smoke() -> int:
    cmd = [
        sys.executable,
        os.path.join(HERE, "health_check.py"),
        "--json", "--retries", "1", "--timeout-secs", "1", "--backoff-secs", "0.05",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode not in (0, 1):
        print("CLI smoke test failed:", proc.stderr, file=sys.stderr)
        return 1
    try:
        json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"CLI smoke test: invalid JSON: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    print("Running health-check retry tests (issue #193)...\n")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(HealthCheckRetryTests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        return 1
    print("\nRunning CLI smoke test...")
    rc = _run_cli_smoke()
    if rc != 0:
        return rc
    print("CLI smoke test OK.\n")
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
