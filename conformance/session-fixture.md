# Host session lifecycle fixture 1

Status: frozen portable fixture interface for [`host-session/1`](../extensions/host-session-1.md). This document specifies test/control integration, not a required production CLI, remote API or communication profile. Implementers receive this contract and the standalone specification, not another lifecycle implementation or its runner.

## 1. Process and private configuration

The coordinator invokes an implementation's argv vector followed by `--config` and an absolute configuration path. It supplies one raw UTF-8 JSON request on stdin, closes stdin, reads one JSON result from stdout, and waits for exit. There is no shell expansion, prompt, daemon installation or automatic network request. Every invocation is a new process; durable state lives at the configured location.

The strict configuration object has exactly these fields:

```json
{
  "owner": {
    "id": "urn:uuid:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "keyId": "urn:uuid:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "publicKeyFile": "/private/owner-public.pem"
  },
  "statePath": "/private/session-state",
  "limits": {"sessions": 16, "intents": 8, "requests": 128},
  "testMode": true,
  "faultFile": "/private/session-fault.json"
}
```

The owner public key is Ed25519 SubjectPublicKeyInfo PEM. Supplied private keys are unencrypted Ed25519 PKCS#8 PEM in protected fixture files. Owner control checks derive the supplied private key's public bytes and compare them with the configured owner pin. Ordinary actor operations compare supplied key possession with the binding's current actor public key. No owner secret is present in configuration or supplied to ordinary operations.

The coordinator authorizes this local fixture entrance and protects its files. An implementation does not treat a pathname or an arbitrary remote request as owner authorization. Local pending access is an explicitly authorized host-custody read of staged outgoing bytes, not a grant to remote content or session memory. Reports exclude key files, credentials, private configuration, raw requests, bodies and returned identities.

On first successful `new`, bind the journal to the configured owner identifier, owner key identifier, owner public-key bytes and capacity settings. Reopening with a different owner binding or different limits reports unknown continuity; it does not reset or migrate state. State format is implementation-specific. The fixture does not inspect private storage to establish conformance.

### Bounds

| Input or resource | Fixture limit |
| --- | --- |
| Raw configuration | 16,384 bytes |
| Raw stdin | 196,608 bytes, read with a bounded cap before JSON parsing |
| Stdout | 2,097,152 bytes for the complete result |
| Entire process | 15 seconds including bounded lock contention; the coordinator enforces termination and cleanup |
| PEM key file | 4,096 bytes |
| Any absolute file path | 1–4,096 characters, no NUL |
| `limits.sessions` | Integer 1–64, total retained sessions including retired bindings |
| `limits.intents` | Integer 1–8, total retained staged intents across the entire journal |
| `limits.requests` | Integer 1–256, total retained successful owner mutation intents |

These are bounded demonstration settings, not universal production limits. Used actor-key assignments are retained and bounded by successful owner mutations; rotation consumes request capacity. No successful mutation or preparation evicts an older session, key assignment, request result or outgoing intent. Authorized exact duplicates can succeed at capacity because they allocate no new retained record.

## 2. Validation and common fields

Configuration and request objects use strict UTF-8 JSON: reject duplicate names, BOM, invalid Unicode/lone surrogates, unknown fields, nonstandard numbers and invalid types at every nested level. An optional trailing newline is part of the raw request bytes. The entire stdin must contain exactly one JSON object plus permitted JSON whitespace; property order is not normalized.

