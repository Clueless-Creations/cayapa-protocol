import contextlib
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import run_direct as runner


FIXTURE = '''import json, os, signal, subprocess, sys, time
from pathlib import Path

mode, marker = sys.argv[1:3]
marker = Path(marker)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
if mode == "child":
    marker.write_text(str(os.getpid()))
    time.sleep(20)
    raise SystemExit(0)
child = subprocess.Popen([sys.executable, __file__, "child", str(marker)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
deadline = time.monotonic() + 3
while not marker.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
if not marker.exists():
    child.kill()
    child.wait(timeout=1)
    raise SystemExit(2)
if mode == "capture-success":
    request = json.load(sys.stdin)
    print(json.dumps({"observedInput": request == {"fixture": "resource-probe"}}), flush=True)
elif mode == "capture-oversized":
    for unused in range(int(sys.argv[3]) // 65536 + 1):
        sys.stdout.buffer.write(b"x" * 65536)
        sys.stdout.buffer.flush()
elif mode == "capture-stalled":
    time.sleep(20)
elif mode == "server-ready":
    print('{"ready":true}', flush=True)
    time.sleep(20)
elif mode == "server-invalid-ready":
    print('{"ready":false}', flush=True)
    time.sleep(20)
else:
    raise SystemExit(2)
'''


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def process_running(pid):
    if Path("/proc").is_dir():
        try:
            stat = Path("/proc") / str(pid) / "stat"
            state = stat.read_text().rsplit(")", 1)[1].split()[0]
            return state not in {"Z", "X"}
        except FileNotFoundError:
            return False
    result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=2, check=False)
    state = result.stdout.decode("ascii", errors="replace").strip()
    return bool(state) and state[0] not in {"Z", "X"}


def descendant_stopped(marker):
    require(marker.is_file(), "Finite descendant fixture never became ready")
    pid = int(marker.read_text())
    deadline = time.monotonic() + 1
    while process_running(pid) and time.monotonic() < deadline:
        time.sleep(0.01)
    require(not process_running(pid), "Adapter descendant remained running after process-group cleanup")


class CountingPipe:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.bytes_read = 0
        self.largest_request = 0

    def read(self, size=-1):
        self.largest_request = max(self.largest_request, size)
        value = self.wrapped.read(size)
        self.bytes_read += len(value)
        return value

    def readline(self, size=-1):
        self.largest_request = max(self.largest_request, size)
        value = self.wrapped.readline(size)
        self.bytes_read += len(value)
        return value

    def close(self):
        self.wrapped.close()


@contextlib.contextmanager
def observed_processes():
    original = subprocess.Popen
    processes = []

    def observed(*args, **kwargs):
        process = original(*args, **kwargs)
        process.stdout = CountingPipe(process.stdout)
        process.wait_calls = 0
        process.separate_session = kwargs.get("start_new_session") is True
        wait = process.wait

        def observed_wait(*args, **kwargs):
            process.wait_calls += 1
            return wait(*args, **kwargs)

        process.wait = observed_wait
        processes.append(process)
        return process

    subprocess.Popen = observed
    try:
        yield processes
    finally:
        subprocess.Popen = original


