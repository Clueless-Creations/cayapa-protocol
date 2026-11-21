import argparse
import base64
import concurrent.futures
import datetime
import hashlib
import http.client
import http.server
import json
import os
import platform
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import cryptography
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import NameOID

from run import CheckFailure, require


ROOT = Path(__file__).resolve().parent.parent
MESSAGE_PATH = "/cayapa/v0.3/messages"
DELEGATION_PATH = "/cayapa/v0.3/delegations/revoke"
ADMISSION_PATH = "/cayapa/v0.3/admissions/revoke"
CAPABILITIES_PATH = "/cayapa/v0.3/capabilities"
RESPONSE_LIMIT = 65536
PROCESS_OUTPUT_LIMIT = 2 * 1024 * 1024
PROCESS_TIMEOUT = 15


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def b64(value):
    return base64.b64encode(value).decode("ascii")


def url64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def unurl64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def utc(value):
    return datetime.datetime.fromtimestamp(value, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def private_file(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def public_bytes(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def save_key(key, path):
    private_file(path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def capture(command, value=None):
    environment = {name: os.environ[name] for name in ("PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL", "PYTHONUTF8") if name in os.environ}
    deadline = time.monotonic() + PROCESS_TIMEOUT
    with tempfile.TemporaryFile() as input_file:
        input_file.write(b"" if value is None else packed(value))
        input_file.seek(0)
        process = subprocess.Popen(command, stdin=input_file, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment, bufsize=0, start_new_session=True)
        raw = bytearray()
        finished = threading.Event()
        read_failed = threading.Event()

        def consume():
            try:
                while len(raw) <= PROCESS_OUTPUT_LIMIT:
                    block = process.stdout.read(min(65536, PROCESS_OUTPUT_LIMIT + 1 - len(raw)))
                    if not block:
                        break
                    raw.extend(block)
            except (OSError, ValueError):
                read_failed.set()
            finally:
                finished.set()

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        try:
            require(finished.wait(max(0, deadline - time.monotonic())), "Adapter exceeded its wall deadline")
            require(not read_failed.is_set(), "Adapter output could not be read; content withheld")
            require(len(raw) <= PROCESS_OUTPUT_LIMIT, "Adapter output exceeded the capture bound")
            try:
                status = process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise CheckFailure("Adapter exceeded its wall deadline") from None
        finally:
            stop_process(process)
            process.stdout.close()
            reader.join(timeout=1)
    try:
        result = json.loads(raw)
    except (UnicodeError, ValueError):
        raise CheckFailure("Adapter did not return one JSON result; output withheld") from None
    require(isinstance(result, dict), "Adapter result must be an object")
    return result, status


def stop_process(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=1)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class Identity:
    def __init__(self, directory, label):
        self.owner = "urn:uuid:" + secrets.token_hex(16)
        self.actor = "urn:uuid:" + secrets.token_hex(16)
        self.owner_id = self.owner + "#owner-1"
        self.actor_id = self.actor + "#actor-1"
        self.owner_key = ed25519.Ed25519PrivateKey.generate()
        self.actor_key = ed25519.Ed25519PrivateKey.generate()
        self.owner_file = directory / (label + "-owner-private.pem")
        self.actor_file = directory / (label + "-actor-private.pem")
        self.public_file = directory / (label + "-owner-public.pem")
        save_key(self.owner_key, self.owner_file)
        save_key(self.actor_key, self.actor_file)
        private_file(self.public_file, self.owner_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    def claims(self, recipient, **changes):
        now = int(time.time())
        value = {
            "iss": self.owner, "sub": self.actor, "aud": recipient,
            "iat": now - 1, "nbf": now - 1, "exp": now + 850,
            "jti": secrets.token_hex(12), "scope": "cayapa:deliver",
            "cnf": {"jwk": {"kty": "OKP", "crv": "Ed25519", "x": url64(public_bytes(self.actor_key)), "kid": self.actor_id}},
        }
        value.update(changes)
        return value

    def token(self, recipient, claims=None, header=None, signing_key=None, raw_claims=None):
        protected = header or {"typ": "cayapa-delegation+jwt", "alg": "Ed25519", "kid": self.owner_id}
        payload = packed(self.claims(recipient) if claims is None else claims) if raw_claims is None else raw_claims
        signing_input = (url64(packed(protected)) + "." + url64(payload)).encode("ascii")
        return signing_input.decode("ascii") + "." + url64((signing_key or self.owner_key).sign(signing_input))


class Certificates:
    def __init__(self, directory):
        self.directory = directory
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Disposable direct conformance CA")])
        now = datetime.datetime.now(datetime.timezone.utc)
        self.cert = x509.CertificateBuilder().subject_name(self.name).issuer_name(self.name).public_key(self.key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(self.key, hashes.SHA256())
        self.ca_file = directory / "tls-ca.pem"
        private_file(self.ca_file, self.cert.public_bytes(serialization.Encoding.PEM))

    def server(self, label, hostname="localhost"):
        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])).issuer_name(self.name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False).add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False).sign(self.key, hashes.SHA256())
        key_file = self.directory / (label + "-tls-key.pem")
        cert_file = self.directory / (label + "-tls-cert.pem")
        save_key(key, key_file)
        private_file(cert_file, cert.public_bytes(serialization.Encoding.PEM))
        return cert_file, key_file


class Operator:
    def __init__(self, command, directory, label, identity, peer, certificates, limits=None, admissions=None):
        self.command = command
        self.label = label
        self.identity = identity
        self.peer = peer
        self.process = None
        self.directory = directory / label
        self.directory.mkdir(mode=0o700)
        self.config_file = self.directory / "config.json"
        self.port = free_port()
        self.origin = "https://localhost:" + str(self.port)
        cert_file, key_file = certificates.server(label)
        now = int(time.time())
        self.admission_id = label + "-admission"
        self.config = {
            "origin": self.origin, "listenHost": "127.0.0.1", "port": self.port,
            "tlsCertificateFile": str(cert_file), "tlsPrivateKeyFile": str(key_file),
            "clientCaFile": str(certificates.ca_file), "statePath": str(self.directory / "state"),
            "recipient": {"actor": identity.actor, "owner": identity.owner},
            "trustedOwners": [{"owner": owner.owner, "keyId": owner.owner_id, "publicKeyFile": str(owner.public_file)} for owner in (identity, peer)],
            "admissions": admissions if admissions is not None else [{"id": self.admission_id, "owner": peer.owner, "actor": peer.actor, "recipient": identity.actor, "scope": "cayapa:deliver", "notBefore": now - 5, "expiresAt": now + 86400, "active": True}],
            "limits": limits or {"nonces": 4096, "messages": 4096, "controls": 4096},
            "testMode": True, "faultFile": str(self.directory / "fault.json"),
        }
        private_file(self.config_file, packed(self.config))

    def invoke(self, verb, value=None):
        return capture(self.command + [verb, "--config", str(self.config_file)], value)

    def start(self):
        require(self.process is None, "Operator already running")
        self.process = subprocess.Popen(self.command + ["serve", "--config", str(self.config_file)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, start_new_session=True)
        ready = threading.Event()
        state = {"valid": False}

        def read_ready():
            try:
                raw = self.process.stdout.readline(1025)
                state["valid"] = len(raw) <= 1024 and json.loads(raw) == {"ready": True}
            except (OSError, ValueError):
                pass
            finally:
                ready.set()

        self.reader = threading.Thread(target=read_ready, daemon=True)
        self.reader.start()
        if not ready.wait(10) or not state["valid"]:
            self.stop()
            raise CheckFailure("Operator did not become ready within the bounded startup period")

    def stop(self):
        process = self.process
        if process is None:
            return
        stop_process(process)
        process.stdout.close()
        self.reader.join(timeout=1)
        self.process = None

    def restart(self, crash=False):
        if crash and self.process is not None:
            os.killpg(self.process.pid, signal.SIGKILL)
        self.stop()
        self.start()

    def inspect(self):
        result, status = self.invoke("inspect")
        require(status == 0 and isinstance(result.get("messages"), list), "Local handoff inspection failed")
        return result

    def fault(self, operation):
        private_file(Path(self.config["faultFile"]), packed({"operation": operation, "phase": "after-commit"}))


class Reply:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = {key.lower(): value for key, value in headers}
        try:
            self.value = json.loads(body)
        except (UnicodeError, ValueError):
            self.value = None


class Harness:
    def __init__(self, left_command, right_command, directory):
        self.directory = directory
        self.certificates = Certificates(directory)
        self.context = ssl.create_default_context(cafile=str(self.certificates.ca_file))
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.left_identity = Identity(directory, "left")
        self.right_identity = Identity(directory, "right")
        self.left = Operator(left_command, directory, "left", self.left_identity, self.right_identity, self.certificates)
        self.right = Operator(right_command, directory, "right", self.right_identity, self.left_identity, self.certificates)
        self.operators = [self.left, self.right]
        self.cases = []
        self.extra = []

    def case(self, lane, name, operation):
        started = time.monotonic()
        try:
            operation()
            result = {"lane": lane, "name": name, "status": "passed"}
        except CheckFailure as error:
            result = {"lane": lane, "name": name, "status": "failed", "reason": str(error)}
        except Exception as error:
            result = {"lane": lane, "name": name, "status": "failed", "reason": "Harness or adapter raised " + type(error).__name__ + "; details withheld"}
        result["durationMs"] = round((time.monotonic() - started) * 1000)
        self.cases.append(result)
        print(json.dumps(result), flush=True)

    def event(self, sender, receiver, payload=b"opaque payload", **changes):
        value = {
            "specversion": "1.0", "type": "dev.cayapa.message", "source": sender.identity.actor,
            "id": secrets.token_hex(12), "datacontenttype": "application/octet-stream", "data_base64": b64(payload),
            "cayapaowner": sender.identity.owner, "cayapato": receiver.identity.actor,
            "cayapaprofile": "direct/0.3", "cayapaexpires": utc(int(time.time()) + 1800),
        }
        value.update(changes)
        return packed(value)

    def token(self, sender, receiver, **changes):
        return sender.identity.token(receiver.identity.actor, claims=sender.identity.claims(receiver.identity.actor, **changes))

    def native(self, sender, receiver, body, token=None, path=MESSAGE_PATH, owner=False, key=None, key_id=None, key_file=None, **options):
        identity = sender.identity
        request = {
            "endpoint": receiver.origin + path, "bodyBase64": b64(body),
            "keyId": key_id or (identity.owner_id if owner else identity.actor_id),
            "privateKeyFile": str(key_file or (identity.owner_file if owner else identity.actor_file)),
        }
        if path == MESSAGE_PATH:
            request["delegation"] = token or self.token(sender, receiver)
        request.update(options)
        result, status = sender.invoke("request", request)
        outcome = result.get("outcome")
        require(status == {"accepted": 0, "revoked": 0, "rejected": 1, "unknown": 2}.get(outcome), "Native client exit status disagrees with normalized outcome")
        return result

    def headers(self, sender, receiver, body, token=None, path=MESSAGE_PATH, owner=False, created=None, expires=None, nonce=None, key=None, key_id=None, content_type=None, target=None, component_names=None, algorithm="ed25519", tag=None):
        delivery = path == MESSAGE_PATH
        key = key or (sender.identity.owner_key if owner else sender.identity.actor_key)
        key_id = key_id or (sender.identity.owner_id if owner else sender.identity.actor_id)
        created = int(time.time()) if created is None else created
        expires = created + 60 if expires is None else expires
        nonce = nonce or secrets.token_hex(16)
        content_type = content_type or ("application/cloudevents+json" if delivery else "application/json")
        digest = "sha-256=:" + b64(hashlib.sha256(body).digest()) + ":"
        components = component_names or (["@method", "@target-uri", "content-type", "content-digest", "cayapa-delegation"] if delivery else ["@method", "@target-uri", "content-type", "content-digest"])
        tag = tag or ("cayapa-delivery-0.3" if delivery else "cayapa-control-0.3")
        parameters = "(" + " ".join('"' + component + '"' for component in components) + f');created={created};expires={expires};nonce="{nonce}";keyid="{key_id}";alg="{algorithm}";tag="{tag}"'
        values = {"@method": "POST", "@target-uri": target or receiver.origin + path, "content-type": content_type, "content-digest": digest, "cayapa-delegation": token or ""}
        signature_base = "\n".join('"' + component + '": ' + values[component] for component in components) + '\n"@signature-params": ' + parameters
        headers = {
            "Host": urlsplit(receiver.origin).netloc, "Content-Type": content_type, "Content-Length": str(len(body)),
            "Content-Digest": digest, "Signature-Input": "sig1=" + parameters,
            "Signature": "sig1=:" + b64(key.sign(signature_base.encode("utf-8"))) + ":",
        }
        if delivery:
            headers["Cayapa-Delegation"] = token or self.token(sender, receiver)
        return headers

    def wire(self, receiver, body=b"", headers=None, path=MESSAGE_PATH, method="POST"):
        connection = http.client.HTTPSConnection("localhost", receiver.port, timeout=10, context=self.context)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            raw = response.read(RESPONSE_LIMIT + 1)
            require(len(raw) <= RESPONSE_LIMIT, "Response exceeded the public client bound")
            return Reply(response.status, response.getheaders(), raw)
        finally:
            connection.close()

    def signed(self, sender, receiver, body=None, token=None, **options):
        body = self.event(sender, receiver) if body is None else body
        token = token or self.token(sender, receiver)
        path = options.get("path", MESSAGE_PATH)
        return self.wire(receiver, body, self.headers(sender, receiver, body, token, **options), path)

    def refuse(self, reply, status, code):
        require(reply.status in status if isinstance(status, set) else reply.status == status, "Receiver returned an unexpected refusal status")
        require(isinstance(reply.value, dict), "Refusal did not contain a problem document")
        expected = {"type": "about:blank", "title": "Request rejected", "status": reply.status, "coreVersion": "0.3", "profile": "direct/0.3", "outcome": "rejected"}
        require(all(reply.value.get(key) == value for key, value in expected.items()), "Refusal problem fields disagree with the contract")
        require(reply.value.get("code") in code if isinstance(code, set) else reply.value.get("code") == code, "Receiver returned an unexpected refusal code")
        require(reply.headers.get("content-type") == "application/problem+json", "Refusal media type is invalid")

    def accepted(self, result, body, duplicate=False):
        require(result.get("outcome") == "accepted", "Native send did not report accepted")
        require(result.get("httpStatus") == (200 if duplicate else 201), "Acceptance status disagrees with retry state")
        receipt = result.get("receipt")
        event = json.loads(body)
        expected = {
            "coreVersion": "0.3", "profile": "direct/0.3", "outcome": "accepted", "delivery": "receiver-custody",
            "source": event["source"], "id": event["id"], "to": event["cayapato"], "bodySha256": sha(body),
            "expiresAt": int(datetime.datetime.strptime(event["cayapaexpires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()),
            "duplicate": duplicate,
        }
        require(isinstance(receipt, dict) and all(type(receipt.get(key)) is type(value) and receipt.get(key) == value for key, value in expected.items()), "Receipt does not bind the exact accepted intent")
        require(type(receipt.get("acceptedAt")) is int and 0 <= receipt["acceptedAt"] <= int(time.time()), "Receipt acceptance time is invalid")
        return receipt

    def custody(self, receiver, body, expected_count=1):
        event = json.loads(body)
        messages = receiver.inspect()["messages"]
        matches = [entry for entry in messages if entry.get("receipt", {}).get("source") == event["source"] and entry.get("receipt", {}).get("id") == event["id"]]
        require(len(matches) == expected_count, "Local handoff count disagrees with acceptance semantics")
        if expected_count:
            require(matches[0].get("bodyBase64") == b64(body), "Local handoff changed the exact accepted envelope bytes")

    def control_body(self, sender, receiver, target, path=DELEGATION_PATH, request_id=None):
        return packed({"issuer": sender.identity.owner, "audience": receiver.identity.actor, "delegation_jti" if path == DELEGATION_PATH else "admission_id": target, "request_id": request_id or secrets.token_hex(12)})

    def revoked(self, result, body, duplicate=False):
        receipt = result.get("receipt", {})
        require(result.get("outcome") == "revoked" and result.get("httpStatus") == 200, "Authenticated withdrawal was not acknowledged")
        expected = {"coreVersion": "0.3", "outcome": "revoked", "scope": "receiver", "request_id": json.loads(body)["request_id"], "duplicate": duplicate}
        require(all(type(receipt.get(key)) is type(value) and receipt.get(key) == value for key, value in expected.items()), "Withdrawal receipt fields are invalid")
        require(type(receipt.get("effectiveAt")) is int and 0 <= receipt["effectiveAt"] <= int(time.time()), "Withdrawal effective time is invalid")
        return receipt

    def vectors(self):
        vectors = json.loads((ROOT / "vectors/direct-signatures.json").read_text())
        owner = serialization.load_pem_public_key(vectors["ownerPublicKeyPem"].encode())
        for vector in vectors["cases"]:
            body = base64.b64decode(vector["bodyBase64"], validate=True)
            require(vector["contentDigest"] == "sha-256=:" + b64(hashlib.sha256(body).digest()) + ":", "Known-answer content digest is incorrect")
            token = vector["delegation"]
            if token:
                protected, claims, signature = token.split(".")
                owner.verify(unurl64(signature), (protected + "." + claims).encode("ascii"))
            key = serialization.load_pem_public_key(vector["publicKeyPem"].encode())
            key.verify(base64.b64decode(vector["signature"][6:-1]), vector["signatureBase"].encode())
            values = [('"@method"', vector["method"]), ('"@target-uri"', vector["targetUri"]), ('"content-type"', vector["contentType"]), ('"content-digest"', vector["contentDigest"])]
            if token:
                values.append(('"cayapa-delegation"', token))
            values.append(('"@signature-params"', vector["signatureInput"][5:]))
            require("\n".join(key + ": " + value for key, value in values) == vector["signatureBase"], "Known-answer signature base disagrees with published components")

    def capabilities(self, receiver):
        reply = self.wire(receiver, path=CAPABILITIES_PATH, method="GET")
        require(reply.status == 200 and isinstance(reply.value, dict), "Capabilities unavailable")
        expected = {"coreVersion": "0.3", "profiles": ["direct/0.3"], "bindings": ["http-message/0.3"], "security": ["http-signatures/0.3"]}
        require(all(reply.value.get(key) == value for key, value in expected.items()), "Advertised profile or bindings disagree")
        require(reply.value.get("limits") == {"maxBodyBytes": 98304, "maxPayloadBytes": 65536, "maxMessageLifetimeSeconds": 86400, "maxDelegationLifetimeSeconds": 900, "maxSignatureLifetimeSeconds": 60}, "Advertised protocol limits disagree")

    def basic(self, sender, receiver, payload, media):
        body = self.event(sender, receiver, payload, datacontenttype=media)
        self.accepted(self.native(sender, receiver, body), body)
        self.custody(receiver, body)

    def retry(self, sender, receiver):
        body = self.event(sender, receiver)
        first = self.accepted(self.native(sender, receiver, body), body)
        second = self.accepted(self.native(sender, receiver, body), body, True)
        require({key: value for key, value in first.items() if key != "duplicate"} == {key: value for key, value in second.items() if key != "duplicate"}, "Retry did not preserve original receipt")
        self.custody(receiver, body)

    def conflict(self, sender, receiver, whitespace=False):
        body = self.event(sender, receiver)
        self.accepted(self.native(sender, receiver, body), body)
        changed = body + b" " if whitespace else packed({**json.loads(body), "data_base64": b64(b"different")})
        self.refuse(self.signed(sender, receiver, changed), 409, "conflict")
        self.custody(receiver, body)

    def concurrent(self, sender, receiver):
        body = self.event(sender, receiver)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.native, sender, receiver, body) for unused in range(2)]
            results = [future.result(timeout=35) for future in futures]
        require(sorted(result.get("httpStatus", 0) for result in results) == [200, 201], "Concurrent identical intents did not serialize to one acceptance")
        for result in results:
            self.accepted(result, body, result["httpStatus"] == 200)
        self.custody(receiver, body)

    def replay(self, sender, receiver, restart=False):
        body = self.event(sender, receiver)
        token = self.token(sender, receiver)
        parameters = {"nonce": secrets.token_hex(16), "created": int(time.time())}
        parameters["expires"] = parameters["created"] + 60
        self.accepted(self.native(sender, receiver, body, token, **parameters), body)
        if restart:
            receiver.restart()
        result = self.native(sender, receiver, body, token, **parameters)
        require(result.get("outcome") == "rejected" and result.get("httpStatus") == 409 and result.get("code") == "replay", "Authenticated nonce replay was not refused")
        self.custody(receiver, body)

    def negative_cases(self, sender, receiver):
        lane = sender.label + "-to-" + receiver.label

        def body_refusal(changes, status=400, code="invalid", transform=None):
            body = self.event(sender, receiver, **changes)
            if transform:
                body = transform(body)
            self.refuse(self.signed(sender, receiver, body), status, code)

        variants = [
            ("unknown-profile", {"cayapaprofile": "direct/9.9"}, 422, "unsupported_profile"),
            ("wrong-recipient-attribution", {"cayapato": sender.identity.actor}, 401, "unauthorized"),
            ("wrong-source-attribution", {"source": receiver.identity.actor}, 401, "unauthorized"),
            ("wrong-owner-attribution", {"cayapaowner": receiver.identity.owner}, 401, "unauthorized"),
            ("unknown-envelope-control", {"conversation": "not-core"}, 400, "invalid"),
            ("invalid-uri-percent-escape", {"source": "urn:bad:%GG"}, 400, "invalid"),
            ("invalid-media-type", {"datacontenttype": "not a media type"}, 400, "invalid"),
            ("noncanonical-payload-base64", {"data_base64": "YQ"}, 400, "invalid"),
            ("noncanonical-base64-pad-bits", {"data_base64": "YR=="}, 400, "invalid"),
            ("expired-message", {"cayapaexpires": utc(int(time.time()) - 1)}, 410, "expired"),
            ("excessive-message-lifetime", {"cayapaexpires": utc(int(time.time()) + 90000)}, 400, "invalid"),
            ("fractional-message-expiry", {"cayapaexpires": utc(int(time.time()) + 1800).replace("Z", ".000Z")}, 400, "invalid"),
            ("payload-over-limit", {"data_base64": b64(b"x" * 65537)}, 413, "too_large"),
        ]
        for name, changes, status, code in variants:
            self.case(lane, name, lambda changes=changes, status=status, code=code: body_refusal(changes, status, code))
        for name, transform in [
            ("duplicate-envelope-member", lambda body: b'{"id":"duplicate",' + body[1:]),
            ("invalid-utf8", lambda body: body[:-1] + b'\xff}'),
            ("byte-order-mark", lambda body: b"\xef\xbb\xbf" + body),
            ("lone-unicode-surrogate", lambda body: body.replace(b"application/octet-stream", b"application/\\ud800")),
        ]:
            self.case(lane, name, lambda transform=transform: body_refusal({}, transform=transform))

        def token_refusal(changes=None, header=None, rogue=False, transform=None):
            claims = sender.identity.claims(receiver.identity.actor)
            claims.update(changes or {})
            raw_claims = transform(packed(claims)) if transform else None
            token = sender.identity.token(receiver.identity.actor, claims=claims, header=header, signing_key=ed25519.Ed25519PrivateKey.generate() if rogue else None, raw_claims=raw_claims)
            self.refuse(self.signed(sender, receiver, token=token), 401, "unauthorized")

        now = int(time.time())
        token_variants = [
            ("wrong-delegation-audience", {"aud": sender.identity.actor}),
            ("wrong-delegation-scope", {"scope": "anything"}),
            ("expired-delegation", {"iat": now - 100, "nbf": now - 100, "exp": now - 1}),
            ("future-delegation", {"iat": now, "nbf": now + 60, "exp": now + 800}),
            ("excessive-delegation-lifetime", {"iat": now, "nbf": now, "exp": now + 901}),
            ("delegation-unknown-claim", {"extra": "not-defined"}),
            ("unknown-owner-pin", {"iss": "urn:unknown:owner"}),
        ]
        for name, changes in token_variants:
            self.case(lane, name, lambda changes=changes: token_refusal(changes))
        for name, algorithm in [("jwt-none-algorithm", "none"), ("jwt-polymorphic-algorithm", "EdDSA"), ("jwt-algorithm-confusion", "HS256")]:
            self.case(lane, name, lambda algorithm=algorithm: token_refusal(header={"typ": "cayapa-delegation+jwt", "alg": algorithm, "kid": sender.identity.owner_id}))
        self.case(lane, "forged-owner-signature", lambda: token_refusal(rogue=True))
        self.case(lane, "duplicate-jwt-member", lambda: token_refusal(transform=lambda raw: b'{"scope":"cayapa:deliver",' + raw[1:]))
        self.case(lane, "fractional-jwt-time-token", lambda: token_refusal(transform=lambda raw: raw.replace(b'"iat":' + str(json.loads(raw)["iat"]).encode(), b'"iat":' + str(json.loads(raw)["iat"]).encode() + b".0")))

        def private_jwk():
            claims = sender.identity.claims(receiver.identity.actor)
            claims["cnf"]["jwk"]["d"] = url64(b"x" * 32)
            token_refusal(claims)

        self.case(lane, "private-jwk-material", private_jwk)

        def owner_key_as_actor(owner_identity):
            claims = sender.identity.claims(receiver.identity.actor)
            actor_id = sender.identity.actor + "#forbidden-control-key"
            claims["cnf"]["jwk"].update({"kid": actor_id, "x": url64(public_bytes(owner_identity.owner_key))})
            token = sender.identity.token(receiver.identity.actor, claims=claims)
            body = self.event(sender, receiver)
            self.refuse(self.signed(sender, receiver, body, token, key=owner_identity.owner_key, key_id=actor_id), 401, "unauthorized")

        self.case(lane, "issuer-owner-key-cannot-be-actor-key", lambda: owner_key_as_actor(sender.identity))
        self.case(lane, "other-pinned-owner-key-cannot-be-actor-key", lambda: owner_key_as_actor(receiver.identity))

        def signature_refusal(kind):
            body = self.event(sender, receiver)
            token = self.token(sender, receiver)
            options = {}
            if kind == "expired-signature":
                options = {"created": int(time.time()) - 70, "expires": int(time.time()) - 10}
            elif kind == "future-signature":
                options = {"created": int(time.time()) + 60, "expires": int(time.time()) + 90}
            elif kind == "excessive-signature-lifetime":
                options = {"expires": int(time.time()) + 70}
            elif kind == "wrong-signature-algorithm":
                options = {"algorithm": "Ed25519"}
            elif kind == "wrong-signature-domain":
                options = {"tag": "cayapa-control-0.3"}
            elif kind == "missing-digest-coverage":
                options = {"component_names": ["@method", "@target-uri", "content-type", "cayapa-delegation"]}
            elif kind == "wrong-target-uri":
                options = {"target": receiver.origin + MESSAGE_PATH + "?different=1"}
            headers = self.headers(sender, receiver, body, token, **options)
            if kind == "body-tampering":
                body = body.replace(b"opaque", b"altered") if b"opaque" in body else body + b" "
                headers["Content-Length"] = str(len(body))
            elif kind == "forged-actor-signature":
                headers["Signature"] = "sig1=:" + b64(b"\x00" * 64) + ":"
            elif kind == "wrong-content-digest":
                headers["Content-Digest"] = "sha-256=:" + b64(b"\x00" * 32) + ":"
            self.refuse(self.wire(receiver, body, headers), 401, "unauthorized")

        for name in ["expired-signature", "future-signature", "excessive-signature-lifetime", "wrong-signature-algorithm", "wrong-signature-domain", "missing-digest-coverage", "wrong-target-uri", "body-tampering", "forged-actor-signature", "wrong-content-digest"]:
            self.case(lane, name, lambda name=name: signature_refusal(name))

        def missing_admission():
            actor = "urn:unadmitted:" + secrets.token_hex(8)
            claims = sender.identity.claims(receiver.identity.actor, sub=actor)
            token = sender.identity.token(receiver.identity.actor, claims=claims)
            body = self.event(sender, receiver, source=actor)
            self.refuse(self.signed(sender, receiver, body, token), 403, "not_admitted")

        self.case(lane, "identity-without-recipient-admission", missing_admission)

        def forbidden_control(owner, path):
            body = self.control_body(sender, receiver, "unseen", path)
            result = self.native(sender, receiver, body, path=path, owner=owner)
            require(result.get("outcome") == "rejected" and result.get("httpStatus") in {401, 403}, "Unauthorized controller was not refused")

        self.case(lane, "actor-cannot-withdraw-owner-delegation", lambda: forbidden_control(False, DELEGATION_PATH))
        self.case(lane, "foreign-owner-cannot-withdraw-recipient-admission", lambda: forbidden_control(True, ADMISSION_PATH))

        def wrong_media():
            body = self.event(sender, receiver)
            self.refuse(self.signed(sender, receiver, body, content_type="application/json"), 415, "unsupported_media_type")

        def compressed():
            body = self.event(sender, receiver)
            token = self.token(sender, receiver)
            headers = self.headers(sender, receiver, body, token)
            headers["Content-Encoding"] = "gzip"
            self.refuse(self.wire(receiver, body, headers), {400, 415}, {"invalid", "unsupported_media_type"})

        def large_body():
            body = self.event(sender, receiver)
            body += b" " * (98305 - len(body))
            self.refuse(self.signed(sender, receiver, body), 413, "too_large")

        self.case(lane, "unsupported-envelope-media-type", wrong_media)
        self.case(lane, "unsupported-content-encoding", compressed)
        self.case(lane, "body-over-limit", large_body)

    def loss_and_recovery(self, sender, receiver):
        body = self.event(sender, receiver)
        receiver.fault("message")
        result = self.native(sender, receiver, body)
        require(result.get("outcome") == "unknown", "Lost post-commit response was not reported unknown")
        receiver.restart(crash=True)
        self.accepted(self.native(sender, receiver, body), body, True)
        self.custody(receiver, body)

    def withdrawal(self, sender, receiver, response_loss=False):
        claims = sender.identity.claims(receiver.identity.actor)
        token = sender.identity.token(receiver.identity.actor, claims=claims)
        body = self.event(sender, receiver)
        self.accepted(self.native(sender, receiver, body, token), body)
        control = self.control_body(sender, receiver, claims["jti"])
        if response_loss:
            receiver.fault("control")
            result = self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True)
            require(result.get("outcome") == "unknown", "Lost withdrawal response was not reported unknown")
        else:
            self.revoked(self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True), control)
        receiver.restart(crash=response_loss)
        self.revoked(self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True), control, True)
        result = self.native(sender, receiver, body, token)
        require(result.get("outcome") == "rejected" and result.get("httpStatus") == 401, "Withdrawn delegation leaked a prior acceptance receipt")
        self.custody(receiver, body)
        unseen = self.event(sender, receiver)
        self.refuse(self.signed(sender, receiver, unseen, token), 401, "unauthorized")
        self.custody(receiver, unseen, 0)

    def control_conflict(self, sender, receiver):
        control = self.control_body(sender, receiver, secrets.token_hex(10))
        self.revoked(self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True), control)
        changed = packed({**json.loads(control), "delegation_jti": secrets.token_hex(10)})
        result = self.native(sender, receiver, changed, path=DELEGATION_PATH, owner=True)
        require(result.get("outcome") == "rejected" and result.get("httpStatus") == 409 and result.get("code") == "conflict", "Control intent reuse with changed body was not refused")

    def cross_route_control(self, receiver, nonce_reuse=False):
        request_id = secrets.token_hex(12)
        first = self.control_body(receiver, receiver, "unseen-delegation", request_id=request_id)
        nonce = secrets.token_hex(16)
        self.revoked(self.native(receiver, receiver, first, path=DELEGATION_PATH, owner=True, nonce=nonce), first)
        second = self.control_body(receiver, receiver, "unseen-admission", ADMISSION_PATH, secrets.token_hex(12) if nonce_reuse else request_id)
        result = self.native(receiver, receiver, second, path=ADMISSION_PATH, owner=True, **({"nonce": nonce} if nonce_reuse else {}))
        require(result.get("outcome") == "rejected" and result.get("httpStatus") == 409 and result.get("code") == ("replay" if nonce_reuse else "conflict"), "Cross-route control identity or nonce scope was not enforced")

    def preemptive_withdrawal(self, sender, receiver):
        claims = sender.identity.claims(receiver.identity.actor)
        control = self.control_body(sender, receiver, claims["jti"])
        self.revoked(self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True), control)
        receiver.restart()
        token = sender.identity.token(receiver.identity.actor, claims=claims)
        body = self.event(sender, receiver)
        self.refuse(self.signed(sender, receiver, body, token), 401, "unauthorized")
        self.custody(receiver, body, 0)

    def invalid_attempt_nonce(self, sender, receiver):
        body = self.event(sender, receiver)
        token = self.token(sender, receiver)
        nonce = secrets.token_hex(16)
        headers = self.headers(sender, receiver, body, token, nonce=nonce)
        headers["Signature"] = "sig1=:" + b64(b"\x00" * 64) + ":"
        self.refuse(self.wire(receiver, body, headers), 401, "unauthorized")
        self.accepted(self.native(sender, receiver, body, token, nonce=nonce), body)
        self.custody(receiver, body)

    def nonce_across_delegations(self, sender, receiver):
        body = self.event(sender, receiver)
        nonce = secrets.token_hex(16)
        self.accepted(self.native(sender, receiver, body, self.token(sender, receiver), nonce=nonce), body)
        result = self.native(sender, receiver, body, self.token(sender, receiver), nonce=nonce)
        require(result.get("outcome") == "rejected" and result.get("httpStatus") == 409 and result.get("code") == "replay", "A replacement delegation bypassed the actor key's nonce ledger")
        self.custody(receiver, body)

    def interrupted_upload(self, sender, receiver):
        body = self.event(sender, receiver)
        token = self.token(sender, receiver)
        headers = self.headers(sender, receiver, body, token)
        raw_socket = socket.create_connection(("127.0.0.1", receiver.port), timeout=10)
        with self.context.wrap_socket(raw_socket, server_hostname="localhost") as connection:
            connection.settimeout(10)
            head = "POST " + MESSAGE_PATH + " HTTP/1.1\r\n" + "".join(key + ": " + value + "\r\n" for key, value in headers.items()) + "Connection: close\r\n\r\n"
            connection.sendall(head.encode("ascii") + body[:len(body) // 2])
        receiver.restart(crash=True)
        self.accepted(self.native(sender, receiver, body, token), body)
        self.custody(receiver, body)

    def expired_intent(self, sender, receiver):
        expires = int(time.time()) + 2
        body = self.event(sender, receiver, cayapaexpires=utc(expires))
        self.accepted(self.native(sender, receiver, body), body)
        time.sleep(max(0, expires + 0.05 - time.time()))
        self.refuse(self.signed(sender, receiver, body), 410, "expired")

    def rotation(self, sender, receiver):
        claims = sender.identity.claims(receiver.identity.actor)
        token = sender.identity.token(receiver.identity.actor, claims=claims)
        body = self.event(sender, receiver)
        self.accepted(self.native(sender, receiver, body, token), body)
        control = self.control_body(sender, receiver, claims["jti"])
        self.revoked(self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True), control)
        new_key = ed25519.Ed25519PrivateKey.generate()
        key_file = self.directory / (sender.label + "-rotated-actor.pem")
        save_key(new_key, key_file)
        key_id = sender.identity.actor + "#actor-rotated"
        claims = sender.identity.claims(receiver.identity.actor)
        claims["cnf"]["jwk"].update({"kid": key_id, "x": url64(public_bytes(new_key))})
        token = sender.identity.token(receiver.identity.actor, claims=claims)
        self.accepted(self.native(sender, receiver, body, token, key_id=key_id, key_file=key_file), body, True)
        new_body = self.event(sender, receiver)
        self.accepted(self.native(sender, receiver, new_body, token, key_id=key_id, key_file=key_file), new_body)
        self.custody(receiver, body)
        self.custody(receiver, new_body)

    def inflight(self, sender, receiver, expiry=False):
        now = int(time.time())
        claims = sender.identity.claims(receiver.identity.actor)
        token = sender.identity.token(receiver.identity.actor, claims=claims)
        body = self.event(sender, receiver)
        options = {"created": now - 55, "expires": now + 2} if expiry else {}
        headers = self.headers(sender, receiver, body, token, **options)
        raw_socket = socket.create_connection(("127.0.0.1", receiver.port), timeout=10)
        with self.context.wrap_socket(raw_socket, server_hostname="localhost") as connection:
            connection.settimeout(10)
            head = "POST " + MESSAGE_PATH + " HTTP/1.1\r\n" + "".join(key + ": " + value + "\r\n" for key, value in headers.items()) + "Connection: close\r\n\r\n"
            connection.sendall(head.encode("ascii") + body[:-1])
            if expiry:
                time.sleep(max(0, now + 2.1 - time.time()))
            else:
                control = self.control_body(sender, receiver, claims["jti"])
                self.revoked(self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True), control)
            connection.sendall(body[-1:])
            response = http.client.HTTPResponse(connection)
            response.begin()
            self.refuse(Reply(response.status, response.getheaders(), response.read(RESPONSE_LIMIT + 1)), 401, "unauthorized")
        self.custody(receiver, body, 0)

    def pending_withdrawal(self, sender, receiver):
        claims = sender.identity.claims(receiver.identity.actor)
        token = sender.identity.token(receiver.identity.actor, claims=claims)
        control = self.control_body(sender, receiver, claims["jti"])
        receiver.stop()
        try:
            result = self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True)
            require(result.get("outcome") == "unknown", "Unreachable withdrawal was not reported unknown")
        finally:
            receiver.start()
        body = self.event(sender, receiver)
        self.accepted(self.native(sender, receiver, body, token), body)
        self.revoked(self.native(sender, receiver, control, path=DELEGATION_PATH, owner=True), control)
        self.refuse(self.signed(sender, receiver, self.event(sender, receiver), token), 401, "unauthorized")

    def admission_withdrawal(self, sender, receiver):
        body = self.event(sender, receiver)
        self.accepted(self.native(sender, receiver, body), body)
        control = self.control_body(receiver, receiver, receiver.admission_id, ADMISSION_PATH)
        self.revoked(self.native(receiver, receiver, control, path=ADMISSION_PATH, owner=True), control)
        receiver.restart()
        self.revoked(self.native(receiver, receiver, control, path=ADMISSION_PATH, owner=True), control, True)
        result = self.native(sender, receiver, body)
        require(result.get("outcome") == "rejected" and result.get("httpStatus") == 403 and result.get("code") == "not_admitted", "Withdrawn admission leaked a prior receipt or was resurrected at restart")
        self.custody(receiver, body)

    def raw_headers(self, sender, receiver, kind):
        body = self.event(sender, receiver)
        token = self.token(sender, receiver)
        headers = list(self.headers(sender, receiver, body, token).items())
        if kind == "duplicate-signature-header":
            headers.append(next(item for item in headers if item[0] == "Signature"))
        elif kind == "duplicate-content-length":
            headers.append(("Content-Length", str(len(body))))
        elif kind == "transfer-encoding":
            headers.append(("Transfer-Encoding", "chunked"))
        else:
            headers.append(("X-Padding", "x" * 16400))
        raw_socket = socket.create_connection(("127.0.0.1", receiver.port), timeout=10)
        with self.context.wrap_socket(raw_socket, server_hostname="localhost") as connection:
            connection.settimeout(10)
            request = "POST " + MESSAGE_PATH + " HTTP/1.1\r\n" + "".join(key + ": " + value + "\r\n" for key, value in headers) + "Connection: close\r\n\r\n"
            connection.sendall(request.encode("ascii") + body)
            response = http.client.HTTPResponse(connection)
            response.begin()
            require(400 <= response.status < 500, "Malformed framing or oversized headers were not refused")
        self.custody(receiver, body, 0)

    def capacity(self, sender, base_receiver, kind):
        limits = {"nonces": 100, "messages": 100, "controls": 100}
        limits[kind] = 1
        receiver = Operator(base_receiver.command, self.directory, base_receiver.label + "-capacity-" + kind, base_receiver.identity, sender.identity, self.certificates, limits)
        self.extra.append(receiver)
        receiver.start()
        try:
            if kind == "controls":
                first = self.control_body(sender, receiver, "first-target")
                self.revoked(self.native(sender, receiver, first, path=DELEGATION_PATH, owner=True), first)
                second = self.control_body(sender, receiver, "second-target")
                result = self.native(sender, receiver, second, path=DELEGATION_PATH, owner=True)
                require(result.get("outcome") == "rejected" and result.get("code") == "capacity", "Live control tombstone was evicted instead of refusing capacity")
                receiver.restart()
                self.revoked(self.native(sender, receiver, first, path=DELEGATION_PATH, owner=True), first, True)
            else:
                first = self.event(sender, receiver)
                token = self.token(sender, receiver)
                nonce = secrets.token_hex(16)
                self.accepted(self.native(sender, receiver, first, token, nonce=nonce), first)
                second = self.event(sender, receiver)
                result = self.native(sender, receiver, second)
                require(result.get("outcome") == "rejected" and result.get("httpStatus") == 429 and result.get("code") == "capacity", "Live state was evicted instead of refusing capacity")
                receiver.restart()
                if kind == "messages":
                    self.accepted(self.native(sender, receiver, first), first, True)
                else:
                    result = self.native(sender, receiver, first, token, nonce=nonce)
                    require(result.get("outcome") == "rejected" and result.get("code") == "replay", "Live replay state was lost at capacity or restart")
                self.custody(receiver, first)
                self.custody(receiver, second, 0)
        finally:
            receiver.stop()

    def client_refuses_untrusted_result(self, sender, receiver, mode):
        certificates = self.certificates
        if mode == "untrusted-ca":
            ca_directory = self.directory / ("unknown-ca-" + sender.label)
            ca_directory.mkdir(mode=0o700)
            certificates = Certificates(ca_directory)
        cert_file, key_file = certificates.server("fake-" + sender.label + "-" + mode, "wrong.invalid" if mode == "hostname" else "localhost")

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format_string, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 98304))
                event = json.loads(raw)
                status = 200
                response_body = b"{}"
                if mode in {"mismatched-digest", "mismatched-recipient", "status-duplicate-mismatch", "fractional-acceptance-time"}:
                    receipt = {"coreVersion": "0.3", "profile": "direct/0.3", "outcome": "accepted", "delivery": "receiver-custody", "source": event["source"], "id": event["id"], "to": event["cayapato"], "bodySha256": sha(raw), "acceptedAt": int(time.time()), "expiresAt": int(datetime.datetime.strptime(event["cayapaexpires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()), "duplicate": False}
                    status = 201
                    if mode == "mismatched-digest":
                        receipt["bodySha256"] = "0" * 64
                    elif mode == "mismatched-recipient":
                        receipt["to"] = "urn:wrong:recipient"
                    elif mode == "status-duplicate-mismatch":
                        receipt["duplicate"] = True
                    else:
                        receipt["acceptedAt"] += 0.5
                    response_body = packed(receipt)
                elif mode == "malformed-control":
                    response_body = packed({"coreVersion": "0.3", "outcome": "revoked", "scope": "receiver", "request_id": "wrong-request", "effectiveAt": int(time.time()), "duplicate": False})
                elif mode == "unrecognized-problem":
                    status = 403
                    response_body = packed({"type": "about:blank", "title": "Request rejected", "status": 403, "coreVersion": "9.9", "profile": "direct/0.3", "outcome": "rejected", "code": "not_admitted"})
                elif mode == "oversized":
                    response_body = b"x" * 65537
                elif mode == "redirect":
                    status = 302
                self.send_response(status)
                self.send_header("Content-Type", "application/problem+json" if mode == "unrecognized-problem" else "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                if mode == "redirect":
                    self.send_header("Location", receiver.origin + MESSAGE_PATH)
                self.end_headers()
                try:
                    self.wfile.write(response_body)
                except (OSError, ssl.SSLError):
                    pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert_file, key_file)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            body = self.control_body(sender, receiver, "unseen") if mode == "malformed-control" else self.event(sender, receiver)
            path = DELEGATION_PATH if mode == "malformed-control" else MESSAGE_PATH
            result = self.native(sender, receiver, body, path=path, owner=mode == "malformed-control", endpoint="https://localhost:" + str(server.server_port) + path)
            require(result.get("outcome") == "unknown", "Native client trusted an invalid or unauthenticated response")
            if path == MESSAGE_PATH:
                self.custody(receiver, body, 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def run(self):
        self.case("suite", "published-known-answer-signatures", self.vectors)
        for operator in self.operators:
            operator.start()
        for sender, receiver in [(self.left, self.right), (self.right, self.left)]:
            lane = sender.label + "-to-" + receiver.label
            self.case(lane, "explicit-capabilities", lambda receiver=receiver: self.capabilities(receiver))
            self.case(lane, "native-binary-message-and-local-custody", lambda: self.basic(sender, receiver, bytes(range(256)), "application/octet-stream"))
            self.case(lane, "native-unknown-content-type", lambda: self.basic(sender, receiver, "Cayapa: ¡hola! 🦜".encode(), "application/vnd.independent.example+opaque; version=7"))
            self.case(lane, "native-empty-payload", lambda: self.basic(sender, receiver, b"", "application/octet-stream"))
            self.case(lane, "maximum-payload", lambda: self.basic(sender, receiver, b"x" * 65536, "application/octet-stream"))

            def maximum_body():
                body = self.event(sender, receiver)
                body += b" " * (98304 - len(body))
                self.accepted(self.native(sender, receiver, body), body)
                self.custody(receiver, body)

            self.case(lane, "maximum-envelope-body", maximum_body)
            self.case(lane, "fresh-process-fresh-nonce-retry", lambda: self.retry(sender, receiver))
            self.case(lane, "changed-intent-conflict", lambda: self.conflict(sender, receiver))
            self.case(lane, "exact-byte-retry-equivalence", lambda: self.conflict(sender, receiver, True))
            self.case(lane, "concurrent-identical-intents", lambda: self.concurrent(sender, receiver))
            self.case(lane, "authenticated-request-replay", lambda: self.replay(sender, receiver))
            self.case(lane, "replay-survives-restart", lambda: self.replay(sender, receiver, True))
            before = len(receiver.inspect()["messages"])
            self.negative_cases(sender, receiver)
            self.case(lane, "refusals-created-no-handoffs", lambda before=before: require(len(receiver.inspect()["messages"]) == before, "A refused request changed the handoff store"))
            for kind in ["duplicate-signature-header", "duplicate-content-length", "transfer-encoding", "oversized-headers"]:
                self.case(lane, kind, lambda kind=kind: self.raw_headers(sender, receiver, kind))
            self.case(lane, "interrupted-upload-crash-and-retry", lambda: self.interrupted_upload(sender, receiver))
            self.case(lane, "lost-acceptance-response-crash-and-retry", lambda: self.loss_and_recovery(sender, receiver))
            self.case(lane, "owner-signed-withdrawal-and-restart", lambda: self.withdrawal(sender, receiver))
            self.case(lane, "lost-withdrawal-response-crash-and-retry", lambda: self.withdrawal(sender, receiver, True))
            self.case(lane, "control-intent-conflict", lambda: self.control_conflict(sender, receiver))
            self.case(lane, "cross-route-control-intent-conflict", lambda: self.cross_route_control(receiver))
            self.case(lane, "cross-route-owner-nonce-replay", lambda: self.cross_route_control(receiver, True))
            self.case(lane, "preemptive-withdrawal-survives-restart", lambda: self.preemptive_withdrawal(sender, receiver))
            self.case(lane, "unauthenticated-attempt-cannot-reserve-nonce", lambda: self.invalid_attempt_nonce(sender, receiver))
            self.case(lane, "actor-nonce-scope-spans-delegations", lambda: self.nonce_across_delegations(sender, receiver))
            self.case(lane, "accepted-intent-expiry-is-a-current-refusal", lambda: self.expired_intent(sender, receiver))
            self.case(lane, "actor-key-rotation-and-prior-intent", lambda: self.rotation(sender, receiver))
            self.case(lane, "withdrawal-during-inflight-delivery", lambda: self.inflight(sender, receiver))
            self.case(lane, "signature-expires-during-inflight-delivery", lambda: self.inflight(sender, receiver, True))
            self.case(lane, "remote-withdrawal-pending-until-receiver-commit", lambda: self.pending_withdrawal(sender, receiver))
            for kind in ["messages", "nonces", "controls"]:
                self.case(lane, "bounded-live-" + kind, lambda kind=kind: self.capacity(sender, receiver, kind))
            for mode in ["hostname", "untrusted-ca", "redirect", "malformed", "oversized", "mismatched-digest", "mismatched-recipient", "status-duplicate-mismatch", "fractional-acceptance-time", "malformed-control", "unrecognized-problem"]:
                self.case(lane, "native-client-refuses-" + mode, lambda mode=mode: self.client_refuses_untrusted_result(sender, receiver, mode))
            self.case(lane, "recipient-admission-withdrawal-and-restart", lambda: self.admission_withdrawal(sender, receiver))

    def stop(self):
        for operator in self.operators + self.extra:
            operator.stop()


def command(value):
    try:
        result = json.loads(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Command must be a JSON argv array") from None
    if not isinstance(result, list) or not result or not all(isinstance(item, str) and item for item in result):
        raise argparse.ArgumentTypeError("Command must be a nonempty array of strings")
    return result


def source_hashes():
    names = ["core/0.3.md", "profiles/direct-0.3.md", "profiles/durable-conversation-0.2.md", "bindings/http-message-0.3.md", "security/http-signatures-0.3.md", "schemas/direct-0.3.schema.json", "vectors/direct-signatures.json", "conformance/direct-fixture.md", "conformance/requirements.txt", "conformance/run_direct.py", "conformance/run.py"]
    return [{"path": name, "sha256": sha((ROOT / name).read_bytes())} for name in names]


def implementation_identity(argv):
    entries = []
    for argument in argv:
        path = Path(argument)
        if path.is_file():
            entries.append({"name": path.name, "sha256": sha(path.read_bytes())})
    return {"executable": Path(argv[0]).name, "entryFiles": entries}


def main():
    parser = argparse.ArgumentParser(description="Independent direct/0.3 HTTPS interoperability proof.")
    parser.add_argument("--left-command-json", required=True, type=command)
    parser.add_argument("--right-command-json", required=True, type=command)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("The test harness requires POSIX process-group cleanup; the protocol itself is OS-independent")
    directory = args.work_dir.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(directory.iterdir()):
        parser.error("Use a new or empty private work directory")
    directory.chmod(0o700)
    harness = None
    fatal = None
    initial_sources = source_hashes()
    initial_implementations = {"left": implementation_identity(args.left_command_json), "right": implementation_identity(args.right_command_json)}
    started = time.monotonic()
    try:
        harness = Harness(args.left_command_json, args.right_command_json, directory)
        harness.run()
    except CheckFailure as error:
        fatal = str(error)
    except Exception as error:
        fatal = "Harness initialization or orchestration raised " + type(error).__name__ + "; details withheld"
    finally:
        if harness:
            harness.stop()
    cases = harness.cases if harness else []
    if source_hashes() != initial_sources or {"left": implementation_identity(args.left_command_json), "right": implementation_identity(args.right_command_json)} != initial_implementations:
        fatal = "Published inputs or implementation entry files changed while the proof was running"
    failures = sum(case["status"] != "passed" for case in cases) + bool(fatal)
    report = {
        "format": "cayapa-direct-conformance-1", "coreVersion": "0.3", "profile": "direct/0.3", "binding": "http-message/0.3", "security": "http-signatures/0.3",
        "status": "passed" if cases and not failures else "failed", "generatedAt": utc(int(time.time())),
        "runtime": {"python": platform.python_version(), "cryptography": cryptography.__version__, "tls": ssl.OPENSSL_VERSION},
        "implementations": initial_implementations,
        "fixture": {"transport": "verified HTTPS on loopback", "independentOwnerKeys": True, "independentActorKeys": True, "independentTlsKeys": True, "separateStores": True, "sharedTestCaPurpose": "localhost endpoint certificates only", "nativeSendersBothDirections": True, "deterministicAfterCommitFaults": True},
        "summary": {"passed": sum(case["status"] == "passed" for case in cases), "failed": failures, "skipped": 0, "durationMs": round((time.monotonic() - started) * 1000)},
        "limitations": ["Two local implementations and bounded schedules, not every implementation or public deployment", "Receiver custody is not model consumption or execution", "Trusted manual owner pins, not global identity discovery or root-owner transfer", "Remote withdrawal remains pending until receiver commit", "No cross-operator durable-conversation replication or legacy-profile claim", "No production readiness, payment, end-to-end encryption, or dishonest-receiver guarantee"],
        "sourceHashes": initial_sources, "cases": cases,
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
