import argparse
import concurrent.futures
import copy
import json
import os
import platform
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import run_direct as wire
from run import CheckFailure, require


ROOT = Path(__file__).resolve().parent.parent
SESSION_FIELDS = {"actor", "owner", "keyId", "publicKey", "revision", "state"}
ADDRESS = re.compile(r"urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


class SessionAdapter:
    def __init__(self, command, directory, label, identity, limits=None):
        self.command = command
        self.directory = directory / label
        self.directory.mkdir(mode=0o700)
        self.identity = identity
        self.label = label
        self.config = {
            "owner": {"id": identity.owner, "keyId": identity.owner_id, "publicKeyFile": str(identity.public_file)},
            "statePath": str(self.directory / "state"),
            "limits": limits or {"sessions": 64, "intents": 8, "requests": 256},
            "testMode": True, "faultFile": str(self.directory / "fault.json"),
        }
        self.config_file = self.directory / "config.json"
        wire.private_file(self.config_file, wire.packed(self.config))
        self.primary = None
        self.life = None
        self.forked = None
        self.loss_armed = False

    def key(self, label):
        key = wire.ed25519.Ed25519PrivateKey.generate()
        path = self.directory / (label + ".pem")
        wire.save_key(key, path)
        return {"key": key, "file": path, "id": "urn:uuid:" + secrets.token_hex(16) + "#key"}

    def invoke(self, value, raw=None):
        command = self.command + ["--config", str(self.config_file)]
        if raw is not None:
            path = self.directory / ("input-" + secrets.token_hex(8))
            wire.private_file(path, raw)
            command = [sys.executable, "-c", "import os,sys; f=open(sys.argv[1],'rb'); os.dup2(f.fileno(),0); os.execvp(sys.argv[2],sys.argv[2:])", str(path)] + command
        try:
            if self.loss_armed:
                self.lost_result(command, value)
                return {"outcome": "unknown", "code": "storage"}
            result, status = wire.capture(command, None if raw is not None else value)
        finally:
            self.loss_armed = False
            if raw is not None:
                path.unlink(missing_ok=True)
        expected = 1 if result.get("outcome") == "rejected" else 2 if result.get("outcome") == "unknown" else 0
        require(status == expected, "Session adapter exit status disagrees with its outcome")
        return result

    def lost_result(self, command, value):
        environment = {name: os.environ[name] for name in ("PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL", "PYTHONUTF8") if name in os.environ}
        with tempfile.TemporaryFile() as source:
            source.write(wire.packed(value))
            source.seek(0)
            process = subprocess.Popen(command, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment, bufsize=0, start_new_session=True)
            finished = threading.Event()
            observed = {"byte": None}

            def read_one():
                try:
                    observed["byte"] = process.stdout.read(1)
                finally:
                    finished.set()

            reader = threading.Thread(target=read_one, daemon=True)
            reader.start()
            deadline = time.monotonic() + 15
            try:
                require(finished.wait(max(0, deadline - time.monotonic())), "After-commit fault exceeded its output deadline")
                require(observed["byte"] == b"", "After-commit fault returned an outcome instead of losing its result")
                try:
                    status = process.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    raise CheckFailure("After-commit fault exceeded its exit deadline") from None
                require(status == 2, "After-commit fault did not report process-level uncertainty")
            finally:
                wire.stop_process(process)
                process.stdout.close()
                reader.join(timeout=1)

    def call(self, value):
        return self.invoke(value)

    def contended(self, value):
        for attempt in range(5):
            result = self.invoke(value)
            if result != {"outcome": "unknown", "code": "storage"}:
                return result
            time.sleep(0.05 * (attempt + 1))
        raise CheckFailure("Session controller remained busy after bounded retries")

    def administration(self, op, **values):
        return {"op": op, "requestId": secrets.token_hex(12), "ownerPrivateKeyFile": str(self.identity.owner_file), **values}

    def creation(self, ref, key):
        return self.administration("new", sessionRef=ref, actorKeyId=key["id"], actorPrivateKeyFile=str(key["file"]))

    def access(self, op, ref, session, key, **values):
        return {"op": op, "sessionRef": ref, "expectedRevision": session["revision"], "actorPrivateKeyFile": str(key["file"]), **values}

    def session(self, result, outcome, key=None):
        require(result.get("outcome") == outcome, "Session operation did not return the required outcome")
        value = result.get("session")
        require(isinstance(value, dict) and set(value) == SESSION_FIELDS, "Session descriptor does not match the portable fixture")
        require(isinstance(value["actor"], str) and ADDRESS.fullmatch(value["actor"]) is not None, "New session address is not an opaque UUID actor URI")
        require(value["owner"] == self.identity.owner, "Session accountable owner changed")
        require(type(value["revision"]) is int and value["revision"] > 0 and value["state"] in ("active", "retired"), "Session lifecycle metadata is invalid")
        if key is not None:
            require(value["keyId"] == key["id"] and value["publicKey"] == wire.url64(wire.public_bytes(key["key"])), "Session actor key binding changed")
        return value

    def fault(self):
        wire.private_file(Path(self.config["faultFile"]), wire.packed({"operation": "session", "phase": "after-commit"}))
        self.loss_armed = True


class SessionHarness:
    def __init__(self, left_session, right_session, left_wire, right_wire, directory):
        self.directory = directory
        self.cases = []
        self.adapters = []
        self.wire_commands = [left_wire, right_wire]
        self.wire_harness = None
        for label, command in (("left", left_session), ("right", right_session)):
            identity = wire.Identity(directory, label)
            self.adapters.append(SessionAdapter(command, directory, label, identity))

    def case(self, lane, name, requirements, operation):
        started = time.monotonic()
        try:
            operation()
            result = {"lane": lane, "name": name, "requirements": requirements, "status": "passed"}
        except CheckFailure as error:
            result = {"lane": lane, "name": name, "requirements": requirements, "status": "failed", "reason": str(error)}
        except Exception as error:
            result = {"lane": lane, "name": name, "requirements": requirements, "status": "failed", "reason": "Session harness or adapter raised " + type(error).__name__ + "; details withheld"}
        result["durationMs"] = round((time.monotonic() - started) * 1000)
        self.cases.append(result)
        print(json.dumps(result), flush=True)

    def refused(self, result, code, outcome="rejected"):
        require(result == {"outcome": outcome, "code": code}, "Session refusal disagrees with its declared boundary")

    def event(self, adapter, session, message_id=None, **changes):
        value = {
            "specversion": "1.0", "type": "dev.cayapa.message", "source": session["actor"],
            "id": message_id or secrets.token_hex(12), "datacontenttype": "application/octet-stream", "data_base64": wire.b64(b"fabricated opaque payload"),
            "cayapaowner": adapter.identity.owner, "cayapato": "urn:uuid:" + secrets.token_hex(16),
            "cayapaprofile": "direct/0.3", "cayapaexpires": wire.utc(int(time.time()) + 1800),
        }
        value.update(changes)
        return wire.packed(value)

    def create(self, adapter):
        key = {"key": adapter.identity.actor_key, "file": adapter.identity.actor_file, "id": adapter.identity.actor_id}
        request = adapter.creation("primary", key)
        result = adapter.call(request)
        session = adapter.session(result, "created", key)
        require(result.get("duplicate") is False and session["revision"] == 1 and session["state"] == "active", "New identity was not committed once as active")
        adapter.primary = {"session": session, "key": key, "request": request}
        adapter.identity.actor = session["actor"]
        life_key = adapter.key("life")
        life_request = adapter.creation("life", life_key)
        life = adapter.session(adapter.call(life_request), "created", life_key)
        require(session["actor"] != life["actor"] and session["publicKey"] != life["publicKey"], "Same-owner new sessions shared an address or actor key")
        adapter.life = {"session": life, "key": life_key, "request": life_request}

    def mutation_recovery(self, adapter):
        key = adapter.key("lost-create")
        request = adapter.creation("lost-create", key)
        adapter.fault()
        self.refused(adapter.call(request), "storage", "unknown")
        recovered = adapter.call(request)
        session = adapter.session(recovered, "created", key)
        require(recovered.get("duplicate") is True, "Lost creation result allocated a new binding")
        require(adapter.session(adapter.call(adapter.access("resume", "lost-create", session, key)), "resumed", key) == session, "Recovered creation differs from retained identity")
        changed = dict(request, sessionRef="changed-intent")
        self.refused(adapter.call(changed), "conflict")
        self.refused(adapter.call(dict(request, requestId=secrets.token_hex(12))), "conflict")

    def concurrent_creation(self, adapter):
        keys = [adapter.key("parallel-" + str(i)) for i in range(2)]
        requests = [adapter.creation("parallel-" + str(i), key) for i, key in enumerate(keys)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(adapter.contended, requests))
        sessions = [adapter.session(result, "created", key) for result, key in zip(results, keys)]
        require(sessions[0]["actor"] != sessions[1]["actor"], "Concurrent new sessions collapsed into one address")
        for request, session in zip(requests, sessions):
            result = adapter.call(request)
            require(result.get("duplicate") is True and result.get("session") == session, "Concurrent creation was not retained idempotently")

    def resume(self, adapter):
        primary = adapter.primary
        request = adapter.access("resume", "primary", primary["session"], primary["key"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(adapter.contended, [request, request]))
        for result in results:
            require(adapter.session(result, "resumed", primary["key"]) == primary["session"], "A separate connection reset the logical session")

    def continuity_refusal(self, adapter):
        primary = adapter.primary
        request = adapter.access("resume", "primary", primary["session"], primary["key"])
        self.refused(adapter.call(dict(request, sessionRef="copied-title")), "not_found")
        wrong = adapter.key("wrong-control")
        self.refused(adapter.call(dict(request, actorPrivateKeyFile=str(wrong["file"]))), "unauthorized")
        self.refused(adapter.call(dict(request, actorPrivateKeyFile=str(adapter.directory / "absent-key.pem"))), "unauthorized")
        missing = SessionAdapter(adapter.command, self.directory, adapter.label + "-missing", adapter.identity)
        self.refused(missing.call(request), "continuity", "unknown")
        wire.private_file(Path(missing.config["statePath"]), wire.packed(primary["session"]))
        self.refused(missing.call(request), "continuity", "unknown")

    def owner_isolation(self, adapter):
        wrong = adapter.key("wrong-owner")
        key = adapter.key("owner-test-actor")
        request = adapter.creation("wrong-owner", key)
        self.refused(adapter.call(dict(request, ownerPrivateKeyFile=str(wrong["file"]))), "unauthorized")
        self.refused(adapter.call(adapter.creation("reused-actor", adapter.primary["key"])), "conflict")
        owner_key = {"key": adapter.identity.owner_key, "file": adapter.identity.owner_file, "id": adapter.identity.owner_id}
        self.refused(adapter.call(adapter.creation("owner-as-actor", owner_key)), "unauthorized")
        request = adapter.access("resume", "primary", adapter.primary["session"], adapter.primary["key"])
        original = dict(adapter.config)
        adapter.config["owner"] = dict(original["owner"], id="urn:uuid:" + secrets.token_hex(16))
        wire.private_file(adapter.config_file, wire.packed(adapter.config))
        try:
            self.refused(adapter.call(request), "continuity", "unknown")
        finally:
            adapter.config = original
            wire.private_file(adapter.config_file, wire.packed(adapter.config))

    def prepare(self, adapter):
        life = adapter.life
        body = self.event(adapter, life["session"], cayapaexpires=wire.utc(int(time.time()) - 1))
        request = adapter.access("prepare", "life", life["session"], life["key"], bodyBase64=wire.b64(body))
        first = adapter.call(request)
        require(first == {"outcome": "prepared", "duplicate": False, "id": json.loads(body)["id"]}, "Staged intent did not retain its message identity")
        require(adapter.call(request) == dict(first, duplicate=True), "Exact staging retry was not idempotent")
        changed = json.loads(body)
        changed["cayapaexpires"] = wire.utc(int(time.time()) + 1800)
        self.refused(adapter.call(dict(request, bodyBase64=wire.b64(wire.packed(changed)))), "conflict")
        wrong = dict(changed, id=secrets.token_hex(12), source=adapter.primary["session"]["actor"])
        self.refused(adapter.call(dict(request, bodyBase64=wire.b64(wire.packed(wrong)))), "unauthorized")
        pending = adapter.call(adapter.access("pending", "life", life["session"], life["key"]))
        require(pending == {"outcome": "pending", "messages": [{"id": json.loads(body)["id"], "bodyBase64": wire.b64(body)}]}, "Staged bytes were changed or reclaimed after expiry")
        primary = adapter.primary
        require(adapter.call(adapter.access("pending", "primary", primary["session"], primary["key"])) == {"outcome": "pending", "messages": []}, "Another session inherited outgoing intents")
        life["body"] = body

    def fork(self, adapter):
        life = adapter.life
        key = adapter.key("fork")
        request = adapter.administration("fork", sourceRef="life", sessionRef="fork", expectedRevision=life["session"]["revision"], actorKeyId=key["id"], actorPrivateKeyFile=str(key["file"]))
        result = adapter.call(request)
        session = adapter.session(result, "forked", key)
        require(session["actor"] != life["session"]["actor"], "Fork reused its source address")
        require(adapter.call(adapter.access("pending", "fork", session, key)) == {"outcome": "pending", "messages": []}, "Fork inherited source intent or receipt state")
        self.refused(adapter.call(dict(request, requestId=secrets.token_hex(12), sessionRef="stale-fork", expectedRevision=99)), "conflict")
        require(adapter.session(adapter.call(adapter.access("resume", "life", life["session"], life["key"])), "resumed") == life["session"], "Fork changed its source identity")
        adapter.forked = {"session": session, "key": key}

    def rotation(self, adapter):
        life = adapter.life
        before = dict(life["session"])
        old_key = life["key"]
        key = adapter.key("life-rotated")
        request = adapter.administration("rotate", sessionRef="life", expectedRevision=before["revision"], actorKeyId=key["id"], actorPrivateKeyFile=str(key["file"]))
        adapter.fault()
        self.refused(adapter.call(request), "storage", "unknown")
        result = adapter.call(request)
        current = adapter.session(result, "rotated", key)
        require(result.get("duplicate") is True and current["actor"] == before["actor"] and current["revision"] == before["revision"] + 1, "Rotation retry changed identity or repeated mutation")
        self.refused(adapter.call(adapter.access("resume", "life", before, key)), "conflict")
        self.refused(adapter.call(adapter.access("resume", "life", current, old_key)), "unauthorized")
        require(adapter.call(adapter.access("pending", "life", current, key))["messages"][0]["bodyBase64"] == wire.b64(life["body"]), "Rotation reset outgoing uncertainty")
        life.update(session=current, key=key, old_key=old_key)

    def retirement(self, adapter):
        life = adapter.life
        request = adapter.administration("retire", sessionRef="life", expectedRevision=life["session"]["revision"])
        adapter.fault()
        self.refused(adapter.call(request), "storage", "unknown")
        result = adapter.call(request)
        current = adapter.session(result, "retired", life["key"])
        require(result.get("duplicate") is True and current["state"] == "retired" and current["revision"] == life["session"]["revision"] + 1, "Retirement was not terminal and idempotent")
        self.refused(adapter.call(adapter.access("resume", "life", current, life["key"])), "retired")
        self.refused(adapter.call(adapter.access("prepare", "life", current, life["key"], bodyBase64=wire.b64(life["body"]))), "retired")
        require(adapter.call(adapter.access("pending", "life", current, life["key"]))["messages"][0]["bodyBase64"] == wire.b64(life["body"]), "Retirement discarded uncertain intent evidence")
        prior = adapter.call(life["request"])
        require(prior.get("duplicate") is True and prior.get("session") == current, "A creation retry resurrected a retired binding")
        self.refused(adapter.call(adapter.creation("reuse-retired-key", life["old_key"])), "conflict")
        self.refused(adapter.call(adapter.creation("life", adapter.key("rebind-retired"))), "conflict")
        life["session"] = current

    def capacity(self, adapter):
        for kind in ("sessions", "intents", "requests"):
            limits = {"sessions": 64, "intents": 8, "requests": 256}
            limits[kind] = 1
            bounded = SessionAdapter(adapter.command, self.directory, adapter.label + "-capacity-" + kind, adapter.identity, limits)
            key = bounded.key("first")
            request = bounded.creation("first", key)
            session = bounded.session(bounded.call(request), "created", key)
            if kind == "intents":
                body = self.event(bounded, session)
                prepare = bounded.access("prepare", "first", session, key, bodyBase64=wire.b64(body))
                require(bounded.call(prepare).get("outcome") == "prepared", "First bounded intent was refused")
                self.refused(bounded.call(dict(prepare, bodyBase64=wire.b64(self.event(bounded, session)))), "capacity")
                require(bounded.call(prepare).get("duplicate") is True, "Full intent capacity blocked an exact retry")
                require(bounded.call(bounded.access("pending", "first", session, key))["messages"][0]["bodyBase64"] == wire.b64(body), "Capacity refusal evicted an existing intent")
            else:
                self.refused(bounded.call(bounded.creation("second", bounded.key("second"))), "capacity")
            require(bounded.call(request).get("duplicate") is True, "Full controller capacity blocked mutation reconciliation")

    def strict_inputs(self, adapter):
        primary = adapter.primary
        request = adapter.access("resume", "primary", primary["session"], primary["key"])
        for value in (dict(request, unexpected=True), dict(request, expectedRevision=True), dict(request, expectedRevision=0), dict(request, op="enroll")):
            self.refused(adapter.call(value), "invalid")
        raw = wire.packed(request)
        self.refused(adapter.invoke(None, raw=b'{"op":"new",' + raw[1:]), "invalid")
        self.refused(adapter.invoke(None, raw=b"\xef\xbb\xbf" + raw), "invalid")
        self.refused(adapter.invoke(None, raw=b" " * 196609), "invalid")

    def local(self, adapter):
        cases = [
            ("distinct-new-same-owner-sessions", ["SI-1", "SI-3"], self.create),
            ("lost-creation-result-and-intent-conflict", ["SI-1", "SI-2"], self.mutation_recovery),
            ("concurrent-new-sessions", ["SI-1"], self.concurrent_creation),
            ("separate-process-and-concurrent-resume", ["SI-2"], self.resume),
            ("missing-copied-descriptor-and-wrong-control", ["SI-2", "SI-3"], self.continuity_refusal),
            ("owner-key-and-session-isolation", ["SI-1", "SI-3", "SI-4"], self.owner_isolation),
            ("exact-intent-retention-without-authority-renewal", ["SI-2", "SI-4", "SI-5"], self.prepare),
            ("explicit-fork-without-inherited-state", ["SI-1", "SI-4"], self.fork),
            ("authorized-rotation-and-stale-control-refusal", ["SI-2", "SI-3", "SI-5"], self.rotation),
            ("terminal-retirement-retains-uncertainty", ["SI-1", "SI-2", "SI-5"], self.retirement),
            ("bounded-state-refuses-without-eviction", ["SI-2", "SI-5"], self.capacity),
            ("closed-bounded-control-input", ["SI-3", "SI-4"], self.strict_inputs),
        ]
        for name, requirements, operation in cases:
            self.case(adapter.label, name, requirements, lambda operation=operation: operation(adapter))

    def connect_wire(self):
        harness = wire.Harness.__new__(wire.Harness)
        harness.directory = self.directory
        harness.certificates = wire.Certificates(self.directory)
        harness.context = wire.ssl.create_default_context(cafile=str(harness.certificates.ca_file))
        harness.context.minimum_version = wire.ssl.TLSVersion.TLSv1_2
        harness.operators = []
        harness.extra = []
        harness.cases = []
        self.wire_harness = harness
        for index, adapter in enumerate(self.adapters):
            peer = self.adapters[1 - index]
            operator = wire.Operator(self.wire_commands[index], self.directory, adapter.label + "-wire", adapter.identity, peer.identity, harness.certificates)
            harness.operators.append(operator)
            operator.start()
        harness.left, harness.right = harness.operators

    def native_refusal(self, result, code):
        require(result.get("outcome") == "rejected" and result.get("code") == code, "Native delivery did not enforce the expected current authority")

    def authority(self, index):
        harness = self.wire_harness
        sender, receiver = harness.operators[index], harness.operators[1 - index]
        adapter = self.adapters[index]
        forked = adapter.forked
        identity = copy.copy(adapter.identity)
        identity.actor = forked["session"]["actor"]
        identity.actor_key = forked["key"]["key"]
        identity.actor_id = forked["key"]["id"]
        body = harness.event(sender, receiver, source=identity.actor)
        token = identity.token(receiver.identity.actor)
        result = harness.native(sender, receiver, body, token, key_id=identity.actor_id, key_file=forked["key"]["file"])
        self.native_refusal(result, "not_admitted")
        harness.custody(receiver, body, 0)
        own_body = harness.event(sender, sender, source=identity.actor)
        own_result = harness.native(sender, sender, own_body, identity.token(sender.identity.actor), key_id=identity.actor_id, key_file=forked["key"]["file"])
        self.native_refusal(own_result, "not_admitted")
        harness.custody(sender, own_body, 0)

    def invalid_delegation(self, index):
        harness = self.wire_harness
        sender, receiver = harness.operators[index], harness.operators[1 - index]
        body = harness.event(sender, receiver)
        forged = sender.identity.token(receiver.identity.actor, signing_key=receiver.identity.owner_key)
        self.native_refusal(harness.native(sender, receiver, body, forged), "unauthorized")
        wrong = sender.identity.token(sender.identity.actor)
        self.native_refusal(harness.native(sender, receiver, body, wrong), "unauthorized")
        other_body = harness.event(sender, receiver, source=self.adapters[index].forked["session"]["actor"])
        self.native_refusal(harness.native(sender, receiver, other_body), "unauthorized")
        harness.custody(receiver, body, 0)

    def expiry_and_resume(self, index):
        harness = self.wire_harness
        sender, receiver = harness.operators[index], harness.operators[1 - index]
        adapter = self.adapters[index]
        primary = adapter.primary
        resumed = adapter.session(adapter.call(adapter.access("resume", "primary", primary["session"], primary["key"])), "resumed")
        require(resumed == primary["session"], "Short-lived delegation expiry changed session identity")
        now = int(time.time())
        claims = sender.identity.claims(receiver.identity.actor, iat=now - 120, nbf=now - 120, exp=now - 1)
        body = harness.event(sender, receiver)
        self.native_refusal(harness.native(sender, receiver, body, sender.identity.token(receiver.identity.actor, claims)), "unauthorized")
        harness.custody(receiver, body, 0)
        harness.accepted(harness.native(sender, receiver, body), body)
        harness.custody(receiver, body)

    def unknown_retry_and_rotation(self, index):
        harness = self.wire_harness
        sender, receiver = harness.operators[index], harness.operators[1 - index]
        adapter = self.adapters[index]
        primary = adapter.primary
        body = harness.event(sender, receiver)
        prepared = adapter.call(adapter.access("prepare", "primary", primary["session"], primary["key"], bodyBase64=wire.b64(body)))
        require(prepared.get("outcome") == "prepared", "Outgoing intent was not durably staged before send")
        token = harness.token(sender, receiver)
        receiver.fault("message")
        require(harness.native(sender, receiver, body, token).get("outcome") == "unknown", "Lost wire result invented a delivery outcome")
        receiver.restart(crash=True)
        resumed = adapter.session(adapter.call(adapter.access("resume", "primary", primary["session"], primary["key"])), "resumed")
        require(resumed == primary["session"], "Resume after uncertain delivery replaced the actor")
        pending = adapter.call(adapter.access("pending", "primary", resumed, primary["key"]))
        require(pending["messages"] == [{"id": json.loads(body)["id"], "bodyBase64": wire.b64(body)}], "Resume lost the exact uncertain outgoing intent")
        first = harness.accepted(harness.native(sender, receiver, body, token), body, True)
        key = adapter.key("primary-rotated")
        request = adapter.administration("rotate", sessionRef="primary", expectedRevision=resumed["revision"], actorKeyId=key["id"], actorPrivateKeyFile=str(key["file"]))
        current = adapter.session(adapter.call(request), "rotated", key)
        require(current["actor"] == resumed["actor"], "Actor-key rotation changed the message namespace")
        adapter.identity.actor_key, adapter.identity.actor_id, adapter.identity.actor_file = key["key"], key["id"], key["file"]
        primary.update(session=current, key=key)
        second = harness.accepted(harness.native(sender, receiver, body), body, True)
        require(first == second, "Renewed actor authority changed the retained receipt")
        harness.custody(receiver, body)
        primary["wire_body"] = body

    def withdrawal(self, index):
        harness = self.wire_harness
        sender, receiver = harness.operators[index], harness.operators[1 - index]
        adapter = self.adapters[index]
        primary = adapter.primary
        body = primary["wire_body"]
        claims = sender.identity.claims(receiver.identity.actor)
        token = sender.identity.token(receiver.identity.actor, claims)
        control = wire.packed({"issuer": sender.identity.owner, "audience": receiver.identity.actor, "delegation_jti": claims["jti"], "request_id": secrets.token_hex(12)})
        harness.revoked(harness.native(sender, receiver, control, path=wire.DELEGATION_PATH, owner=True), control)
        receiver.restart(crash=True)
        require(adapter.session(adapter.call(adapter.access("resume", "primary", primary["session"], primary["key"])), "resumed") == primary["session"], "Remote withdrawal reset the retained local identity")
        self.native_refusal(harness.native(sender, receiver, body, token), "unauthorized")
        harness.accepted(harness.native(sender, receiver, body), body, True)
        admission = wire.packed({"issuer": receiver.identity.owner, "audience": receiver.identity.actor, "admission_id": receiver.admission_id, "request_id": secrets.token_hex(12)})
        harness.revoked(harness.native(receiver, receiver, admission, path=wire.ADMISSION_PATH, owner=True), admission)
        receiver.restart(crash=True)
        adapter.session(adapter.call(adapter.access("resume", "primary", primary["session"], primary["key"])), "resumed")
        self.native_refusal(harness.native(sender, receiver, body), "not_admitted")
        harness.custody(receiver, body)

    def run(self):
        for adapter in self.adapters:
            self.local(adapter)
        self.connect_wire()
        for index, lane in enumerate(("left-to-right", "right-to-left")):
            cases = [
                ("new-and-fork-identity-do-not-grant-admission", ["SI-3", "SI-4"], self.authority),
                ("forged-substituted-and-wrong-destination-proof", ["SI-3", "SI-4"], self.invalid_delegation),
                ("stable-resume-with-separate-delegation-renewal", ["SI-2", "SI-3", "SI-6"], self.expiry_and_resume),
                ("lost-wire-result-resume-rotation-exact-retry", ["SI-2", "SI-5", "SI-6"], self.unknown_retry_and_rotation),
                ("withdrawal-survives-receiver-restart-and-local-resume", ["SI-4", "SI-5"], self.withdrawal),
            ]
            for name, requirements, operation in cases:
                self.case(lane, name, requirements, lambda operation=operation: operation(index))

    def stop(self):
        if self.wire_harness is not None:
            self.wire_harness.stop()


def source_hashes():
    return wire.source_hashes() + [{"path": name, "sha256": wire.sha((ROOT / name).read_bytes())} for name in ("extensions/host-session-1.md", "proposals/session-identity.md", "conformance/session-fixture.md", "conformance/run_sessions.py")]


def main():
    parser = argparse.ArgumentParser(description="Portable host-session/1 lifecycle and existing Direct/0.3 interoperability proof.")
    for name in ("left-session", "right-session", "left-wire", "right-wire"):
        parser.add_argument("--" + name + "-command-json", required=True, type=wire.command)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("The fixture requires POSIX process cleanup; the protocol has no operating-system requirement")
    directory = args.work_dir.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(directory.iterdir()):
        parser.error("Use a new or empty private fixture directory")
    directory.chmod(0o700)
    commands = {name: getattr(args, name.replace("-", "_") + "_command_json") for name in ("left-session", "right-session", "left-wire", "right-wire")}
    initial = source_hashes()
    implementations = {name: wire.implementation_identity(command) for name, command in commands.items()}
    harness = None
    fatal = None
    started = time.monotonic()
    try:
        harness = SessionHarness(commands["left-session"], commands["right-session"], commands["left-wire"], commands["right-wire"], directory)
        harness.run()
    except CheckFailure as error:
        fatal = str(error)
    except Exception as error:
        fatal = "Session fixture initialization or orchestration raised " + type(error).__name__ + "; details withheld"
    finally:
        if harness is not None:
            harness.stop()
    if source_hashes() != initial or implementations != {name: wire.implementation_identity(command) for name, command in commands.items()}:
        fatal = "Published contract or implementation entry files changed during the run"
    cases = harness.cases if harness is not None else []
    failed = sum(case["status"] != "passed" for case in cases) + bool(fatal)
    report = {
        "format": "cayapa-host-session-conformance-1", "contract": "host-session/1", "coreVersion": "0.3", "profile": "direct/0.3",
        "status": "passed" if len(cases) == 34 and not failed else "failed", "generatedAt": wire.utc(int(time.time())),
        "runtime": {"python": platform.python_version(), "cryptography": wire.cryptography.__version__, "tls": wire.ssl.OPENSSL_VERSION},
        "implementations": implementations, "sourceHashes": initial,
        "fixture": {"transport": "verified HTTPS on loopback", "independentOwnerKeys": True, "independentActorKeys": True, "separateLifecycleStores": True,
                    "manualIntroduction": True, "nativeSendersBothDirections": True, "mcpRequired": False, "dnsDiscoveryRequired": False,
                    "deterministicLocalAndWireAfterCommitFaults": True, "productionDeployed": False, "actualModelHosts": False},
        "summary": {"passed": sum(case["status"] == "passed" for case in cases), "failed": failed, "skipped": 0, "durationMs": round((time.monotonic() - started) * 1000)},
        "limitations": ["Two project-isolated lifecycle implementations and existing wire operators; not independent external adoption", "Privileged local fixture controls are not a required native API or public enrollment service",
                        "Complete copies of all controlling state and keys are indistinguishable; no global fencing or rollback-resistant custody claim", "Local retirement or rotation is not receiver admission or delegation withdrawal",
                        "Custody is not a model read, wake, reply or action; no real host was activated", "No new Direct/0.3 envelope, capability or durable/0.2 wire behavior"],
        "cases": cases,
    }
    if fatal:
        report["fatal"] = fatal
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], **report["summary"]}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(143))
    raise SystemExit(main())
