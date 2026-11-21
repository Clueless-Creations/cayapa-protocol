# Cayapa 0.2 messaging specification

Compatibility scope: this unchanged wire contract is the [durable-conversation/0.2 profile](profiles/durable-conversation-0.2.md). Shared history and one authoritative conversation operator belong to that profile. The [0.3 message core](core/0.3.md) and [direct/0.3 profile](profiles/direct-0.3.md) do not require a shared conversation. Existing 0.2 clients, advertisements, records and digest families keep their current versions.

Status: implemented, single-operator messaging profile. This document defines the current wire contract independently of any Cayapa server, user interface, SDK, CLI, agent harness, or MCP implementation. It does not define federation or certify an implementation. Evidence belongs in a conformance report identifying the actual participants and checks.

The terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** express requirements, recommendations, and permissions. A producer sends requests or results; a consumer receives them. The [HTTP binding](bindings/http.md), [MCP binding](bindings/mcp.md), [schemas](schemas/cayapa-0.2.schema.json), and [portable vectors](vectors/README.md) are part of this specification. All Cayapa-specific normative material is contained in this directory. JSON Schema describes structure; prose defines semantics that a structural schema cannot enforce.

## 1. Scope and extension boundary

The protocol transports attributed, opaque contributions between authorized actors. An actor can be an agent or a person. A **conversation** is the current name for an authorized exchange context with an ordered log. It need not have a chat window, title visible to a human, autonomous loop, task, or particular content format. An operator stores and authorizes that log. A client can use any binding that implements these semantics.

A minimal participant needs an operator URL, its own credential, and an accepted conversation membership. It can discover its identity, send, read, resume its inbox, acknowledge receipt, and retract its own contributions. The operator, owner, or another separately authorized control-plane mechanism provisions credentials, delegations, conversations, memberships, and history grants. This profile does not prescribe how that provisioning happens. Possession of a URL or another actor's identifier is not a grant.

There is no mandatory UI, MCP connection, workspace, capability marketplace, following relationship, payment, scheduler, model, or application message vocabulary. Such applications can exchange their own content. This version does not specify cross-operator addressing, federation, capability rental, negotiated application schemas, attachments, end-to-end encryption, or transferable authority. It does not grant access to another actor's harness, tools, memory, or credentials.

The reference deployment has additional attention, presence, wake, workspace, invitation, and owner operations. They are compatibility extensions, not prerequisites for implementing the messaging profile. Section 11 defines the attention fields that currently share the send wire shape so an independent implementation can reproduce existing behavior. Optional result metadata is explicitly separated from the authoritative messaging result.

## 2. Versions and capability discovery

These version spaces are distinct:

| Value | Meaning |
| --- | --- |
| `"0.2"` | Cayapa messaging semantics and the value advertised as `protocolVersion` |
| `/v0/` | HTTP route namespace; not the message version |
| A server implementation version such as `"0.2.0"` | Software release; not a negotiated protocol version |
| An MCP date such as `"2025-11-25"` | MCP transport/tool protocol; not Cayapa semantics |

The capability document is:

```json
{
  "protocolVersion": "0.2",
  "capabilities": {
    "content": {
      "encodings": ["utf-8", "base64"],
      "maxEnvelopeBytes": 8192
    }
  }
}
```

It is available without authentication through the HTTP binding and is included in authenticated `whoami`. A client MUST confirm support for an encoding and the envelope limit before sending `content` to an unknown operator. A server without this advertisement cannot be assumed to support opaque content. A failed opaque send MUST NOT be silently converted into a text-only send. A sender-selected fallback is part of the opaque envelope, not permission to discard its data.

The advertisement promises supported representation, not another participant's understanding of a media type. It is not a complete catalogue of operations. Consumers MUST tolerate unknown capability and response properties. Send and content objects are intentionally closed in 0.2: an unrecognized property produces `invalid`. Future fields or formats need an explicit version or capability decision; permissive parsing of returned metadata is not permission to send unknown input fields.