def emergency_cleanup(processes, marker):
    for process in processes:
        if process.separate_session:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
    if marker.is_file():
        pid = int(marker.read_text())
        if process_running(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def observed_exit(processes, limit):
    require(len(processes) == 1, "Probe did not start exactly one immediate adapter")
    process = processes[0]
    require(process.separate_session, "Adapter was not isolated in a POSIX process session")
    require(process.returncode is not None and process.wait_calls > 0, "Immediate adapter was not waited and reaped")
    require(process.stdout.bytes_read <= limit, "Adapter capture exceeded its bounded sentinel allowance")
    return {"isolatedSession": process.separate_session, "immediateProcessReaped": True,
            "descendantStopped": True, "capturedBytes": process.stdout.bytes_read,
            "captureLimitPlusSentinel": limit, "largestReadRequest": process.stdout.largest_request,
            "forcedKill": process.returncode == -signal.SIGKILL}


def capture_probe(script, directory, mode, expected_failure=None):
    marker = directory / (mode + "-child")
    original_timeout = runner.PROCESS_TIMEOUT
    runner.PROCESS_TIMEOUT = 4
    processes = []
    failure = None
    result = None
    started = time.monotonic()
    try:
        with observed_processes() as processes:
            try:
                result = runner.capture([sys.executable, "-u", str(script), mode, str(marker),
                                         str(runner.PROCESS_OUTPUT_LIMIT * 2)], {"fixture": "resource-probe"})
            except runner.CheckFailure as error:
                failure = str(error)
        elapsed = time.monotonic() - started
        require(elapsed < runner.PROCESS_TIMEOUT + 3, "Adapter exceeded the wall deadline and cleanup allowance")
        if expected_failure:
            require(failure is not None and expected_failure in failure, "Adapter did not return the expected content-free failure")
        else:
            require(failure is None and result == ({"observedInput": True}, 0), "Successful adapter result or supplied input changed")
        descendant_stopped(marker)
        return {"case": mode, "elapsedMs": round(elapsed * 1000),
                "wallDeadlineMs": runner.PROCESS_TIMEOUT * 1000,
                **observed_exit(processes, runner.PROCESS_OUTPUT_LIMIT + 1)}
    finally:
        runner.PROCESS_TIMEOUT = original_timeout
        emergency_cleanup(processes, marker)


def server_probe(script, directory, mode):
    marker = directory / (mode + "-child")
    fixture = directory / mode
    fixture.mkdir(mode=0o700)
    certificates = runner.Certificates(fixture)
    owner = runner.Identity(fixture, "owner")
    peer = runner.Identity(fixture, "peer")
    operator = runner.Operator([sys.executable, "-u", str(script), mode, str(marker)], fixture,
                               "operator", owner, peer, certificates)
    processes = []
    failure = None
    started = time.monotonic()
    try:
        with observed_processes() as processes:
            try:
                operator.start()
            except runner.CheckFailure as error:
                failure = str(error)
            if mode == "server-ready":
                require(failure is None and process_running(int(marker.read_text())), "Ready-server descendant fixture was not alive before stop")
                operator.stop()
            else:
                require(failure is not None and "did not become ready" in failure, "Invalid readiness did not fail with content-free startup error")
        elapsed = time.monotonic() - started
        require(elapsed < 6, "Server lifecycle exceeded bounded fixture and cleanup allowance")
        descendant_stopped(marker)
        require(operator.process is None, "Stopped server retained a live process handle")
        return {"case": mode, "elapsedMs": round(elapsed * 1000), **observed_exit(processes, 1025)}
    finally:
        try:
            operator.stop()
        finally:
            emergency_cleanup(processes, marker)


def main():
    require(os.name == "posix", "Direct resource probes require POSIX process groups")
    probes = []
    with tempfile.TemporaryDirectory(prefix="cayapa-direct-resources-") as temporary:
        directory = Path(temporary)
        script = directory / "finite-adapter.py"
        runner.private_file(script, FIXTURE.encode("utf-8"))
        operations = [
            ("capture-success", lambda: capture_probe(script, directory, "capture-success")),
            ("capture-oversized", lambda: capture_probe(script, directory, "capture-oversized", "capture bound")),
            ("capture-stalled", lambda: capture_probe(script, directory, "capture-stalled", "wall deadline")),
            ("server-ready", lambda: server_probe(script, directory, "server-ready")),
            ("server-invalid-ready", lambda: server_probe(script, directory, "server-invalid-ready")),
        ]
        for name, operation in operations:
            try:
                result = operation()
                probes.append({**result, "passed": True})
            except Exception as error:
                reason = str(error) if isinstance(error, AssertionError) else "Resource probe raised " + type(error).__name__ + "; details withheld"
                probes.append({"case": name, "passed": False, "reason": reason})
    passed = sum(probe["passed"] for probe in probes)
    report = {"reportFormat": "cayapa-direct-resource-regression-1", "status": "passed" if passed == len(probes) else "failed",
              "passed": passed, "failed": len(probes) - passed, "skipped": 0,
              "runnerSha256": hashlib.sha256(Path(runner.__file__).read_bytes()).hexdigest(),
              "probes": probes, "containsCredentialsOrResponseBodies": False,
              "operatorRequestsMade": False, "descendantLiveness": "Absent or exited zombie is stopped; zombies are reaped by their adopting parent"}
    print(json.dumps(report, indent=2))
    return 0 if passed == len(probes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
