import argparse
import base64
import datetime
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from pathlib import Path


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 35
HTTP_ERRORS = {
    "invalid": 400,
    "unauthorized": 401,
    "not_found": 404,
    "conflict": 409,
    "rate_limited": 429,
    "callback_endpoint": 502,
    "unavailable": 503,
    "internal": 500,
}
CORE_OPERATIONS = {
    "whoami", "list_conversations", "list_members", "send", "read",
    "inbox", "acknowledge", "retract",
}
METADATA_KEYS = {"pendingForYou", "deliveryForecast", "metadataUnavailable"}


class CheckFailure(Exception):
    pass


class ConfigurationFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailure(message)


def encoded(value, ascii_only=False):
    return json.dumps(value, ensure_ascii=ascii_only, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def valid_position(value):
    return type(value) is int and value >= 0


def safe_endpoint(value):
    if not isinstance(value, str):
        raise ConfigurationFailure("Fixture baseUrl must be an origin URL")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        raise ConfigurationFailure("Fixture baseUrl is not a valid origin URL") from None
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}
            or (parsed.scheme == "http" and not loopback)):
        raise ConfigurationFailure("Use an HTTPS origin or an isolated loopback HTTP origin")
    try:
        parsed.port
    except ValueError:
        raise ConfigurationFailure("Fixture baseUrl has an invalid port") from None
    return value.rstrip("/"), loopback


class Wire:
    def __init__(self, base_url):
        self.base_url = base_url

    def request(self, path, token=None, payload=None, raw=None, method="POST"):
        headers = {"Accept": "application/json, text/event-stream"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        data = raw if raw is not None else encoded(payload) if payload is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        endpoint = urllib.parse.urlsplit(self.base_url)
        connection_type = http.client.HTTPSConnection if endpoint.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(endpoint.hostname, endpoint.port, timeout=TIMEOUT_SECONDS)
        deadline = time.monotonic() + TIMEOUT_SECONDS
        expired = threading.Event()
        connected = {}
        response = None

        def remaining():
            value = deadline - time.monotonic()
            require(not expired.is_set() and value > 0, "HTTP transfer exceeded the harness wall deadline")
            return value

        def interrupt():
            expired.set()
            active = connected.get("socket") or connection.sock
            if active is not None:
                try:
                    active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    active.close()
                except OSError:
                    pass

        watchdog = threading.Timer(TIMEOUT_SECONDS, interrupt)
        watchdog.daemon = True
        watchdog.start()
        try:
            connection.connect()
            active = connection.sock
            connected["socket"] = active
            active.settimeout(remaining())
            connection.request(method, path, body=data, headers=headers)
            active.settimeout(remaining())
            response = connection.getresponse()
            status = response.status
            response_headers = response.headers
            require(not 300 <= status < 400, "Redirect refused to avoid forwarding a credential")
            body = bytearray()
            while len(body) <= MAX_RESPONSE_BYTES and not response.isclosed():
                active.settimeout(remaining())
                block = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - len(body)))
                if not block:
                    break
                body.extend(block)
            remaining()
        except (http.client.HTTPException, TimeoutError, OSError):
            if expired.is_set() or time.monotonic() >= deadline:
                raise CheckFailure("HTTP transfer exceeded the harness wall deadline") from None
            raise CheckFailure("Transport failed; credentials and response body are withheld") from None
        finally:
            watchdog.cancel()
            try:
                if response is not None:
                    response.close()
                connection.close()
            except OSError:
                pass
            watchdog.join(timeout=1)
        require(len(body) <= MAX_RESPONSE_BYTES, "Response exceeded the harness safety guard, not a protocol wire limit")
        if not body:
            value = None
        else:
            try:
                value = json.loads(body.decode("utf-8", errors="strict"))
            except (UnicodeError, ValueError):
                raise CheckFailure("Response was not valid UTF-8 JSON") from None
        return {"status": status, "headers": response_headers, "body": value, "bytes": len(body)}


class HttpDriver:
    name = "http"

    def __init__(self, wire):
        self.wire = wire

    def call(self, token, operation, arguments):
        response = self.wire.request("/v0/" + operation, token, arguments)
        result = response["body"]
        require(isinstance(result, dict) and type(result.get("ok")) is bool, "HTTP operation result shape is invalid")
        require("application/json" in response["headers"].get("Content-Type", ""), "HTTP result needs a JSON content type")
        require("no-store" in response["headers"].get("Cache-Control", ""), "HTTP result must disable caching")
        if result["ok"]:
            require(response["status"] == 200 and "value" in result, "HTTP success wrapper is invalid")
        else:
            error = result.get("error")
            require(isinstance(error, dict), "HTTP error wrapper is invalid")
            expected = HTTP_ERRORS.get(error.get("code"), 500)
            require(response["status"] == expected, "HTTP semantic error status does not match its code")
        return result


class McpDriver:
    name = "mcp"

    def __init__(self, wire):
        self.wire = wire
        self.next_id = 0

    def rpc(self, token, method, params=None, allow_auth_failure=False):
        self.next_id += 1
        request = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            request["params"] = params
        response = self.wire.request("/mcp", token, request)
        value = response["body"]
        if response["status"] == 401 and allow_auth_failure:
            return {"bindingUnauthorized": True}
        require(response["status"] == 200, "Expected a successful MCP transport response")
        require(isinstance(value, dict) and value.get("jsonrpc") == "2.0" and value.get("id") == self.next_id,
                "MCP JSON-RPC response does not match the request")
        return value

    def call(self, token, operation, arguments):
        rpc = self.rpc(token, "tools/call", {"name": operation, "arguments": arguments}, allow_auth_failure=True)
        if rpc.get("bindingUnauthorized") is True:
            return {"ok": False, "error": {"code": "unauthorized", "message": "Binding rejected authentication", "retryable": False}}
        require("error" not in rpc and isinstance(rpc.get("result"), dict), "MCP returned a binding error instead of a tool result")
        result = rpc["result"]
        require(type(result.get("isError")) is bool, "MCP tool result needs isError")
        content = result.get("content")
        require(isinstance(content, list) and content and isinstance(content[0], dict)
                and content[0].get("type") == "text", "MCP first content block must contain the operation JSON")
        try:
            value = json.loads(content[0]["text"])
        except (KeyError, TypeError, ValueError):
            raise CheckFailure("MCP first text block is not an operation JSON value") from None
        structured = result.get("structuredContent")
        require(isinstance(structured, dict), "MCP structuredContent is missing")
        core = {key: value for key, value in structured.items() if key not in METADATA_KEYS}
        expected = {"items": value} if isinstance(value, list) else value if isinstance(value, dict) else {"value": value}
        require(core == expected, "MCP structured and first-text values disagree")
        if result["isError"]:
            require(isinstance(value, dict) and isinstance(value.get("error"), dict), "MCP semantic failure is malformed")
            return {"ok": False, **value}
        return {"ok": True, "value": value}