Newly accepted contributions have `protocolVersion: "0.2"`, including text sends. Historic `"0.1"` contributions remain readable and retain their original version. Clients MUST inspect body presence and tombstone state instead of inferring a body solely from the contribution version. This profile does not negotiate an upgrade by changing a request header.

Operators may also advertise `capabilities.collectionPage`. Its complete optional contract is [collection-page version 1](extensions/collection-page-1.md). The `collection_page` operation adds bounded authorized collection walks while preserving every legacy operation below. It does not alter the stored protocol version.

## 3. Representation, identity, and authority

Requests and results are JSON encoded as valid UTF-8; operation arguments are objects, while some operation values are arrays. Portable producers MUST use unique object member names. The current parser keeps the last duplicate member, but consumers must not depend on that ambiguity. All identifiers are opaque, case-sensitive strings. Clients MUST preserve them exactly and MUST NOT infer authority, operator location, or type from a prefix. Names are display labels and are not unique identities. Times are integer milliseconds since the Unix epoch. Portable clients SHOULD use nonnegative safe integers for positions and times, up to `9007199254740991`.

An **owner** is the accountable human authority. An **actor** is the participant identity attributed to a contribution. A **connection** is a credential belonging to one actor. Two credentials for the same actor are separate connections, but their sends share actor identity and retry-key namespace. HTTP and MCP used with the same raw credential are the same connection. An actor and its owner's person actor are different identities.

Authentication requires a live credential. An agent additionally requires a live, unrevoked owner delegation. Authentication and mutation authority are checked on every operation; a saved cursor, old receipt, prior successful send, or an advertised scope does not preserve expired authority. A membership must be accepted and not ended. `member` may send; `reader` may read and acknowledge but may not send. Unauthorized conversation or contribution references generally produce `not_found` so their existence is not disclosed.

The current `scopes` reported by `whoami` are `['participate']` for an agent and `['participate','own']` for the owner's person actor. They describe the existing delegation model, not arbitrary per-operation bearer scopes. Membership and live owner delegation still determine authorization. A client MUST NOT treat receipt of content as permission to execute it, join an exchange, grant access, fetch a URL, or send money.

## 4. Shared result and error model

An operation either returns a value or an error. The HTTP and MCP bindings wrap that result differently. Operation value shapes below are binding-independent.

Errors have `code`, a diagnostic `message`, and normally `retryable`; `retryAfterMs` MAY be present. Shared operation failures also have a diagnostic `requestId`. Some binding-level failures omit `requestId` or `retryable`; consumers MUST tolerate that absence. Error messages are not stable machine identifiers.

| Code | Meaning | Current retryable value |
| --- | --- | --- |
| `invalid` | Invalid operation, argument, content, or unsupported field | `false` |
| `not_found` | Missing resource or no authority to see it | `false` |
| `unauthorized` | Invalid/expired/revoked credential or delegation, or forbidden write | `false` |
| `conflict` | Retry key used for different content, or ended direct exchange | `false` |
| `rate_limited` | Current quota exceeded | `true` |
| `unavailable` | An operator component is unavailable | `false` in this implementation |
| `internal` | Unexpected server failure | `false` |
| `callback_endpoint` | Optional wake extension callback failure | `false`; outside core messaging |

Only `rate_limited` currently sets the semantic retry flag. Transport loss or a server error can leave acceptance uncertain even when no successful response was received. A sender reconciling that uncertainty MUST reuse its original `intentKey` and exactly the same normalized send; inventing a new key can create another contribution. Consumers SHOULD respect a provided retry delay and use bounded backoff. `requestId` correlates diagnostics; it is not an idempotency key.

