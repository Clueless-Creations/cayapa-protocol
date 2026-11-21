# Direct-profile conformance fixture and independent driver contract

This is a public **test integration**, not a mandatory Cayapa runtime, CLI or administration API. A developer can adapt an existing host/operator to these process controls without importing any reference implementation. Network behavior is defined only by [core](../core/0.3.md), [direct profile](../profiles/direct-0.3.md), [HTTP](../bindings/http-message-0.3.md) and [security](../security/http-signatures-0.3.md).

## Independent implementation boundary

The suite starts two independently authored programs, each with its own persistence and independently generated owner, actor and TLS keys. A program MUST NOT import the other operator, the old Cayapa application, or a shared Cayapa codec/security/store. Standard cryptographic and networking libraries are allowed. The fixture's owner-token issuer and TLS certificate generator are test setup, not operator implementations.

The receiver process receives owner public pins only. Owner and actor private keys remain in separate fixture files available to the native sender/control process when explicitly requested. A common disposable TLS CA authenticates localhost certificates only; it does not issue owner or actor identities. No real credentials, external agents, production endpoint or Cayapa-operated service is used.

## Command adapter

The suite accepts two argv arrays, such as `["node","/path/operator.mjs"]` and `["python3","/path/operator.py"]`. It appends a command and `--config /private/config.json`. It never invokes a shell. Each adapter offers:

| Command | Interface |
|---|---|
| `serve` | Start HTTPS endpoint and open its state. Emit one JSON line `{"ready":true}` after listening. Keep serving until terminated. Content-free diagnostics only. |
| `request` | Read one JSON object from stdin, sign and send it through this implementation's native client, print one normalized result and exit. |
| `inspect` | Read the receiver's local handoff/authority store and print the observation below. This is a local recipient-consumer adapter, not a network history API. |

Request and inspect processes must observe persisted state; a different process does not share in-memory Python/JavaScript objects with the server. Only one `serve` process writes a given fixture store. A replacement server must reopen it without reapplying initial grants over persisted withdrawal.

## Private fixture configuration

All paths are absolute. The test runner owns the temporary directory and restricts secret-bearing file permissions. The minimum configuration shape is:

```json
{
  "origin":"https://localhost:18443",
  "listenHost":"127.0.0.1",
  "port":18443,
  "tlsCertificateFile":"/private/a-cert.pem",
  "tlsPrivateKeyFile":"/private/a-key.pem",
  "clientCaFile":"/private/ca-cert.pem",
  "statePath":"/private/a-state",
  "recipient":{"actor":"recipient actor URI","owner":"recipient owner URI"},
  "trustedOwners":[{"owner":"owner URI","keyId":"owner key URI","publicKeyFile":"/private/owner-public.pem"}],
  "admissions":[{"id":"admission-1","owner":"sender owner URI","actor":"sender actor URI","recipient":"recipient actor URI","scope":"cayapa:deliver","notBefore":1795147200,"expiresAt":1795233600,"active":true}],
  "limits":{"nonces":4096,"messages":4096,"controls":4096},
  "testMode":true,
  "faultFile":"/private/fault.json"
}
```

Each receiver includes its own owner pin for local admission control and the other owner's pin for delegation verification and originating-owner withdrawal. Admission validity is `notBefore <= now < expiresAt`; unknown/missing/false grants cannot accept. Initial admissions are installed only when the store is new. Nonce/message/control limits are positive integer fixture capacity limits. Ordinary defaults are 4096 entries per class, bounding the demonstration store; smaller limits allow a concrete saturation probe. Production sizing is an implementation concern and must not evade the live-retention rule.

The control limit counts unique `(issuer, request_id)` records across both control routes. Each record creates at most one withdrawal tombstone, so that projection is also bounded by this limit. An exact retry uses no new control slot; a new request ID withdrawing an already-withdrawn target does. Message limits count distinct retained acceptance records, while nonce limits count currently retained attempt records. Implementations may reclaim expired message/nonce records under the published retention rules, but may not reclaim live guarantees to pass a capacity check.

Public keys are PEM SubjectPublicKeyInfo Ed25519. Request private keys are unencrypted PEM PKCS#8 in protected fixture files. TLS keys may use an ordinary supported certificate key type. No key is derived from another operator's key or shared as an actor secret.

## Native request adapter

Standard input contains:

```json
{
  "endpoint":"https://localhost:19443/cayapa/v0.3/messages",
  "bodyBase64":"canonical base64 of exact UTF-8 request bytes",
  "delegation":"compact owner-signed JWT",
  "keyId":"actor key URI",
  "privateKeyFile":"/private/actor-key.pem",
  "nonce":"optional 32-character lowercase hex nonce",
  "created":1795147200,
  "expires":1795147260
}
```

Only endpoint, bodyBase64, keyId and privateKeyFile are mandatory; `delegation` is mandatory only for message delivery. Control requests omit it and use the control signature tag. Omitted nonce is freshly random. Omitted `created` is the current integer Unix second; omitted `expires` is `created+60`, capped by delegation expiry for delivery. Optional signature parameters support deterministic replay probes; normal callers omit them. The adapter uses the config's CA trust, verifies endpoint hostname, refuses redirects, caps response bytes at 65,536 and gives the complete request a ten-second deadline.

It MUST validate the resulting protocol outcome rather than trusting a 2xx status. Normalize stdout to one of:

```json
{"outcome":"accepted","httpStatus":201,"receipt":{"complete":"direct receipt"}}
{"outcome":"revoked","httpStatus":200,"receipt":{"complete":"control receipt"}}
{"outcome":"rejected","httpStatus":403,"code":"not_admitted"}
{"outcome":"unknown","httpStatus":0,"code":"transport"}
```

Exit codes are 0 for accepted/revoked, 1 for a recognized refusal, 2 for unknown/local configuration failure. Unknown response content is not echoed. A new request process is used for each native send, so retries cannot rely on hidden process memory. Retained exact bodies and identities belong to the caller's fixture outbox files.

The examples illustrate the normalized shapes. For `unknown`, `httpStatus` may retain an actually observed HTTP status; use `0` when no response status exists. Content-free `code` values distinguish `transport`, `response` (unusable or unrecognized response), and `configuration`. An observed HTTP status never upgrades an unvalidated response into an accepted or revoked outcome.

## Local handoff observation

`inspect` returns at least:

```json
{
  "messages":[{"bodyBase64":"exact accepted content bytes","receipt":{"complete":"original direct receipt"}}],
  "revokedDelegations":[{"issuer":"owner URI","jti":"delegation-1"}],
  "revokedAdmissions":["admission-1"]
}
```

Message order is unspecified. The adapter represents the recipient's own private handoff observation. The suite compares exact accepted payloads and counts but publishes only pass/fail facts and source hashes, never bodies, signatures, identities, token strings or paths to secrets. A message receipt alone cannot prove that a recipient model read the handoff.

## Controlled failure and concurrency

With `testMode: true` only, `faultFile` may contain `{"operation":"message","phase":"after-commit"}` or the same with `operation:"control"`. On the next successful matching mutation, the server consumes the local file, commits normally, and closes that response connection without returning headers. This is a local deterministic fault injector, never selected by a network request. It is disabled when testMode is absent/false.

The runner then stops/restarts the receiver and retries through the other native implementation. The accepted handoff or revoked authority must remain; retry returns the original result without a duplicate mutation. Failure injection is named in the evidence, not presented as natural network behavior.

For an in-flight withdrawal schedule, the runner sends part of a signed message body and holds the rest. It completes an authenticated withdrawal on another connection before finishing the body. The message must then fail the current-authority check. This tests one concrete schedule, not every possible concurrent execution. Servers must handle independent requests concurrently enough that one incomplete body cannot block all control traffic; connections/requests still need finite resource limits.

## Reproduction and reports

The standalone `run_direct.py` accepts `--left-command-json`, `--right-command-json`, `--work-dir` and `--report`. Use a new/empty private work directory. The report records specification/runner hashes, command executable identities without private arguments, exercised implementation identities, cases, failures and skips, HTTPS use, distinct keys/stores and declared limitations. At completion, ordinary error or termination, it terminates each fixture process group and reaps its direct children; orphaned descendants are reaped by their new parent. Forced termination of the entire harness is an external lifecycle responsibility.

The suite uses Python 3.11+ with the explicitly declared [conformance dependency](requirements.txt) for established cryptography, not a Cayapa SDK. This process orchestration requires POSIX process groups so successful, failed and timed-out adapters and their descendants can be stopped together. The protocol and native adopters have no operating-system requirement. Adapters stay in the foreground and MUST NOT detach into a new session to escape fixture cleanup. Captured adapter output has a 2 MiB bound and a fifteen-second outer deadline, separate from the native request's ten-second deadline. Operator dependency choices remain separate. The runner must be executable from a copied standalone protocol directory. Its adapter is a reproducible way to demonstrate implementations, not a condition that native adopters expose a CLI to end users.