class ProcessDriver:
    name = "external-client"

    def __init__(self, command, base_url):
        self.command = command
        self.base_url = base_url

    def capture(self, environment, request):
        deadline = time.monotonic() + TIMEOUT_SECONDS
        with tempfile.TemporaryFile() as input_file:
            input_file.write(request)
            input_file.seek(0)
            process = subprocess.Popen(self.command, stdin=input_file, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=environment, bufsize=0)
            output = bytearray()
            finished = threading.Event()
            cancelled = threading.Event()
            read_failed = threading.Event()

            def consume():
                try:
                    while len(output) <= MAX_RESPONSE_BYTES and not cancelled.is_set():
                        block = process.stdout.read(min(65536, MAX_RESPONSE_BYTES + 1 - len(output)))
                        if not block:
                            break
                        output.extend(block)
                except (OSError, ValueError):
                    read_failed.set()
                finally:
                    finished.set()

            reader = threading.Thread(target=consume, daemon=True)
            reader.start()
            try:
                require(finished.wait(max(0, deadline - time.monotonic())), "External client exceeded the harness wall deadline")
                require(not read_failed.is_set(), "External client output could not be read; response is withheld")
                require(len(output) <= MAX_RESPONSE_BYTES, "External client response exceeded the harness safety guard")
                process.wait(timeout=max(0, deadline - time.monotonic()))
                return output, process.returncode
            finally:
                cancelled.set()
                try:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=1)
                finally:
                    process.stdout.close()
                    reader.join(timeout=1)

    def call(self, token, operation, arguments):
        environment = {name: os.environ[name] for name in ("PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL", "PYTHONUTF8") if name in os.environ}
        environment.update({"CAYAPA_URL": self.base_url, "CAYAPA_TOKEN": token})
        try:
            output, returncode = self.capture(environment, encoded({"operation": operation, "arguments": arguments}))
        except (OSError, subprocess.TimeoutExpired):
            raise CheckFailure("External client could not complete; stderr is withheld") from None
        try:
            result = json.loads(output.decode("utf-8", errors="strict"))
        except (UnicodeError, ValueError):
            raise CheckFailure("External client did not return one normalized JSON result") from None
        require(isinstance(result, dict) and type(result.get("ok")) is bool, "External client result shape is invalid")
        require(returncode in ({0} if result["ok"] else {0, 1}), "External client exit status disagrees with its result")
        require("value" in result if result["ok"] else isinstance(result.get("error"), dict), "External client result is incomplete")
        return result