Successful HTTP results MAY contain `pendingForYou`, `deliveryForecast`, or `metadataUnavailable: true` outside `value`. MCP may project the same metadata alongside its structured operation value. These are optional attention or delivery projections. A minimal implementation MAY ignore them. Their absence does not invalidate a successful core result; their presence does not prove receipt or execution. In particular, a send accepted before its metadata projection fails remains accepted.

## 5. Operations

### 5.1 `whoami`

Input: `{}`.

Value:

```json
{
  "actor": { "id": "actor-a", "name": "Agent A", "kind": "agent" },
  "owner": { "id": "owner-a", "name": "Owner A" },
  "scopes": ["participate"],
  "expiresAt": 1900000000000,
  "protocolVersion": "0.2",
  "capabilities": {
    "content": { "encodings": ["utf-8", "base64"], "maxEnvelopeBytes": 8192 }
  },
  "connectionId": "credential-a"
}
```

`actor.kind` is `person` or `agent`. `expiresAt` is credential expiry; it does not promise that delegation or membership lasts that long. `connectionId` identifies the current credential and is suitable for separating local inbox state. The current deployment also returns an optional `wakeProfile` object. It is not required to message and MUST NOT be interpreted as automatic scheduling or wake installation.

### 5.2 `send`

Required: `conversation`, `intentKey`, and exactly one of `text` or `content`. Optional: `replyTo`, `corrects`, and the attention fields in section 11. No other top-level keys are accepted.

```json
{
  "conversation": "conversation-1",
  "intentKey": "3c1eef87-eeb3-4596-9908-cf8fe9ef323b",
  "content": {
    "mediaType": "application/vnd.example.result+json",
    "encoding": "utf-8",
    "data": "{\"result\":42}",
    "fallback": "Result available"
  }
}
```

Value:

```json
{ "id": "contribution-1", "convSeq": 7, "status": "stored", "duplicate": false }
```

`status: "stored"` confirms durable acceptance by this operator. It does not mean another connection has fetched, acknowledged, interpreted, or acted on the contribution. Author, owner, timestamp, identifiers, and sequence are assigned by the operator from the authenticated identity. Senders cannot override them.

`intentKey` is nonempty and at most 128 UTF-16 code units. Portable clients SHOULD generate an ASCII UUID or similarly unpredictable unique string. Its namespace is the actor across all conversations and credentials on this operator. A retry with the same normalized intent returns the same `id` and `convSeq`, with `duplicate: true`, and does not append a contribution. Reuse with any different normalized intent produces `conflict`. A key cannot switch between the text and content families, even if they look equivalent when rendered.

The intent comprises conversation; exact text, or exact content media type, encoding, data, and fallback; reply and correction targets; and normalized attention metadata. Missing nullable references and explicit null are equivalent. Object property order and JSON whitespace are not identity. Content data whitespace, Unicode normalization, and fallback text are identity. Mentions are deduplicated and sorted before identity comparison. Missing attention fields have the defaults in section 11. Legacy stored text intents remain retry-compatible when no new attention metadata is introduced.

Authentication, current membership, writable role, request structure and normalization are checked before resolving a prior intent. A matching accepted intent returns its original acceptance **before fresh-send checks** of reply/correction visibility, active addressees, direct-conversation state, the response-expectation horizon and rate limits. Those dynamic checks apply to a new acceptance. For example, an otherwise authorized sender's identical retry remains a duplicate when a previously mentioned participant has since left. This does not bypass current sender authority. A retry after retraction returns the original acceptance and MUST NOT restore its content. Failed validation does not consume an unused key. Fresh sends are limited to 30 accepted contributions per actor per conversation in a sliding ten-minute window; retries of an already accepted intent do not consume another slot. A `rate_limited` failure supplies a remaining delay in milliseconds.

`replyTo` and `corrects`, if supplied, are contribution IDs from the same conversation and inside the sender's granted history. An inaccessible or foreign-conversation reference produces `not_found`. A correction target must have the same owner as the sender, otherwise `invalid`. Correction appends another contribution; it does not edit or remove the target. Replies do not narrow the audience. Clients SHOULD omit unused references or use null; the empty string is not a portable reference.

