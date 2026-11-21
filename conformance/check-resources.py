import hashlib
import http.server
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


RUNNER = Path(__file__).resolve().with_name("run.py")
spec = importlib.util.spec_from_file_location("portable_conformance", RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
observations = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class CountingPipe:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.bytes_read = 0
        self.largest_read = 0

    def read(self, size=-1):
        self.largest_read = max(self.largest_read, size)
        block = self.wrapped.read(size)
        self.bytes_read += len(block)
        return block

    def fileno(self):
        return self.wrapped.fileno()

    def close(self):
        self.wrapped.close()


def process_probe(script, mode, timeout, expected_failure=None):
    original_popen = subprocess.Popen
    processes = []

    def counted_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        process.stdout = CountingPipe(process.stdout)
        process.wait_calls = 0
        process.communicate_bytes = 0
        original_wait = process.wait
        original_communicate = process.communicate

        def counted_wait(*args, **kwargs):
            process.wait_calls += 1
            return original_wait(*args, **kwargs)

        def counted_communicate(*args, **kwargs):
            output, error = original_communicate(*args, **kwargs)
            process.communicate_bytes = max(process.communicate_bytes, len(output or b""))
            return output, error

        process.wait = counted_wait
        process.communicate = counted_communicate
        processes.append(process)
        return process

    subprocess.Popen = counted_popen
    runner.TIMEOUT_SECONDS = timeout
    started = time.monotonic()
    failure = None
    try:
        result = runner.ProcessDriver([sys.executable, "-u", str(script), mode, str(runner.MAX_RESPONSE_BYTES * 2)], "http://127.0.0.1:1").call(
            "fabricated-probe-credential", "whoami", {})
    except runner.CheckFailure as error:
        failure = str(error)
    finally:
        subprocess.Popen = original_popen
    elapsed = time.monotonic() - started
    check(len(processes) == 1, "Probe did not create exactly one driver process")
    process = processes[0]
    check(process.returncode is not None and process.wait_calls > 0, "Driver was not waited and reaped")
    captured_bytes = max(process.stdout.bytes_read, process.communicate_bytes)
    check(captured_bytes <= runner.MAX_RESPONSE_BYTES + 1, "Driver captured bytes beyond the safety bound")
    check(elapsed < timeout + 2.5, "Driver exceeded wall deadline plus cleanup allowance")
    if expected_failure:
        check(failure and expected_failure in failure, "Driver did not produce the expected content-free failure")
    else:
        check(failure is None, "Control driver failed")
        check(result.get("ok") is (mode == "success"), "Driver did not preserve normalized success/error status")
    observations.append({"case": "process-" + mode, "passed": True, "elapsedMs": round(elapsed * 1000),
                         "wallDeadlineMs": round(timeout * 1000), "capturedBytes": captured_bytes,
                         "captureLimitPlusSentinel": runner.MAX_RESPONSE_BYTES + 1,
                         "largestReadRequest": process.stdout.largest_read,
                         "waitCalls": process.wait_calls, "reaped": process.returncode is not None,
                         "forcedKill": os.name == "posix" and process.returncode == -signal.SIGKILL})


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            if self.path == "/slow-headers":
                for byte in b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\n{}":
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.04)
                return
            data = b"{}" + b" " * 8 if self.path == "/slow-body" else b'{"ok":true,"value":{}}'
            size = runner.MAX_RESPONSE_BYTES + 65536 if self.path == "/noisy" else len(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            if self.path == "/noisy":
                for unused in range(size // 65536 + 1):
                    self.wfile.write(b"x" * 65536)
                return
            if self.path == "/slow-body":
                for byte in data:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.05)
                return
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


def http_probe(origin, path, timeout, expected_failure=None):
    runner.TIMEOUT_SECONDS = timeout
    original_read = runner.http.client.HTTPResponse.read1
    counted = {"bytes": 0, "largest": 0}

    def read1(response, size=-1):
        counted["largest"] = max(counted["largest"], size)
        block = original_read(response, size)
        counted["bytes"] += len(block)
        return block

    runner.http.client.HTTPResponse.read1 = read1
    started = time.monotonic()
    failure = None
    try:
        result = runner.Wire(origin).request(path, token="fabricated-probe-credential", payload={})
    except runner.CheckFailure as error:
        failure = str(error)
    finally:
        runner.http.client.HTTPResponse.read1 = original_read
    elapsed = time.monotonic() - started
    check(counted["bytes"] <= runner.MAX_RESPONSE_BYTES + 1, "HTTP body exceeded the capture bound")
    check(elapsed < timeout + 0.75, "HTTP transfer exceeded its wall deadline allowance")
    if expected_failure:
        check(failure and expected_failure in failure, "HTTP fault did not produce the expected content-free failure")
    else:
        check(failure is None and result["body"] == {"ok": True, "value": {}}, "HTTP control failed")
    observations.append({"case": "http" + path, "passed": True, "elapsedMs": round(elapsed * 1000),
                         "wallDeadlineMs": round(timeout * 1000), "capturedBytes": counted["bytes"],
                         "captureLimitPlusSentinel": runner.MAX_RESPONSE_BYTES + 1,
                         "largestReadRequest": counted["largest"]})


with tempfile.TemporaryDirectory(prefix="cayapa-driver-probe-") as scratch:
    script = Path(scratch) / "driver.py"
    script.write_text('''import json, os, signal, sys, time
mode = sys.argv[1]
sys.stderr.write(os.environ.get("CAYAPA_TOKEN", ""))
sys.stderr.flush()
if mode == "noisy":
    for unused in range(int(sys.argv[2]) // 65536):
        sys.stdout.buffer.write(b"x" * 65536)
        sys.stdout.buffer.flush()
    sys.exit(0)
if mode == "stalled":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(30)
request = json.load(sys.stdin)
if mode == "success":
    print(json.dumps({"ok": True, "value": {"readInput": request["operation"] == "whoami"}}))
else:
    print(json.dumps({"ok": False, "error": {"code": "unauthorized", "message": "Fixture refusal", "retryable": False}}))
    sys.exit(1)
''', encoding="utf-8")
    process_probe(script, "success", 5)
    process_probe(script, "operator-error", 5)
    process_probe(script, "noisy", 5, "safety guard")
    process_probe(script, "stalled", 0.2, "wall deadline")
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
server.daemon_threads = True
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
try:
    origin = "http://127.0.0.1:" + str(server.server_port)
    http_probe(origin, "/normal", 5)
    http_probe(origin, "/noisy", 5, "safety guard")
    http_probe(origin, "/slow-body", 0.18, "wall deadline")
    http_probe(origin, "/slow-headers", 0.18, "wall deadline")
finally:
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=1)
report = {"reportFormat": "cayapa-resource-regression-1", "passed": len(observations), "runnerSha256": hashlib.sha256(RUNNER.read_bytes()).hexdigest(), "probes": observations,
          "containsCredentialsOrResponseBodies": False, "operatorRequestsMade": False}
print(json.dumps(report, indent=2))