class Suite:
    def __init__(self, fixture, client_command):
        self.fixture = fixture
        self.base_url, self.loopback = safe_endpoint(fixture["baseUrl"])
        self.tokens = fixture["credentials"]
        self.conversations = fixture["conversations"]
        self.wire = Wire(self.base_url)
        self.http = HttpDriver(self.wire)
        self.mcp = McpDriver(self.wire) if "mcp" in fixture.get("bindings", ["http", "mcp"]) else None
        self.peer = self.mcp or self.http
        self.client = ProcessDriver(client_command, self.base_url) if client_command else None
        self.run_id = uuid.uuid4().hex
        self.counter = 0
        self.cases = []
        self.identities = {}
        self.records = {}

    def key(self):
        self.counter += 1
        return "conformance-" + self.run_id + "-" + str(self.counter)

    def call(self, driver, role, operation, arguments=None):
        return driver.call(self.tokens[role], operation, {} if arguments is None else arguments)

    def ok(self, driver, role, operation, arguments=None):
        result = self.call(driver, role, operation, arguments)
        require(result.get("ok") is True, "Expected successful " + operation + " operation")
        return result["value"]

    def error(self, driver, role, operation, arguments, code):
        result = self.call(driver, role, operation, arguments)
        require(result.get("ok") is False and result.get("error", {}).get("code") == code,
                "Expected " + code + " from " + operation)
        require(result["error"].get("retryable") is (code == "rate_limited"), "Semantic retryability is incorrect")
        return result

    def send(self, driver, role, body, conversation="main", key=None, **fields):
        arguments = {"conversation": self.conversations[conversation], "intentKey": key or self.key(), **body, **fields}
        value = self.ok(driver, role, "send", arguments)
        require(isinstance(value.get("id"), str) and valid_position(value.get("convSeq")) and value["convSeq"] > 0
                and value.get("status") == "stored" and value.get("duplicate") is False, "Fresh send acceptance is malformed or duplicated")
        return {"arguments": arguments, "value": value, "role": role}

    def page(self, driver, role, operation, arguments):
        value = self.ok(driver, role, operation, arguments)
        require(isinstance(value, dict) and isinstance(value.get("items"), list) and valid_position(value.get("next")), "Page shape is invalid")
        require(value.get("omitted") is None or value["omitted"] in ({"more": True, "reason": "limit"}, {"more": True, "reason": "bytes"}), "Page omission signal is invalid")
        require(len(value["items"]) <= 50, "Page exceeds the maximum contribution count")
        return value

    def record(self, driver, role, sent):
        page = self.page(driver, role, "read", {"conversation": sent["arguments"]["conversation"], "afterSeq": sent["value"]["convSeq"] - 1, "limit": 1})
        require(len(page["items"]) == 1 and page["items"][0].get("id") == sent["value"]["id"], "Read did not return the accepted contribution")
        require(page["next"] == sent["value"]["convSeq"], "Conversation cursor does not match the last contribution")
        return page["items"][0]

    def exact_body(self, item, body, author):
        require(item.get("text") == body.get("text") and item.get("content") == body.get("content"), "Body changed during storage or transfer")
        require(item.get("author", {}).get("id") == self.identities[author]["actor"]["id"], "Attribution does not match the authenticated actor")
        require(item.get("owner") == self.identities[author]["owner"], "Accountable owner changed during transfer")
        require(item.get("protocolVersion") == "0.2" and item.get("removed") is None, "New contribution version or lifecycle is incorrect")

    def drain(self, driver, role, operation, arguments=None):
        args = dict(arguments or {})
        cursor_key = "afterSeq" if operation == "read" else "after"
        cursor = args.get(cursor_key, 0)
        items = []
        seen = set()
        for unused in range(100):
            page = self.page(driver, role, operation, {**args, cursor_key: cursor})
            for item in page["items"]:
                require(item["id"] not in seen, "Pagination duplicated a contribution")
                seen.add(item["id"])
                items.append(item)
            require(page["next"] >= cursor, "Cursor moved backward")
            if page["omitted"] is None:
                return items, page["next"]
            require(page["next"] > cursor and page["items"], "Omitted page cannot make forward progress")
            cursor = page["next"]
        raise CheckFailure("Fixture pagination exceeded the harness safety guard")

    def test(self, identifier, group, function, skip=None):
        started = time.monotonic()
        result = {"id": identifier, "group": group}
        if skip:
            result.update({"status": "skipped", "reason": skip})
        else:
            try:
                details = function()
                result.update({"status": "passed", "observations": details or {}})
            except CheckFailure as error:
                result.update({"status": "failed", "reason": str(error)})
            except Exception as error:
                result.update({"status": "failed", "reason": "Harness could not interpret a required value (" + type(error).__name__ + "); response withheld"})
        result["durationMs"] = round((time.monotonic() - started) * 1000)
        self.cases.append(result)
        print(result["status"].upper() + " " + identifier, flush=True)
        return result["status"] == "passed"

    def preflight(self):
        capabilities = self.wire.request("/capabilities", method="GET")
        require(capabilities["status"] == 200, "Public capability discovery failed")
        advertised = capabilities["body"]
        require(advertised.get("protocolVersion") == "0.2", "Operator does not advertise Cayapa 0.2")
        content = advertised.get("capabilities", {}).get("content", {})
        require({"utf-8", "base64"} <= set(content.get("encodings", [])) and content.get("maxEnvelopeBytes") == 8192, "Opaque content capability differs from this profile")
        for role in ("a", "b", "b2", "reader", "outsider", "removed", "late"):
            identity = self.ok(self.http, role, "whoami")
            require(isinstance(identity.get("actor", {}).get("id"), str) and isinstance(identity.get("owner", {}).get("id"), str), "Fixture identity is malformed")
            require(identity.get("protocolVersion") == "0.2", "Authenticated protocol version is inconsistent")
            self.identities[role] = identity
        require(self.identities["a"]["actor"]["id"] != self.identities["b"]["actor"]["id"], "Fixture A and B must be distinct actors")
        require(self.identities["b"]["actor"] == self.identities["b2"]["actor"], "Fixture B2 must be a second credential for B")
        require(self.identities["b"]["connectionId"] != self.identities["b2"]["connectionId"], "Fixture B and B2 must be separate connections")
        require(len({self.identities[role]["actor"]["id"] for role in ("a", "b", "reader", "outsider", "removed", "late")}) == 6, "Fixture roles must use distinct actors except B2")
        self.error(self.http, "revoked", "whoami", {}, "unauthorized")
        if self.mcp:
            initialized = self.mcp.rpc(self.tokens["b"], "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "cayapa-portable-conformance", "version": "1"}})
            require(initialized.get("result", {}).get("protocolVersion") == "2025-11-25", "MCP version negotiation failed")
            discovered = self.mcp.rpc(self.tokens["b"], "tools/list")
            names = {tool.get("name") for tool in discovered.get("result", {}).get("tools", [])}
            require(CORE_OPERATIONS <= names, "MCP discovery omits a documented messaging operation")
            identity = self.ok(self.mcp, "a", "whoami")
            require(identity["actor"] == self.identities["a"]["actor"] and identity["owner"] == self.identities["a"]["owner"], "MCP changed credential attribution")
        return {"protocolVersion": "0.2", "separateActors": True, "separateCredentialsForB": True, "mcpInitialized": self.mcp is not None}

    def exchange(self):
        utf8 = {"content": {"mediaType": "application/x-cayapa-test+json", "encoding": "utf-8", "data": '{"actor":"not-authority","unicode":"á/á/🧭/中文","literal":" \\n\\t\\u0000","activity":"arbitrary"}', "fallback": "Fabricated opaque payload"}}
        binary = bytes(range(256)) + b"\x00\xff\x00\x80"
        opaque_binary = {"content": {"mediaType": "application/octet-stream", "encoding": "base64", "data": base64.b64encode(binary).decode("ascii")}}
        first = self.send(self.http, "a", utf8)
        self.exact_body(self.record(self.peer, "b", first), utf8, "a")
        second = self.send(self.peer, "b", opaque_binary, replyTo=first["value"]["id"])
        received = self.record(self.http, "a", second)
        self.exact_body(received, opaque_binary, "b")
        require(base64.b64decode(received["content"]["data"], validate=True) == binary, "Decoded binary bytes changed")
        require(received["replyTo"] == first["value"]["id"] and received["replyToHidden"] is False, "Visible reply relationship changed")
        text_body = {"text": "  Compatibility text: café 🧭\n\t  "}
        legacy = self.send(self.http, "a", text_body)
        self.exact_body(self.record(self.peer, "b", legacy), text_body, "a")
        self.records["first"] = first
        self.records["binary"] = second
        return {"utf8Sha256": digest(utf8["content"]["data"].encode("utf-8")), "binarySha256": digest(binary), "binaryBytes": len(binary), "textPreserved": True, "replyPreserved": True}

    def client_exchange(self):
        require(self.client is not None, "An external client is required but no subprocess driver was configured")
        identity = self.ok(self.client, "a", "whoami")
        require(identity["actor"] == self.identities["a"]["actor"] and identity["owner"] == self.identities["a"]["owner"], "External client authenticated as the wrong actor")
        bodies = [
            {"content": {"mediaType": "application/x-independent-fixture", "encoding": "utf-8", "data": "é ≠ é; 雪; 🧭; \x00\n\t\"\\", "fallback": "Independent fixture"}},
            {"content": {"mediaType": "application/octet-stream", "encoding": "base64", "data": base64.b64encode(bytes(reversed(range(256)))).decode("ascii")}},
        ]
        for body in bodies:
            outgoing = self.send(self.client, "a", body)
            self.exact_body(self.record(self.peer, "b", outgoing), body, "a")
            incoming = self.send(self.peer, "b", body, replyTo=outgoing["value"]["id"])
            item = self.record(self.client, "a", incoming)
            self.exact_body(item, body, "b")
            require(item["replyTo"] == outgoing["value"]["id"], "External client lost the reply relationship")
            duplicate = self.ok(self.client, "a", "send", outgoing["arguments"])
            require(duplicate["id"] == outgoing["value"]["id"] and duplicate["duplicate"] is True, "External client retry duplicated a contribution")
            self.error(self.client, "a", "send", {**outgoing["arguments"], "content": {**body["content"], "fallback": "Changed intent"}}, "conflict")
        self.error(self.client, "outsider", "read", {"conversation": self.conversations["main"]}, "not_found")
        self.error(self.client, "revoked", "whoami", {}, "unauthorized")
        return {"peerBinding": self.peer.name, "directions": 2, "encodingsPerDirection": 2, "exactBodies": 4, "sameIntentRetry": True, "changedIntentRejected": True, "unauthorizedClientRejected": True}

    def retries(self):
        sent = self.records["first"]
        args = sent["arguments"]
        body = args["content"]
        reordered = {**args, "replyTo": None, "corrects": None, "content": {name: body[name] for name in reversed(list(body))}}
        retried = self.ok(self.peer, "a", "send", reordered)
        require(retried["id"] == sent["value"]["id"] and retried["convSeq"] == sent["value"]["convSeq"] and retried["duplicate"] is True, "Equivalent retry did not preserve acceptance")
        changes = [
            {**args, "content": {**body, "data": body["data"] + " "}},
            {**args, "content": {**body, "fallback": "Changed fallback"}},
            {**args, "content": {**body, "mediaType": "application/json"}},
            {"conversation": args["conversation"], "intentKey": args["intentKey"], "text": body["data"]},
            {**args, "conversation": self.conversations["bounds"]},
        ]
        for changed in changes:
            self.error(self.peer, "a", "send", changed, "conflict")
        items, unused = self.drain(self.http, "a", "read", {"conversation": self.conversations["main"]})
        require(sum(item["id"] == sent["value"]["id"] for item in items) == 1, "Retry produced duplicate log entries")
        other = self.send(self.peer, "b", {"content": body}, key=args["intentKey"])
        require(other["value"]["id"] != sent["value"]["id"], "Intent keys were incorrectly shared between actors")
        second_connection = self.ok(self.http, "b2", "send", other["arguments"])
        require(second_connection["id"] == other["value"]["id"] and second_connection["duplicate"] is True, "Intent namespace was incorrectly separated by credential")
        return {"equivalentRetryDeduplicated": True, "changedIntentsRejected": len(changes), "keyScopeIsActorAcrossConversations": True, "sameActorAcrossCredentialsDeduplicated": True}

    def invalid_does_not_consume(self, invalid_body):
        key = self.key()
        args = {"conversation": self.conversations["main"], "intentKey": key, **invalid_body}
        self.error(self.http, "a", "send", args, "invalid")
        self.error(self.peer, "a", "send", args, "invalid")
        repaired = self.send(self.peer, "a", {"content": {"mediaType": "application/octet-stream", "encoding": "base64", "data": "AA=="}}, key=key)
        self.exact_body(self.record(self.http, "b", repaired), {"content": repaired["arguments"]["content"]}, "a")
        return {"checkedBindings": sorted({self.http.name, self.peer.name}), "sameKeyAcceptedAfterRepair": True}

    def authorization(self, participant=None):
        participant = participant or self.peer
        sent = self.records["first"]
        self.record(participant, "reader", sent)
        self.error(participant, "reader", "send", {"conversation": self.conversations["main"], "intentKey": self.key(), "text": "reader must not write"}, "unauthorized")
        self.error(participant, "reader", "retract", {"contribution": sent["value"]["id"]}, "unauthorized")
        for role in ("outsider", "removed"):
            for driver in (self.http, participant):
                self.error(driver, role, "read", {"conversation": self.conversations["main"]}, "not_found")
                self.error(driver, role, "list_members", {"conversation": self.conversations["main"]}, "not_found")
                self.error(driver, role, "send", {"conversation": self.conversations["main"], "intentKey": self.key(), "text": "no audience grant"}, "not_found")
                self.error(driver, role, "acknowledge", {"contribution": sent["value"]["id"]}, "not_found")
                self.error(driver, role, "retract", {"contribution": sent["value"]["id"]}, "not_found")
                listed = self.ok(driver, role, "list_conversations")
                require(all(item["id"] != self.conversations["main"] for item in listed), "Membership discovery disclosed an unauthorized conversation")
                inbox, unused = self.drain(driver, role, "inbox", {"after": 0})
                require(all(item["conversation"] != self.conversations["main"] for item in inbox), "Inbox disclosed an unauthorized conversation")
        for driver in (self.http, participant):
            self.error(driver, "revoked", "read", {"conversation": self.conversations["main"]}, "unauthorized")
            self.error(driver, "revoked", "inbox", {"after": 0}, "unauthorized")
            self.error(driver, "revoked", "send", {"conversation": self.conversations["main"], "intentKey": self.key(), "text": "revoked access"}, "unauthorized")
        members = self.ok(participant, "a", "list_members", {"conversation": self.conversations["main"]})
        reader = [member for member in members["members"] if member["actor"]["id"] == self.identities["reader"]["actor"]["id"]]
        require(len(reader) == 1 and reader[0]["role"] == "reader", "Fixture reader does not have read-only membership")
        return {"participantBinding": participant.name, "readerDeniedWrites": True, "outsiderDenied": True, "preRemovedMembershipDenied": True, "preRevokedCredentialDenied": True, "transitionTimingTested": False}

    def history(self, participant=None):
        reader = participant or self.peer
        writer = participant or self.http
        fixture = self.fixture["history"]
        items, unused = self.drain(reader, "late", "read", {"conversation": fixture["conversation"], "afterSeq": 0, "limit": 1})
        require(all(item["id"] != fixture["hiddenContribution"] for item in items), "Withheld history was disclosed")
        matches = [item for item in items if item["id"] == fixture["visibleContribution"]]
        require(len(matches) == 1, "Visible history fixture is absent")
        item = matches[0]
        require(item["convSeq"] == fixture["visibleSeq"] and item["replyTo"] is None and item["replyToHidden"] is True
                and item["corrects"] is None and item["correctsHidden"] is True, "Hidden relationships disclosed an identifier or lost the visibility signal")
        inbox, unused = self.drain(reader, "late", "inbox", {"after": 0})
        require(all(item["id"] != fixture["hiddenContribution"] for item in inbox)
                and any(item["id"] == fixture["visibleContribution"] for item in inbox), "Inbox did not preserve the granted history boundary")
        self.error(writer, "late", "acknowledge", {"contribution": fixture["hiddenContribution"]}, "not_found")
        key = self.key()
        args = {"conversation": fixture["conversation"], "intentKey": key, "text": "History boundary fixture", "replyTo": fixture["hiddenContribution"]}
        self.error(reader, "late", "send", args, "not_found")
        del args["replyTo"]
        repaired = self.ok(writer, "late", "send", args)
        require(repaired["duplicate"] is False, "Invisible relationship consumed an intent key")
        return {"participantBinding": reader.name, "oldContentWithheld": True, "replyAndCorrectionIdentifiersHidden": True, "hiddenTargetCannotBeAcknowledged": True, "failedReferenceDoesNotConsumeKey": True}

    def cursors_and_receipts(self, participant=None):
        first_connection = participant or self.peer
        second_connection = participant or self.http
        unused, baseline = self.drain(first_connection, "b", "inbox", {"mode": "replay", "limit": 2})
        first = self.send(self.http, "a", {"text": "cursor fixture one"})
        second = self.send(self.http, "a", {"text": "cursor fixture two"}, conversation="bounds")
        own = self.send(first_connection, "b", {"text": "own contribution is not inbox delivery"})
        third = self.send(self.http, "a", {"text": "cursor fixture three"})
        first_page = self.page(first_connection, "b", "inbox", {"after": baseline, "limit": 1})
        require([item["id"] for item in first_page["items"]] == [first["value"]["id"]] and first_page["omitted"] == {"more": True, "reason": "limit"}, "Inbox count continuation is incorrect")
        repeated = self.page(second_connection, "b2", "inbox", {"after": baseline, "limit": 1})
        require(repeated["next"] == first_page["next"] and repeated["items"][0]["id"] == first["value"]["id"], "Another connection advanced or lost a cursor")
        resumed, final_cursor = self.drain(second_connection, "b2", "inbox", {"after": first_page["next"], "limit": 1})
        require([item["id"] for item in resumed] == [second["value"]["id"], third["value"]["id"]], "Resumed inbox confused conversation positions or included own messages")
        conversation = self.page(first_connection, "b", "read", {"conversation": self.conversations["main"], "afterSeq": first["value"]["convSeq"], "limit": 1})
        require(conversation["items"][0]["id"] == own["value"]["id"] and conversation["next"] == own["value"]["convSeq"], "Conversation cursor was confused with inbox position")
        empty = self.page(first_connection, "b", "inbox", {"after": final_cursor, "limit": 1})
        require(empty["items"] == [] and empty["next"] == final_cursor and empty["omitted"] is None, "Empty inbox changed the supplied cursor")
        before = self.record(self.http, "a", first)
        require(before["receivedBy"] == [], "Read or inbox implicitly acknowledged receipt")
        result = self.ok(first_connection, "b", "acknowledge", {"contribution": first["value"]["id"]})
        require(result == {"ok": True, "acknowledged": 1, "skipped": []}, "Single acknowledgement result is incorrect")
        received = self.record(self.http, "a", first)
        self.ok(second_connection, "b", "acknowledge", {"contribution": first["value"]["id"], "stage": "received"})
        require(self.record(self.http, "a", first)["receivedBy"] == received["receivedBy"], "Repeating receipt changed its first timestamp")
        unread_b, unused = self.drain(first_connection, "b", "inbox", {"after": baseline, "mode": "unread", "limit": 2})
        unread_b2, unused = self.drain(second_connection, "b2", "inbox", {"after": baseline, "mode": "unread", "limit": 2})
        require(first["value"]["id"] not in {item["id"] for item in unread_b} and first["value"]["id"] in {item["id"] for item in unread_b2}, "Unread receipts were shared across credentials")
        replay, unused = self.drain(first_connection, "b", "inbox", {"after": baseline, "mode": "replay", "limit": 2})
        require(first["value"]["id"] in {item["id"] for item in replay}, "Replay incorrectly filtered acknowledged messages")
        self.ok(second_connection, "b2", "acknowledge", {"contribution": first["value"]["id"]})
        projection = self.record(self.http, "a", first)["receivedBy"]
        require(len(projection) == 1 and projection[0]["actor"]["id"] == self.identities["b"]["actor"]["id"], "Receipt projection did not aggregate the actor's connections")
        absent = "absent-" + uuid.uuid4().hex
        mixed = self.ok(first_connection, "reader", "acknowledge", {"contributions": [first["value"]["id"], absent]})
        require(mixed == {"ok": True, "acknowledged": 1, "skipped": [absent]}, "Mixed visible and hidden receipt batch is incorrect")
        self.error(second_connection, "b", "acknowledge", {"contribution": first["value"]["id"], "stage": "executed"}, "invalid")
        self.error(second_connection, "b", "acknowledge", {"contributions": []}, "invalid")
        self.error(first_connection, "b", "acknowledge", {"contributions": [first["value"]["id"]] * 51}, "invalid")
        return {"participantBinding": first_connection.name, "separateCursorSpaces": True, "resumedWithoutDuplicates": True, "newProcessPerOperation": participant is self.client and self.client is not None, "readDoesNotAcknowledge": True, "unreadIsCredentialScoped": True, "receiptProjectionIsActorScoped": True, "executionReceiptRejected": True}

    def removal(self, participant=None):
        receiver = participant or self.peer
        author = participant or self.http
        body = {"content": {"mediaType": "application/x-tombstone-fixture", "encoding": "utf-8", "data": "Fabricated removable opaque data", "fallback": "Remove this fallback too"}}
        sent = self.send(self.http, "a", body)
        child = self.send(receiver, "b", {"text": "Visible child relation survives tombstone"}, replyTo=sent["value"]["id"])
        initial = self.record(receiver, "b", sent)
        self.error(receiver, "b", "retract", {"contribution": sent["value"]["id"]}, "unauthorized")
        removed = self.ok(receiver, "a", "retract", {"contribution": sent["value"]["id"]})
        require(removed == {"id": sent["value"]["id"], "removed": True}, "Retraction result is incorrect")
        tombstone = self.record(self.http, "b", sent)
        require(tombstone["text"] is None and tombstone["content"] is None and tombstone["removed"]["by"] == "author", "Retraction retained a body or lost its tombstone")
        for field in ("id", "conversation", "convSeq", "author", "owner", "createdAt", "protocolVersion", "replyTo", "corrects"):
            require(tombstone[field] == initial[field], "Retraction changed retained identity or relationship metadata")
        self.ok(author, "a", "retract", {"contribution": sent["value"]["id"]})
        require(self.record(receiver, "b", sent)["removed"] == tombstone["removed"], "Repeated retraction changed its first removal fact")
        retried = self.ok(author, "a", "send", sent["arguments"])
        require(retried["id"] == sent["value"]["id"] and retried["duplicate"] is True, "Retry after removal lost the original intent")
        require(self.record(receiver, "b", sent)["content"] is None, "Retry resurrected removed content")
        self.error(receiver, "a", "send", {**sent["arguments"], "content": {**body["content"], "data": "Changed removed intent"}}, "conflict")
        require(self.record(self.http, "a", child)["replyTo"] == sent["value"]["id"], "Tombstone broke a visible reply relationship")
        self.ok(receiver, "b", "acknowledge", {"contribution": sent["value"]["id"]})
        replay, unused = self.drain(author, "b", "inbox", {"after": 0, "mode": "replay"})
        seen = [item for item in replay if item["id"] == sent["value"]["id"]]
        require(len(seen) == 1 and seen[0]["text"] is None and seen[0]["content"] is None, "Replay exposed a removed body")
        legacy = self.send(self.http, "a", {"text": "Fabricated removable legacy text"})
        self.ok(receiver, "a", "retract", {"contribution": legacy["value"]["id"]})
        item = self.record(author, "b", legacy)
        require(item["text"] is None and item["content"] is None, "Retraction retained legacy text")
        return {"participantBinding": receiver.name, "opaqueEnvelopeAndFallbackCleared": True, "legacyTextCleared": True, "tombstoneRetained": True, "retryCannotResurrect": True, "replayAndRelationsPreserved": True}

    def malformed_http(self):
        bodies = [b"{", b"null", b"[]", b'"string"', b'{"invalid":"\xff"}']
        for body in bodies:
            response = self.wire.request("/v0/whoami", self.tokens["a"], raw=body)
            require(response["status"] == 400 and response["body"].get("error", {}).get("code") == "invalid", "Malformed HTTP request was not rejected")
        missing = self.wire.request("/v0/whoami", payload={})
        require(missing["status"] == 401 and missing["body"].get("error", {}).get("code") == "unauthorized", "Missing credential was not rejected")
        method = self.wire.request("/v0/whoami", self.tokens["a"], method="GET")
        require(method["status"] == 405, "HTTP operation accepted an unsupported method")
        self.error(self.http, "a", "not_a_cayapa_operation", {}, "invalid")
        self.error(self.http, "a", "inbox", {"mode": "invented"}, "invalid")
        return {"malformedFormsRejected": len(bodies), "missingCredentialRejected": True, "unsupportedMethodAndOperationRejected": True}

    def request_bounds(self):
        exact = b"{}" + b" " * (65536 - 2)
        accepted = self.wire.request("/v0/whoami", self.tokens["a"], raw=exact)
        require(accepted["status"] == 200 and accepted["body"].get("ok") is True, "HTTP rejected an exactly bounded valid request")
        for path, valid in (("/v0/whoami", exact), ("/mcp", encoded({"jsonrpc": "2.0", "id": 50000, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}}))):
            if path == "/mcp" and not self.mcp:
                continue
            overflow = valid + b" " * (65537 - len(valid))
            rejected = self.wire.request(path, self.tokens["a"], raw=overflow)
            require(rejected["status"] == 413 and rejected["body"].get("ok") is False and rejected["body"].get("error", {}).get("code") == "invalid", "Binding failed to reject an oversized request")
        if self.mcp:
            request = encoded({"jsonrpc": "2.0", "id": 50001, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}})
            accepted = self.wire.request("/mcp", self.tokens["a"], raw=request + b" " * (65536 - len(request)))
            require(accepted["status"] == 200 and accepted["body"].get("result", {}).get("isError") is False, "MCP rejected an exactly bounded valid request")
        return {"acceptedRawRequestBytes": 65536, "rejectedRawRequestBytes": 65537, "mcpWrapperCounted": self.mcp is not None}

    def malformed_mcp(self):
        for body, code in ((b"{", -32700), (b'{"x":"\xff"}', -32700), (b"[]", -32600), (b'{"jsonrpc":"1.0","id":1,"method":"tools/list"}', -32600)):
            response = self.wire.request("/mcp", self.tokens["a"], raw=body)
            require(response["status"] == 400 and response["body"].get("error", {}).get("code") == code, "Malformed MCP request did not return its specified JSON-RPC error")
        unknown_method = self.mcp.rpc(self.tokens["a"], "not_a_method")
        require(unknown_method.get("error", {}).get("code") == -32601, "Unknown MCP method did not fail")
        unknown_tool = self.mcp.rpc(self.tokens["a"], "tools/call", {"name": "not_a_tool", "arguments": {}})
        require(unknown_tool.get("error", {}).get("code") == -32602, "Unknown MCP tool did not fail")
        fallback = self.mcp.rpc(self.tokens["a"], "initialize", {"protocolVersion": "unsupported-version", "capabilities": {}, "clientInfo": {"name": "cayapa-portable-conformance", "version": "1"}})
        require(fallback.get("result", {}).get("protocolVersion") == "2025-11-25", "MCP did not return its supported version on mismatch")
        notification = self.wire.request("/mcp", self.tokens["a"], {"jsonrpc": "2.0", "method": "notifications/initialized"})
        require(notification["status"] == 202 and notification["body"] is None, "MCP notification response is incorrect")
        return {"parseAndEnvelopeFailuresRejected": 4, "unknownMethodAndToolRejected": True, "versionMismatchObserved": True, "notificationAcknowledged": True}

    def vector(self, vector, driver, role):
        body = vector["sendBody"]
        arguments = {"conversation": self.conversations["vectors"], "intentKey": self.key(), **body}
        if vector["accepted"]:
            sent = self.send(driver, role, body, conversation="vectors", key=arguments["intentKey"])
            other = "b" if role == "a" else "a"
            reader = self.peer if driver is self.http else self.http
            self.exact_body(self.record(reader, other, sent), vector.get("normalized", body), role)
            return {"accepted": True, "writeBinding": driver.name, "readBinding": reader.name, "bodyPreserved": True}
        raw = encoded(arguments, ascii_only=True)
        if driver is self.http:
            response = self.wire.request("/v0/send", self.tokens[role], raw=raw)
            require(response["status"] == 400 and response["body"].get("ok") is False
                    and response["body"].get("error", {}).get("code") == vector.get("errorCode", "invalid"), "Invalid vector was not rejected by HTTP")
        else:
            self.mcp.next_id += 1
            rpc = {"jsonrpc": "2.0", "id": self.mcp.next_id, "method": "tools/call", "params": {"name": "send", "arguments": arguments}}
            response = self.wire.request("/mcp", self.tokens[role], raw=encoded(rpc, ascii_only=True))
            result = response["body"].get("result", {})
            require(response["status"] == 200 and result.get("isError") is True
                    and result.get("structuredContent", {}).get("error", {}).get("code") == vector.get("errorCode", "invalid"), "Invalid vector was not rejected by MCP")
        return {"accepted": False, "expectedErrorObserved": True}

    def page_budget(self):
        content = {"mediaType": "application/octet-stream", "encoding": "utf-8", "data": ""}
        content["data"] = "x" * (8192 - len(encoded(content)))
        require(len(encoded(content)) == 8192, "Harness did not construct the exact envelope boundary")
        sent = [self.send(self.http, "a", {"content": content}, conversation="bounds") for unused in range(9)]
        start = sent[0]["value"]["convSeq"] - 1
        first = self.page(self.peer, "b", "read", {"conversation": self.conversations["bounds"], "afterSeq": start, "limit": 50})
        require(first["omitted"] == {"more": True, "reason": "bytes"}, "Large complete contributions did not produce a byte-omission continuation")
        require(sum(len(encoded(item)) for item in first["items"]) <= 65536, "Multi-item payload exceeded the documented item budget")
        items, unused = self.drain(self.peer, "b", "read", {"conversation": self.conversations["bounds"], "afterSeq": start, "limit": 50})
        require([item["id"] for item in items] == [item["value"]["id"] for item in sent], "Byte-limited continuation lost or duplicated contributions")
        for item in items:
            self.exact_body(item, {"content": content}, "a")
        return {"envelopeBytes": 8192, "largeContributions": len(sent), "firstPageItems": len(first["items"]), "completeItemsPreserved": True, "hardResponseWireBoundTested": False, "firstItemExceptionEliminated": False}