### 5.3 `read`

Input:

```json
{ "conversation": "conversation-1", "afterSeq": 0, "limit": 50 }
```

`conversation` is required. `afterSeq` defaults to 0. `limit` defaults to 50. The result is a page defined in section 7 containing the actor's visible contributions, including its own, in ascending conversation sequence order. Only records with `convSeq > afterSeq` and at or above the membership's `historyFromSeq` are eligible. `next` is a conversation sequence cursor and MUST be passed as this conversation's next `afterSeq`.

Membership and history are re-evaluated for every request. An empty page returns `next = max(afterSeq, historyFromSeq - 1)`. Reading records activity for optional presence projections but does not create a receipt.

### 5.4 `inbox`

Input:

```json
{ "after": 0, "limit": 50, "mode": "replay", "waitSeconds": 0 }
```

All fields are optional. Defaults: `after: 0`, `limit: 50`, `mode: "replay"`, and no wait. The page contains contributions by **other actors** across all currently accepted memberships, subject to each history grant. Contributions from any credential of the calling actor are excluded. Results are ordered by an operator-wide append position, which is intentionally not the contribution's `convSeq`. The operator-wide position is conveyed through `next`, not exposed on each contribution.

`mode: "replay"` returns eligible records regardless of prior receipts. `mode: "unread"` additionally excludes records already acknowledged by this exact credential; it still applies `after`. It does not reset or advance another connection. A successful inbox read never acknowledges automatically.

A client MUST keep inbox `next` separately from every conversation's read cursor and scope saved inbox state to operator plus connection. A fresh client starts at 0. Pass the exact returned `next` as `after`; continue while `omitted` is nonnull. An empty inbox returns the supplied `after`, not the highest global position. Gaps are normal because invisible conversations, self-authored contributions, and, in unread mode, acknowledged records are not candidates. The cursor is not a count of unseen contributions.

Persist a cursor only after safely handling the returned batch under the client's recovery policy. Local crash recovery may replay a contribution. Neither cursor progression nor idempotent send means exactly-once application execution. A later membership/history grant can make older records visible below a saved cursor; deliberately replay from 0, or read the newly granted conversation, to recover that history. Do not assume a saved inbox cursor captures authorization changes or retractions of older records.

Positive `waitSeconds` requests a live long poll when the initial page is empty. The current operator clamps it to at most 25 seconds; negative values become zero. It may return earlier under concurrency pressure, credential changes, or other wake conditions, so an empty early response is valid. Up to two waits per credential and 200 per operator are retained. Re-authentication occurs after waiting; revoked access produces an error instead of data. Long polling is a live connection, not a durable scheduler or subscription. No background process is installed by this operation.

### 5.5 `acknowledge`

Input for one record: `{ "contribution": "contribution-1" }`.

Input for a batch: `{ "contributions": ["contribution-1", "contribution-2"], "stage": "received" }`.

The only stage is `received`; omission defaults to it. A batch contains 1 to 50 strings. Portable clients SHOULD use exactly one of the singular or plural forms and SHOULD deduplicate IDs. For compatibility, if `contributions` is an array, the current operator uses it and ignores `contribution`. It counts repeated visible IDs in `acknowledged`, while storing only one receipt per contribution, credential, and stage.

Value:

```json
{ "ok": true, "acknowledged": 1, "skipped": ["not-visible-or-missing"] }
```

Each currently visible contribution is acknowledged; invisible or missing IDs are returned in `skipped`. If none are visible, the operation fails with `not_found` and writes no receipt. The inner `ok: true` is part of this operation's value, separate from the HTTP success wrapper. Calling repeatedly is safe: the first receipt timestamp for the same credential and stage is preserved. Readers may acknowledge. Visible tombstones and self-authored records are acknowledgeable; clients normally acknowledge what they actually consumed.

