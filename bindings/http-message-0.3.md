# HTTP message binding 0.3

Identifier: `http-message/0.3`. Implements [core 0.3](../core/0.3.md) with [direct/0.3](../profiles/direct-0.3.md) and [http-signatures/0.3](../security/http-signatures-0.3.md). This is separate from the unchanged [durable HTTP binding](http.md).

## 1. Internet substrate and endpoints

Use HTTP over verified TLS, with TLS 1.2 or newer and early data disabled for mutations. The client explicitly configures the receiver origin and intended actor; it MUST verify the certificate and hostname. Redirects MUST NOT be followed for signed requests or capability reliance. No endpoint, issuer or key is fetched from a payload, identity URI or credential header. Deployments may terminate TLS at a trusted proxy only when that trust and original-target reconstruction are explicitly configured; the proof uses direct TLS endpoints.

The configured origin is canonical: lowercase `https://`, lowercase ASCII DNS name (IDNA A-labels if needed) or canonical dotted-decimal IPv4, and an optional decimal port from 1 to 65535 without leading zeros. Port 443 is omitted. There is no trailing DNS dot, path, user information, query or fragment. Literal IPv6 origins are not supported by this binding revision; DNS may resolve to IPv6. Senders and receivers reject noncanonical origins rather than silently rewriting a signed target. The following paths are exact; query strings, trailing variants and unadvertised methods are not aliases:

| Method and path | Meaning |
|---|---|
| `GET /cayapa/v0.3/capabilities` | Public profile/limit advertisement; no recipient directory. |
| `POST /cayapa/v0.3/messages` | Signed delivery of one structured CloudEvent. |
| `POST /cayapa/v0.3/delegations/revoke` | Originating owner withdraws one delegation at this receiver. |
| `POST /cayapa/v0.3/admissions/revoke` | Recipient owner withdraws one local standing admission. |

Capabilities return HTTP 200 and exactly this minimum object (unknown response properties may be ignored):

```json
{"coreVersion":"0.3","profiles":["direct/0.3"],"bindings":["http-message/0.3"],"security":["http-signatures/0.3"],"limits":{"maxBodyBytes":98304,"maxPayloadBytes":65536,"maxMessageLifetimeSeconds":86400,"maxDelegationLifetimeSeconds":900,"maxSignatureLifetimeSeconds":60}}
```

No Cayapa-operated service is contacted to interpret these identifiers. A native host can implement this contract using its own HTTP, signature and persistence libraries.

## 2. Structured CloudEvent

Reuse [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md), its [JSON format](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/formats/json-format.md) and [structured HTTP mode](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/bindings/http-protocol-binding.md). The occurrence is an actor emitting an opaque message. This binding intentionally supports one structured event only; binary mode and batches are not advertised.

`Content-Type` is exactly `application/cloudevents+json`. The UTF-8 JSON body has exactly the following ten string-valued fields, with no duplicate member names, BOM, unpaired surrogates, unknown attributes, `data`, nested values or nonstandard numbers:

```json
{
  "specversion":"1.0",
  "type":"dev.cayapa.message",
  "source":"urn:uuid:11111111-1111-4111-8111-111111111111",
  "id":"message-1",
  "datacontenttype":"application/octet-stream",
  "data_base64":"AAH/",
  "cayapaowner":"urn:uuid:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "cayapato":"urn:uuid:22222222-2222-4222-8222-222222222222",
  "cayapaprofile":"direct/0.3",
  "cayapaexpires":"2026-11-20T05:00:00Z"
}
```

| Field | Constraint |
|---|---|
| `specversion`, `type`, `cayapaprofile` | Exact values above. CloudEvents `1.0` is distinct from Cayapa/profile `0.3`. An unsupported profile returns `unsupported_profile`. |
| `source`, `cayapaowner`, `cayapato` | Absolute ASCII URI reference with a scheme, 1–512 characters, conforming to RFC 3986's `URI` production (including an optional fragment), additionally matching `[a-z][a-z0-9+.-]*:[!-~]+` and containing neither double quote nor backslash. Percent escapes must be valid. Exact identity comparisons; no normalization or dereferencing. |
| `id` | 1–128 ASCII characters matching `[A-Za-z0-9._~-]+`. Unique per source across all its emitted message intents. |
| `datacontenttype` | 1–255 printable ASCII characters conforming to RFC 9110 section 8.3.1 media-type grammar, including any parameters. Preserve its original string. It describes original payload bytes and is never an instruction to parse them. |
| `data_base64` | Canonical padded RFC 4648 standard base64; no whitespace or alternative alphabet. Empty bytes are allowed. Decoded length is at most 65,536 bytes. |
| `cayapaexpires` | Valid RFC 3339 UTC timestamp restricted to `YYYY-MM-DDTHH:MM:SSZ`, no fractional seconds or leap second. Subject to the direct profile's immutable expiry. |

`source` equals the verified delegation subject, `cayapaowner` equals its issuer, and `cayapato` equals both its audience and this endpoint's configured recipient. Context attributes are verified claims. The network route remains the configured HTTP target; the logical recipient field does not trigger forwarding.

The exact serialized UTF-8 bytes define retry equivalence in this binding. Property order or whitespace changes therefore conflict for an already accepted `(source,id)`. Retain the original bytes for retries. This deliberately avoids inventing JSON canonicalization; it does not change the different, normalized equivalence of durable 0.2.