`sessionRef`, `sourceRef` and `requestId` are 1–128 ASCII characters matching `[A-Za-z0-9._~-]+`. `expectedRevision` is a positive safe integer, at most `9007199254740991`, expressed as a JSON integer token with decimal digits and no leading zero. Booleans, strings, fractions and exponent syntax are refused. Owner and key identifiers use the existing [absolute URI rule](../bindings/http-message-0.3.md#2-structured-cloudevent). File paths are literal absolute local paths, not URLs to fetch.

The `op` field is required. Each request has exactly the fields listed for its operation below. Owner administration uses `ownerPrivateKeyFile`; ordinary operations use `actorPrivateKeyFile` and MUST reject an `ownerPrivateKeyFile` field. Parse and validate shape before operation dispatch. Authentication/current control precedes disclosure of retained results.

### Common session result

Every returned session has exactly this shape:

```json
{
  "actor": "urn:uuid:11111111-1111-4111-8111-111111111111",
  "owner": "urn:uuid:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "keyId": "urn:uuid:22222222-2222-4222-8222-222222222222",
  "publicKey": "unpadded_base64url_of_32_raw_Ed25519_public_key_bytes",
  "revision": 1,
  "state": "active"
}
```

`publicKey` is canonical unpadded base64url of exactly 32 raw public-key bytes, not PEM or a private key. `state` is exactly `active` or `retired`. New and fork allocate a fresh random UUID actor as a lowercase `urn:uuid:` URI using standard platform facilities, and start revision 1. Rotation and retirement increase the revision by exactly one. An implementation must refuse rather than overflow the safe-integer range.

## 3. Owner mutation requests

Every operation in this section requires `requestId` and `ownerPrivateKeyFile` whose key matches the configured current owner pin. Supplied actor keys must differ from the owner public key and **every previously assigned actor public key in this journal**, including rotated and retired keys. Compare raw public-key bytes, not key identifiers. The requested actor key identifier must satisfy the URI rule; it is not itself proof of a key.

| `op` | Exact additional fields | Required operation |
| --- | --- | --- |
| `new` | `sessionRef`, `actorKeyId`, `actorPrivateKeyFile` | Allocate a new binding for an unused reference. A previously used reference conflicts under a fresh request ID. |
| `fork` | `sourceRef`, `sessionRef`, `expectedRevision`, `actorKeyId`, `actorPrivateKeyFile` | Authorize the active source at its current expected revision, then allocate a distinct target with the supplied new key. Source key possession is not required. Source and target references must differ, and the target must be unused. Copy no intents or authority. |
| `rotate` | `sessionRef`, `expectedRevision`, `actorKeyId`, `actorPrivateKeyFile` | Replace the active binding's key with a previously unused actor key, preserving identity and intents. |
| `retire` | `sessionRef`, `expectedRevision` | Retire the active binding without deleting its identity, keys, requests or staged bytes. |

Successful results are exactly:

```json
{"outcome":"created","duplicate":false,"session":{}}
```

Replace `{}` with the complete session shape. The `outcome` is `created`, `forked`, `rotated` or `retired` respectively. `duplicate` is a JSON boolean. Commit the binding change, uniqueness facts and request outcome atomically before returning success.

The immutable mutation input is the **entire raw stdin byte sequence**. An exact request retry under the same `requestId` recovers its original operation outcome with `duplicate: true`, without another mutation. Different bytes under that request ID return `conflict`, including changed property order, whitespace, key-file path or expected revision. This deliberately strict fixture rule is not a mandated production serializer.

For an authenticated exact recorded retry, recover before applying the expected-revision, capacity or key-reuse checks for a fresh mutation. Return the target binding's **current** session snapshot. For example, retrying creation after retirement returns `created`, `duplicate: true`, and a currently retired session at its current revision. It never reactivates the binding. A wrong/missing owner key cannot recover even an otherwise identical retained request.

## 4. Ordinary actor operations

All operations below require exactly `op`, `sessionRef`, `expectedRevision` and `actorPrivateKeyFile`, plus any listed additional field. Verify the local caller's authorized custody context, current expected revision and current actor key. No operation accepts an owner private key field, creates identity implicitly, issues delegation, changes admission or performs network I/O.

| `op` | Additional fields | Successful result |
| --- | --- | --- |
| `resume` | None | `{"outcome":"resumed","session":{}}`, with the complete active session snapshot |
| `prepare` | `bodyBase64` | `{"outcome":"prepared","duplicate":false,"id":"message-1"}` |
| `pending` | None | `{"outcome":"pending","messages":[{"id":"message-1","bodyBase64":"..."}]}` |

`resume` and `prepare` refuse retired bindings. `pending` remains allowed on a retired binding after current revision/key checks, returning only its retained staged outgoing intents. A retired key is not thereby allowed to deliver remotely or access private session memory. `pending` returns an empty array when that binding has no staged intents, preserves preparation commit order, and neither acknowledges nor deletes anything.

`bodyBase64` is canonical padded standard base64 of the exact Direct/0.3 HTTP content bytes. Its decoded size is at most 98,304 bytes. Apply the existing [closed ten-string CloudEvent contract](../bindings/http-message-0.3.md#2-structured-cloudevent), including strict JSON, exact constant fields, URI/message-ID/media-type rules, timestamp form, canonical payload base64 and the 65,536-byte decoded payload bound. `source` and `cayapaowner` must exactly match the selected binding's actor and owner. Mismatched attribution is `unauthorized`; structurally unsupported input is `invalid`.

Preparation does not check whether a structurally valid expiry is currently live, grant delivery authority or contact the destination. The existing direct receiver still enforces actual time, delegation and admission at delivery. Store the original decoded bytes without reserialization or normalization. Per binding, an identical retained message `id` and exact body return `duplicate: true`; different bytes under that ID conflict. Exact retry remains identifiable after expiry. Capacity is global across all bindings; a fork starts with no copied intents. `pending` returns the canonical standard-base64 encoding of those unchanged bytes.

Actor-key rotation permits the new current key to resume and inspect the same staged intents. The previous key fails authorization. Same-binding concurrent resumes return the same identity without claiming an exclusive process or physical-host lease. A stale expected revision conflicts even if the supplied key still matches.

## 5. Refusals and uncertainty

Successful operations exit 0 with one strict JSON result and optional trailing newline. Recognized refusals exit 1 with exactly:

```json
{"outcome":"rejected","code":"conflict"}
```

Allowed refusal codes are `conflict`, `not_found`, `retired`, `unauthorized`, `capacity` and `invalid`.

| Condition | Result |
| --- | --- |
| Invalid shape, syntax, bounds, key type or representation | `rejected/invalid` |
| Missing/unreadable/wrong supplied authority key, the owner key supplied as an actor key, or mismatched prepare attribution | `rejected/unauthorized`; never a successful resume |
| Session reference absent from an intact journal | `rejected/not_found` |
| Stale expected revision, changed mutation/message intent, reused reference or previously assigned actor key | `rejected/conflict` |
| A fresh operation requires active state but the binding is retired | `rejected/retired` |
| A fresh commit would exceed retained capacity | `rejected/capacity` |

No ordering is promised between multiple simultaneous violations, except current authentication precedes retained-result disclosure and exact authenticated mutation retry has the precedence defined above. A recognized refusal does not settle a previous unknown attempt.

Unknown outcomes exit 2 with exactly:

```json
{"outcome":"unknown","code":"continuity"}
```

Allowed unknown codes are `continuity` and `storage`. Missing whole journal for any operation other than explicit `new`, corrupt/inconsistent existing state, or mismatched retained owner/configuration binding is `unknown/continuity`. Explicit authorized `new` may initialize a missing journal but must not overwrite corrupt existing state or claim an old identity was recovered. I/O uncertainty and bounded lock contention are `unknown/storage`; retry the same immutable intent rather than assuming no commit.

A timeout, crash, nonconforming response or absent successful result is an unknown outcome at the coordinator. Implementations must not return bodies, key paths, stack traces or private diagnostics in failure results. The coordinator withholds stderr from public evidence. Parent directories, configuration and key custody must already be authorized fixture state; no remote setup or privileged escalation occurs.

## 6. Serialization and deterministic result loss

All operations open the current authoritative state under an implementation-defined serialization boundary. OS/database locks or equivalent atomic controls are valid. Lock acquisition is bounded. Do not remove a lock merely because a process is slow, a guessed timeout elapsed or a competing process wants progress. After interruption, reopen the same committed state. An uncertain busy attempt may be retried within the coordinator's finite retry budget.

When `testMode` is true, the coordinator may create `faultFile` containing exactly:

```json
{"operation":"session","phase":"after-commit"}
```

The next successful **nonduplicate owner mutation** commits durably, consumes/removes that fault, then exits 2 without writing a result to stdout. The coordinator therefore lacks the mutation outcome. Restart and exact request retry must recover the committed outcome with `duplicate: true`. Refused operations, exact duplicates and `prepare` do not consume this fault. Invalid armed fault syntax must be refused before a new mutation commits. With `testMode` false, no fault file is consulted. This is local fixture instrumentation, never a network-enabled operation.

The coordinator may separately terminate a process and restart it, copy only a public descriptor/transcript, or present a stale expected revision. Reports must distinguish those schedules from storage-device power loss or complete control-store rollback. Full copies of the authoritative store and signing keys are outside clone-detection claims; see the [contract limits](../extensions/host-session-1.md#6-copying-recovery-and-honest-limits).

## 7. Independent evidence

The suite must observe distinct new/fork addresses, stable resume, exact mutation recovery, stale/missing/retired refusal, key separation and rotation, bounded capacities, exact staged bytes, fork isolation and current local authorization. Preserve failed and skipped cases. Bind reports to the contract and implementation hashes, fixture limits, runtime and observed schedules.

Lifecycle results are separate from the existing direct wire suite. Use current owner delegation, actor signatures and independent admission for any subsequent network exchange; no local fixture result bypasses those rules. Do not count a local pending read as receiver custody, a model read, a wake, a reply or an action. No real participant, public endpoint or external publication is required by this fabricated fixture.