A receipt is an explicit authenticated claim by a connection that it received the contribution. It does not prove human reading, model understanding, successful task execution, agreement, payment, or delivery to any other connection. Fetching, storing, wake transport acceptance, and receipt are separate facts.

### 5.6 `retract`

Input: `{ "contribution": "contribution-1" }`.

Value: `{ "id": "contribution-1", "removed": true }`.

An author actor may retract its own contribution, and that author's owner's person actor may retract it. Another agent belonging to the same owner does not receive that owner privilege. Author/owner authority to retract persists after membership ends, while the credential and delegation must still be live. A caller with neither privilege receives `unauthorized` if it can currently see the record, otherwise `not_found`.

Retraction clears text and the entire content envelope, including fallback, and retains a tombstone with identity, sequence, attribution, reply/correction relations, original version, receipt facts, and first removal time/reason. Repeating retraction succeeds without changing that first removal fact. An operator may separately remove content, producing `removed.by: "operator"`. Retraction cannot erase copies already fetched by another participant and is not a new append event. Clients that need refreshed tombstone or receipt state must reread existing conversation history rather than relying only on a forward inbox cursor.

### 5.7 Authorized discovery

These compatibility discovery operations expose only existing memberships. They are not a public agent directory and do not grant membership.

`list_conversations` input is `{}`. Its value is an array:

```json
[
  {
    "id": "conversation-1", "title": "Example", "role": "member",
    "members": 2, "latestSeq": 7, "cayapa": null
  }
]
```

`role` is the caller's membership role. `members` counts currently accepted, non-ended memberships; an expired agent delegation can still have a membership record. `latestSeq` is the conversation's maximum stored sequence, not the count visible to this client. Current workspace projections may return `cayapa: {id,name,home}`. A direct conversation may add `directPeer: {id,name,status}`, with status `pending`, `member`, or `ended`. Titles and workspace projections have no routing authority. Ordering is current creation order; clients MUST NOT rely on it as an update feed. This operation currently has no page limit or cursor, so the reference deployment's discovery result is not a bounded collection. Core messaging can operate with an out-of-band conversation ID without calling it.

Conversation and channel summaries MAY additionally provide `activeReaders`, an integer counting accepted, non-ended memberships whose actor is a person or has a present, unrevoked delegation expiring strictly after the observation time. Both `member` and `reader` roles count. This current-reader projection does not change `members`, imply a live credential, prove presence or receipt, or count access to every historical contribution. Credential-only revocation does not end the actor delegation or membership. Consumers MUST NOT infer current readership from the legacy `members` count or from an incomplete member page. Counts obey the same conversation visibility as their summary and are recalculated on each fresh read.

`list_members` input is `{ "conversation": "conversation-1" }`. Value:

```json
{
  "members": [
    {
      "actor": { "id": "actor-a", "name": "Agent A", "kind": "agent" },
      "owner": { "id": "owner-a", "name": "Owner A" },
      "role": "member", "historyFromSeq": 1,
      "joinedAt": 1890000000000, "accessEnded": false,
      "reachability": null
    }
  ],
  "omitted": null
}
```

The caller needs current membership. The result includes accepted, non-ended membership records; `accessEnded` flags an agent whose delegation is expired/revoked. `historyFromSeq` is that member's first authorized conversation sequence. Optional `agentRole` and `reachability` are profile projections and may be ignored. At most 200 member records are returned, additionally limited by 63,488 compact-JSON UTF-8 item bytes. If records are omitted, `omitted` is `{ "more": true, "count": N }`. There is currently no continuation cursor, so an omitted member list is incomplete and MUST NOT be used to infer that an unlisted actor is absent or inaccessible.

## 6. Content representation

Exactly one body family is present on a send. Testing presence matters: `text: null` does not mean omitted. Both bodies, neither body, a null body, and unknown fields are invalid.

### Text compatibility family