## 3. Results

First acceptance returns HTTP **201**, `Content-Type: application/json`, and the complete [direct receipt](../profiles/direct-0.3.md#4-receipt) with `duplicate: false`. An authorized identical retry returns **200** with `duplicate: true`. Other 2xx statuses or malformed/mismatched receipts leave a client outcome unknown. Responses use `Cache-Control: no-store`.

Known request refusals use [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) `application/problem+json` with `type: "about:blank"`, `title: "Request rejected"`, numeric `status`, `coreVersion: "0.3"`, `profile: "direct/0.3"`, `outcome: "rejected"`, and the stable `code`. Do not include credential contents, payloads, stack traces or hidden identity details.

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `invalid` | Invalid UTF-8/JSON/envelope/format or unsupported input controls. |
| 401 | `unauthorized` | Missing/invalid signature, digest, delegation, owner control, timing, algorithm or attribution. Use one generic error for these identity failures. |
| 403 | `not_admitted` | Authenticated delivery lacks an active admission, or the authenticated control caller lacks the required local-owner authority. |
| 409 | `conflict` | A retained message/control identity was used for a different body. |
| 409 | `replay` | Authenticated nonce was already used. |
| 410 | `expired` | Structurally valid message has expired. |
| 413 | `too_large` | Body, payload or aggregate headers exceed the declared limit. |
| 415 | `unsupported_media_type` | Unsupported HTTP content type or content encoding. |
| 422 | `unsupported_profile` | Required core/profile behavior is not supported. |
| 429 | `capacity` | Accepting would exceed a bounded live replay/custody/ledger limit. No live guarantee may be evicted instead. |

Unknown route is 404, unsupported method is 405 with `Allow`, and malformed HTTP may be refused by the HTTP stack without a JSON problem. Clients treat all transport errors, redirects, invalid TLS, invalid 2xx results and 5xx outcomes as unknown with respect to earlier or in-flight acceptance. A 4xx refusal describes the current attempt and does not prove a prior uncertain attempt never succeeded.

No error precedence is promised when a request violates multiple rules. Authentication and current authority must precede disclosure of retained acceptance evidence; malformed input may be refused earlier without identity details.

## 4. Owner withdrawal operations

Both bodies are strict UTF-8 JSON objects of four strings, with no unknown or duplicate fields:

```json
{"issuer":"owner URI","audience":"recipient actor URI","delegation_jti":"delegation-1","request_id":"withdrawal-1"}
```

The admission path uses `admission_id` instead of `delegation_jti`. Identifiers use the message-id character/length rule; issuer/audience use the URI rule. The [owner signature](../security/http-signatures-0.3.md) authenticates `issuer`. Audience must equal this endpoint's recipient. Delegation withdrawal can target only that issuer's `jti`. Admission withdrawal additionally requires issuer to be the configured recipient owner. A grant identifier is a selector, not an authority credential.

Serialize authority withdrawal with acceptance. Persist delegation tombstones even if the token has not been seen; a later token with that issuer/jti is revoked. This version retains withdrawal tombstones and control request fingerprints until explicit local trust retirement; implementations MUST bound capacity and refuse before commit when full. Reusing `(issuer, request_id)` across either control path with different path/body is `conflict`. Exact retries use fresh nonces and return the original result with `duplicate: true`.

Successful control response: HTTP 200, `application/json`, no-store, `{ "coreVersion":"0.3", "outcome":"revoked", "scope":"receiver", "request_id":"withdrawal-1", "effectiveAt":1795147200, "duplicate":false }`. The receiver commits before responding. An unknown admission ID is treated idempotently as withdrawn without disclosing another grant; it must not be resurrected by configuration reload. Sender reconciliation preserves request ID and exact bytes. This result says only that withdrawal is effective at this receiver. No contribution body or prior history is deleted by it.

A control client recognizes withdrawal only for HTTP 200 with `application/json`, the exact core version/outcome/scope above, matching `request_id`, a nonnegative safe-integer `effectiveAt` and boolean `duplicate`. A malformed or mismatched response leaves propagation unknown. Unknown optional response properties may be ignored.

## 5. Bounds and processing

Maximum raw body is 98,304 bytes, leaving room for a base64-encoded 65,536-byte payload and bounded context. Aggregate request header names/values are limited to 16,384 bytes, calculated as the sum of each raw field-name and field-value's ISO-8859-1 byte length after removing outer SP/HTAB from the value; count duplicates individually and exclude colon/CRLF separators. Protected header values must be ASCII and may not contain CR/LF. A delegation header is at most 8,192 ASCII bytes. Reject oversized content before expensive crypto where possible. Duplicate `Host`, `Content-Type`, `Content-Length`, `Content-Digest`, `Signature-Input`, `Signature` or `Cayapa-Delegation` fields are invalid. `Content-Encoding`, `Transfer-Encoding` and trailers are unsupported for signed requests; require one decimal Content-Length matching received bytes. The signature profile forbids ambiguous target reconstruction.

Implementations use bounded queues, replay/acceptance stores, request deadlines and connections. The proof contract uses a ten-second request deadline and 65,536-byte response cap for native senders; these are client implementation limits, not a new transport. Retries are caller-controlled and bounded. The conformance [fixture contract](../conformance/direct-fixture.md) specifies test integration separately from public wire semantics.