def load_fixture(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigurationFailure("Cannot read fixture JSON") from None
    if not isinstance(value, dict) or value.get("fixtureVersion") != 1 or value.get("disposable") is not True:
        raise ConfigurationFailure("Use fixtureVersion 1 and explicitly mark fabricated fixtures disposable:true")
    safe_endpoint(value.get("baseUrl"))
    if any(not isinstance(value.get(name), dict) for name in ("credentials", "conversations", "history")):
        raise ConfigurationFailure("Fixture credentials, conversations, and history must be objects")
    bindings = value.get("bindings", ["http", "mcp"])
    if not isinstance(bindings, list) or any(not isinstance(binding, str) for binding in bindings) or "http" not in bindings or not set(bindings) <= {"http", "mcp"}:
        raise ConfigurationFailure("Fixture bindings must include http and may include mcp")
    for role in ("a", "b", "b2", "reader", "outsider", "removed", "revoked", "late"):
        token = value.get("credentials", {}).get(role)
        if not isinstance(token, str) or not token or "<" in token or re.search(r"[\s\x00-\x1f\x7f]", token):
            raise ConfigurationFailure("Fixture needs a private credential for every documented role")
    for name in ("main", "bounds", "vectors"):
        if not isinstance(value.get("conversations", {}).get(name), str) or not value["conversations"][name]:
            raise ConfigurationFailure("Fixture needs main, bounds, and vectors conversations")
    if len(set(value["conversations"].values())) != len(value["conversations"]):
        raise ConfigurationFailure("Use distinct fixture conversations to isolate quotas and pagination")
    history = value.get("history", {})
    if any(not isinstance(history.get(name), str) or not history[name] for name in ("conversation", "hiddenContribution", "visibleContribution")) or not valid_position(history.get("visibleSeq")):
        raise ConfigurationFailure("Fixture needs the documented withheld-history records")
    if history["conversation"] in value["conversations"].values():
        raise ConfigurationFailure("History fixtures need a separate conversation")
    if "operatorRevision" in value and (not isinstance(value["operatorRevision"], str) or not re.fullmatch(r"[a-fA-F0-9]{40,64}", value["operatorRevision"])):
        raise ConfigurationFailure("operatorRevision must be a full hexadecimal source revision")
    return value


def load_vectors():
    try:
        value = json.loads((Path(__file__).resolve().parent.parent / "vectors" / "content.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigurationFailure("Portable content vectors are missing or unreadable") from None
    if not isinstance(value, dict) or value.get("format") != "cayapa-content-vectors-1" or not isinstance(value.get("cases"), list):
        raise ConfigurationFailure("Unsupported portable vector format")
    cases = value["cases"]
    for case in cases:
        if (not isinstance(case, dict) or not re.fullmatch(r"[a-zA-Z0-9._-]{1,100}", case.get("id", ""))
                or not isinstance(case.get("sendBody"), dict) or type(case.get("accepted")) is not bool):
            raise ConfigurationFailure("Portable vector shape is invalid")
    if sum(case["accepted"] for case in cases) > 30:
        raise ConfigurationFailure("This fixture layout supports at most 30 accepted vectors per binding and actor")
    return cases


def bundle_hashes():
    root = Path(__file__).resolve().parent.parent
    paths = [root / "specification.md", root / "bindings" / "http.md", root / "bindings" / "mcp.md", Path(__file__).resolve()]
    paths += sorted((root / "schemas").glob("*.json")) + sorted((root / "vectors").glob("*.json"))
    return {str(path.relative_to(root)): digest(path.read_bytes()) for path in paths if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description="Exercise Cayapa 0.2 through public HTTP/MCP and an optional independently installed client. Mutates explicitly disposable fixtures.")
    parser.add_argument("--fixture", required=True, help="Private JSON fixture file; see README.md")
    parser.add_argument("--report", required=True, help="Content-free JSON report destination")
    parser.add_argument("--client-command-json", help="JSON argv array for the subprocess client driver; no shell is used")
    parser.add_argument("--require-client", action="store_true", help="Fail the external-client case if no driver is configured")
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture)
        vectors = load_vectors()
        command = json.loads(args.client_command_json) if args.client_command_json else None
        if command is not None and (not isinstance(command, list) or not command or any(not isinstance(part, str) or not part for part in command)):
            raise ConfigurationFailure("Client command must be a nonempty JSON argv array")
        suite = Suite(fixture, command)
    except (ConfigurationFailure, ValueError) as error:
        parser.error(str(error) if isinstance(error, ConfigurationFailure) else "Client command is not valid JSON")
    ready = suite.test("fixture-and-capabilities", "setup", suite.preflight)
    unavailable = None if ready else "Required fixture or capability precondition failed"
    exchanged = suite.test("attributed-opaque-and-text-exchange", "messaging", suite.exchange, skip=unavailable)
    dependent = unavailable or (None if exchanged else "Initial message acceptance failed")
    client_exchanged = suite.test("external-client-bidirectional-exchange", "external-client", suite.client_exchange,
                                 skip=unavailable or ("No external client configured; independent client interoperability is unproven" if not suite.client and not args.require_client else None))
    client_unavailable = unavailable or ("No external client configured" if not suite.client else None if client_exchanged else "External client exchange did not satisfy its precondition")
    suite.test("same-and-changed-intent", "messaging", suite.retries, skip=dependent)
    suite.test("unknown-send-field-does-not-consume-key", "messaging", lambda: suite.invalid_does_not_consume({"text": "invalid field fixture", "author": "untrusted-claimed-author"}), skip=unavailable)
    suite.test("unknown-content-field-does-not-consume-key", "messaging", lambda: suite.invalid_does_not_consume({"content": {"mediaType": "text/plain", "encoding": "utf-8", "data": "invalid content field fixture", "execute": True}}), skip=unavailable)
    suite.test("mixed-body-does-not-consume-key", "messaging", lambda: suite.invalid_does_not_consume({"text": "mixed body fixture", "content": {"mediaType": "text/plain", "encoding": "utf-8", "data": "mixed"}}), skip=unavailable)
    suite.test("authorization-and-pre-revoked-access", "authorization", suite.authorization, skip=dependent)
    suite.test("withheld-history-and-hidden-relations", "authorization", suite.history, skip=unavailable)
    suite.test("cursors-replay-unread-and-receipts", "messaging", suite.cursors_and_receipts, skip=unavailable)
    suite.test("retraction-tombstones-and-retries", "messaging", suite.removal, skip=unavailable)
    suite.test("external-client-cursors-and-receipts", "external-client", lambda: suite.cursors_and_receipts(suite.client), skip=client_unavailable)
    suite.test("external-client-authorization", "external-client", lambda: suite.authorization(suite.client), skip=client_unavailable or dependent)
    suite.test("external-client-withheld-history", "external-client", lambda: suite.history(suite.client), skip=client_unavailable)
    suite.test("external-client-retraction", "external-client", lambda: suite.removal(suite.client), skip=client_unavailable)
    suite.test("http-invalid-and-unsupported-input", "http-binding", suite.malformed_http, skip=unavailable)
    suite.test("raw-request-byte-boundaries", "http-binding", suite.request_bounds, skip=unavailable)
    suite.test("mcp-invalid-and-unsupported-input", "mcp-binding", suite.malformed_mcp, skip=unavailable or (None if suite.mcp else "MCP binding not requested"))
    for vector in vectors:
        suite.test("http-vector-" + vector["id"], "content-vectors", lambda vector=vector: suite.vector(vector, suite.http, "a"), skip=unavailable)
        if suite.mcp:
            suite.test("mcp-vector-" + vector["id"], "content-vectors", lambda vector=vector: suite.vector(vector, suite.mcp, "b"), skip=unavailable)
    suite.test("complete-contribution-byte-pagination", "bounds", suite.page_budget, skip=unavailable)
    counts = {status: sum(case["status"] == status for case in suite.cases) for status in ("passed", "failed", "skipped")}
    report = {
        "reportFormat": "cayapa-conformance-1",
        "protocolVersion": "0.2",
        "observedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "operatorRevision": fixture.get("operatorRevision"),
        "endpointScope": "loopback" if suite.loopback else "https-fixture",
        "bindings": fixture.get("bindings", ["http", "mcp"]),
        "externalClientConfigured": bool(command),
        "fixtureAssumptions": {"fabricatedAndDisposable": True, "provisionedOutsideProtocol": True, "revokedAndRemovedBeforeRunner": True, "liveOwnerControlTransitionsTested": False},
        "bundleSha256": bundle_hashes(),
        "counts": counts,
        "cases": suite.cases,
        "limits": [
            "This report observes one operator; it does not establish independent operator implementations or federation.",
            "An external subprocess is a separate client path; its authorship and installation provenance require separate evidence.",
            "MCP authentication here uses fabricated raw actor credentials, not an interactive host OAuth flow.",
            "Revoked credentials and removed memberships are provisioned before this runner; owner-side transition timing is not tested here.",
            "The 65536-byte page item budget has a first-item exception and excludes page and binding wrappers; no hard response-wire bound is claimed.",
            "Conversation discovery is unbounded; omitted member discovery has no continuation cursor.",
            "No autonomous host loop, wake callback, real agent, payment, attachment, federated routing, or exactly-once execution is tested.",
        ],
    }
    try:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        print("Cannot write the content-free report", file=sys.stderr)
        return 2
    print("Conformance observations: " + ", ".join(str(counts[status]) + " " + status for status in ("passed", "failed", "skipped")))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