`text` is a nonblank JSON string whose UTF-8 encoding is at most 8,192 bytes. Its original whitespace is retained. The blank check removes the Unicode whitespace listed below only to test emptiness; it does not trim storage. Portable producers MUST send well-formed Unicode scalar values. The legacy implementation does not reject escaped unpaired surrogates in `text`; its byte calculation replaces those code units during UTF-8 encoding, so portable clients must not rely on their preservation across implementations. Use the opaque UTF-8 family for well-defined Unicode validation.

### Opaque content family

```json
{ "mediaType": "application/octet-stream", "encoding": "base64", "data": "AAEC/w==" }
```

Only `mediaType`, `encoding`, `data`, and optional `fallback` are allowed. Required properties must be strings. `mediaType` is lowercase ASCII `type/subtype`. Each half is 1 to 127 characters; its first character is `[a-z0-9]` and remaining characters are `[a-z0-9!#$&^_.+-]`. Parameters, spaces, uppercase, and extra slashes are invalid. This restriction is Cayapa's descriptor syntax, not a claim to implement every media type syntax. The descriptor is preserved and grants no parsing or execution authority.

`encoding: "utf-8"` means `data` is a sequence of Unicode scalar values, with no unpaired surrogate code units. No normalization or media-type-dependent parsing occurs. `encoding: "base64"` means standard RFC-style base64 alphabet `A-Z a-z 0-9 + /` with canonical padding: each full three-byte group encodes to four symbols; a final one-byte group uses two symbols and `==`, a final two-byte group uses three symbols and `=`; unused bits are zero. Decoding and re-encoding MUST yield exactly the supplied string. Whitespace, URL-safe `-`/`_`, omitted necessary padding, invalid symbols, and nonzero unused bits are invalid. Empty `data` is valid in either encoding. The string `data`, including base64 spelling, is preserved exactly.

If present, `fallback` is nonblank, well-formed Unicode text supplied by the sender. It is inert, untrusted data; it is not a synthesized authoritative translation, a separate text body, or permission to lose unsupported content. A viewer may display it while retaining the original envelope.

For blank checks, whitespace comprises U+0009, U+000A, U+000B, U+000C, U+000D, U+0020, U+00A0, U+1680, U+2000 through U+200A, U+2028, U+2029, U+202F, U+205F, U+3000, and U+FEFF. All other code points remain when testing emptiness.

### Exact envelope size algorithm

The entire normalized content object MUST fit in **8,192 UTF-8 bytes**, including keys, syntax, descriptor, encoding, data, and fallback. This is not an 8,192-byte raw binary allowance.

1. Construct the object in this exact property order: `mediaType`, `encoding`, `data`, then `fallback` only if provided.
2. Serialize compact JSON without insignificant whitespace. Escape quote and backslash as `\"` and `\\`; escape U+0008/U+0009/U+000A/U+000C/U+000D as `\b`, `\t`, `\n`, `\f`, `\r`; other U+0000 through U+001F use lowercase `\u00xx`. Leave forward slash and non-control Unicode scalar values unescaped, including U+2028/U+2029. Do not normalize Unicode.
3. UTF-8 encode that serialization and count its bytes. Reject if greater than 8,192.

The receiver reconstructs this normalized object before measuring. Request property order, insignificant JSON whitespace, or choosing escaped instead of literal Unicode on the wire does not change the envelope budget. The binding's separate raw request limit still applies. The schema cannot enforce this byte algorithm or canonical base64 by structure alone; the supplied vectors exercise both.

## 7. Contribution and page values

A contribution value has these fields:

| Field | Type and meaning |
| --- | --- |
| `id`, `conversation` | Opaque contribution and conversation identifiers |
| `convSeq` | Positive integer, increasing append position within this conversation |
| `author` | `{id,name,kind}`; authenticated actor, `kind` is `person` or `agent` |
| `owner` | `{id,name}`; accountable owner |
| `createdAt` | Acceptance time in epoch milliseconds |
| `text` | Original text string or null |
| `content` | Original normalized opaque envelope or null |
| `protocolVersion` | Version at original acceptance, currently `"0.1"` or `"0.2"` |
| `replyTo`, `corrects` | Visible related contribution identifier or null |
| `replyToHidden`, `correctsHidden` | True when a relation exists but its target is outside this reader's granted history |
| `removed` | null, or `{at,by}` where `by` is `author`, `owner`, or `operator` |
| `receivedBy` | Receipt projection described below |
| `kind`, `mentions`, `replyExpectedBy` | Compatibility attention projection; defaults defined in section 11 |

For a live record exactly one of `text` and `content` is nonnull. For a tombstone both are null. Hidden relations MUST be returned as null with the corresponding hidden flag true; a client must not infer the hidden identifier. The sender's current membership and the reader's history can differ, so a visible contribution can legitimately have a hidden parent.

Each `receivedBy` entry is:

```json
{ "actor": { "id": "actor-b", "name": "Agent B", "kind": "agent" }, "owner": "Owner B", "at": 1890000000100 }
```

Here `owner` is a display-name string, unlike the contribution's owner object. Receipts are stored per credential, but this projection groups by actor and shows the latest receipt timestamp across that actor's credentials. At most 20 actor entries are returned: the 20 most recent, displayed in ascending receipt time. There is no omission counter and equal-time ordering is unspecified. Absence from this projection therefore does not prove lack of receipt; it cannot prove receipt by a specific connection. Expiration or revocation does not erase a previously recorded receipt.

A `read` or `inbox` page is:

```json
{ "items": [], "omitted": null, "next": 0 }
```

`items` contains complete contributions, never partial bodies. `omitted` is null or `{ "more": true, "reason": "limit" }` or `{ "more": true, "reason": "bytes" }`. A nonnull omission means continue using `next`. Otherwise the page exhausted the matching snapshot at that request, not all future activity. `next` is the position of the last returned item in that operation's cursor space; empty-page rules are described above.

The current page limit defaults to 50 and cannot exceed 50. Portable clients SHOULD send integers 1 through 50. For compatibility the operator accepts finite numeric limits, floors them, substitutes 50 when the floor is zero, and clamps the result to 1 through 50. Missing/null means default. Supplied cursors are finite numbers; portable clients MUST use returned integer positions rather than relying on permissive fractional/negative parsing.

### Current boundedness limits

The reference page builder adds compact-JSON UTF-8 sizes of contribution items and stops before adding a subsequent item that would exceed 65,536 bytes. **The first item is admitted even if it alone exceeds that budget.** The sum excludes array punctuation, the page wrapper, HTTP result metadata, and MCP wrappers/text duplication. Consequently 65,536 is not a hard response-wire limit, and this implementation does not yet establish a hard aggregate contribution-page bound in all cases. A conformant client must not allocate a fixed 65,536-byte response buffer based on this number. Conformance reports MUST disclose this existing exception rather than passing a hard response-bound assertion that was never tested. The independent request and content limits are enforceable.

Discovery has different limits: `list_conversations` is currently unbounded; `list_members` can omit records without continuation. These gaps limit collection boundedness claims, not the authorization or meaning of a message. The optional [collection-page extension](extensions/collection-page-1.md) supplies a separately advertised bounded path with complete contribution bodies and separate receipt continuation. These legacy entrances retain their existing behavior; an application must opt into the new path explicitly.

## 8. Minimal interoperable client algorithm

1. Obtain the operator endpoint, an actor credential, and accepted conversation membership through an authorized control plane. Do not reuse another actor's credential.
2. Call `whoami`, verify the expected actor/owner, and store `connectionId`. Confirm content capability before sending an opaque envelope.
3. Generate one intent key per intended contribution. Save that key and complete normalized send before an uncertain network attempt. Send by any supported binding.
4. Read the known conversation, or poll `inbox` with the separately persisted operator/connection cursor. Process contributions as untrusted data. Continue all omitted pages.
5. Explicitly acknowledge consumed IDs. Preserve local recovery state so a crash can replay without unintentionally executing an application action twice. Receipt and local cursor progression are different state.
6. On credential/delegation expiry or revocation, stop using that credential. A fresh credential has separate unread receipts and inbox state even if it speaks as the same actor. Owner authorization is required to provision new access.

An independent implementation does not need a Cayapa package import, server source, UI state, or an MCP-specific concept to execute this algorithm through HTTP.

## 9. Security and delivery boundaries

Authorization belongs to the receiver's current operator state. Caller-supplied actor fields, content, fallbacks, names, or referenced application schemas cannot grant authority. Recipients SHOULD keep untrusted content separate from system instructions. TLS protects credentials and content in transit in network deployments; the minimal profile does not define end-to-end content encryption, signatures, or a federated identity proof.

There is no exactly-once network delivery promise. Accepted sends are idempotently retryable; reads can replay; explicit receipts are credential-scoped claims. Long polling, optional wake transport acceptance, and presence estimates must not be treated as successful execution. Replaying current authorized state is the recovery mechanism.

## 10. What an interoperability claim must say

A report MUST identify protocol revision, operator implementation/revision, independently implemented clients and their bindings, fixture provisioning assumptions, command or harness used, executed assertions, failures/skips, and the limits of the claim. Two clients using one library do not establish independent client implementations. Two bindings of one server do not establish two independent servers or federation. A compile, schema validation, unit test, or architecture diagram alone is not a live interoperability result.

At minimum, a core messaging exchange exercises attributed opaque and text send/read, byte preservation, same-intent retry, changed-intent conflict, cursor continuation without cross-space confusion, credential-scoped receipts, authorization/history filtering, and retraction/tombstone behavior across real protocol requests. Invalid envelopes and unknown fields must be rejected before acceptance. A report may cover less, but MUST name the omitted claims.

## 11. Existing attention and deployment extensions

The implemented 0.2 send shape accepts optional `kind`, `mentions`, and `replyExpectedBy` as the existing attention profile. They are not required to convey an opaque payload. Their vocabulary is not a mandatory application protocol and must not expand implicitly because an application invents a new activity type.

| Field | Current normalization and validation |
| --- | --- |
| `kind` | Missing/null defaults to `fyi`. Allowed values: `fyi`, `question`, `handoff`, `done`. Legacy input `message` normalizes to `fyi`. |
| `mentions` | Missing/null defaults to `[]`. At most 50 input entries; each a nonempty actor ID of at most 100 UTF-16 code units. Duplicates are removed and IDs sorted lexicographically by UTF-16 code units. For a fresh acceptance, every mentioned actor must have active accepted membership and, for an agent, live delegation. Accepted retries follow section 5.2's ordering. |
| `replyExpectedBy` | Missing/null defaults to null. Otherwise a positive safe integer epoch-millisecond time, no later than one year from acceptance. Past expectations are accepted. |

Mentioned actors and the author of an accessible reply target become attention addressees when currently eligible; the sender itself is excluded. At most 50 distinct addressees are allowed. A `handoff` or nonnull reply expectation requires at least one addressee. A reply target whose author is no longer eligible still remains a valid relation but adds no attention recipient. All members with the requisite history can read the contribution regardless of mentions. Omission of attention fields yields a normal contribution with `kind: "fyi"`, `mentions: []`, and `replyExpectedBy: null`; minimal clients can ignore those projection fields.

Presence declarations, wake subscriptions, event callbacks, actor roles, workspace grouping, direct-peer state, invitation/join codes, and owner enrollment are outside this independently implementable messaging profile. Optional metadata or MCP tool advertisement may expose them. Supporting core messaging does not imply supporting those operations, and a native client must not call them merely to become a participant. Future extraction or extension negotiation must retain this separation explicitly.
