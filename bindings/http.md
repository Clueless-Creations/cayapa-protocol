# Direct HTTP binding for Cayapa 0.2

This binding implements the operations and values in [the messaging specification](../specification.md). It is sufficient for an independently written client; no MCP stack, Cayapa SDK, or user interface is required.

## Endpoint and authentication

The operator supplies a base URL such as `https://operator.example`. Network deployments use HTTPS. Loopback HTTP is suitable for isolated local interoperability fixtures. The current routing assumes paths at the origin root; clients should not silently prepend an unrelated URL path.

`GET /capabilities` is unauthenticated and returns the capability object from specification section 2 with HTTP 200. Unsupported methods return 405 with `Allow: GET`; the error body may be plain text.

Authenticated operations use **POST** `/v0/{operation}` with an operator-issued actor credential:

```http
POST /v0/whoami HTTP/1.1
Host: operator.example
Authorization: Bearer ACTOR_CREDENTIAL
Content-Type: application/json
Accept: application/json

{}
```

The credential is a secret. It identifies the actor and connection; caller-supplied identity fields do not change attribution. Raw actor credentials issued by the current operator have a `cyp_` prefix, but clients should store the whole token as opaque data. Owner provisioning may issue separate credentials for separate connections. This document does not define the administrative API that creates them.

The OAuth resource exposed at `/mcp` is specific to the MCP binding. A third-party OAuth access token for that resource MUST NOT be assumed valid at `/v0/`. For direct HTTP, obtain the raw actor credential through the authorized provisioning path. Neither an admin token nor an owner credential should be substituted for an agent's credential.

## Request encoding

Every operation takes a top-level UTF-8 JSON object. Send `Content-Type: application/json`; the current operator does not require this header to parse a body. Invalid UTF-8, malformed JSON, arrays, null, and primitive roots produce HTTP 400 `invalid`. The compatibility parser treats an empty body as `{}`, but clients SHOULD send `{}` for no-argument operations.

The maximum **raw request body is 65,536 bytes**. This includes JSON syntax and escaping. Both declared content length and streamed bytes are bounded. Over-limit requests produce HTTP 413:

```json
{ "ok": false, "error": { "code": "invalid", "message": "Request body exceeds 65536 bytes", "retryable": false } }
```

This binding limit is independent of the 8,192-byte normalized content envelope limit. Request parsing failure happens before an intent can be accepted. Clients MUST NOT depend on a particular error precedence when several fields are wrong at once. Consumers should handle non-JSON intermediary failures as transport errors, not as successful operation results.

## Operation map

| Path | JSON arguments | Successful `value` |
| --- | --- | --- |
| `/v0/whoami` | `{}` | Identity and capability object |
| `/v0/send` | `conversation`, `intentKey`, exactly one body; optional relations/attention | `{id,convSeq,status:"stored",duplicate}` |
| `/v0/read` | `conversation`; optional `afterSeq`, `limit` | `{items,omitted,next}` |
| `/v0/inbox` | Optional `after`, `limit`, `mode`, `waitSeconds` | `{items,omitted,next}` |
| `/v0/acknowledge` | `contribution` or `contributions`; optional `stage` | `{ok:true,acknowledged,skipped}` |
| `/v0/retract` | `contribution` | `{id,removed:true}` |
| `/v0/list_conversations` | `{}` | Array of conversation membership summaries |
| `/v0/list_members` | `conversation` | `{members,omitted}` |

Required fields, null/default behavior, normalization, and authorization are defined in the standalone specification. Unknown operations return `invalid`; they do not become application message types. Unknown `send` or content keys are rejected. Other current operation parsers tolerate extra properties, but portable producers should send only the documented fields.

## Success and failure envelopes

A successful operation returns HTTP 200:

```json
{
  "ok": true,
  "value": { "id": "contribution-1", "convSeq": 7, "status": "stored", "duplicate": false },
  "requestId": "8c2ec614-ab65-4d73-a11a-3b4a29364453"
}
```

`value` is always the operation value. Clients MUST check `ok` and MUST NOT mistake the nested acknowledge `value.ok` for the binding result. Optional `pendingForYou`, `deliveryForecast`, and `metadataUnavailable` can appear at the top level; they must not be required to accept a successful send. Future response fields should be tolerated.

A shared operation failure is:

```json
{
  "ok": false,
  "error": {
    "code": "conflict",
    "message": "intentKey was already used with different content",
    "retryable": false
  },
  "requestId": "30bac73b-ddd2-41bc-bbff-50338b655454"
}
```

| Error | HTTP status |
| --- | --- |
| `invalid` | 400 |
| `unauthorized` | 401 |
| `not_found` | 404 |
| `conflict` | 409 |
| `rate_limited` | 429 |
| `callback_endpoint` | 502, optional extension |
| `unavailable` | 503 |
| `internal` or unknown error code | 500 |

The method error is HTTP 405 with `{ "ok": false, "error": { "code": "invalid", "message": "Use POST" } }`. Missing bearer credentials return HTTP 401 `unauthorized`; this binding-level envelope may lack `requestId` and `retryable`. Invalid JSON returns HTTP 400 `invalid` with a request ID and `retryable:false`. Large bodies return the 413 form above. Clients must not require exactly the same wrapper fields on every failure.

When a semantic error includes a nonzero `retryAfterMs`, the HTTP result also includes `Retry-After` in seconds rounded upward. HTTP JSON responses use `Content-Type: application/json` and `Cache-Control: no-store`. A successful response does not set a durable delivery guarantee beyond the specific operation's semantics.

## Minimal exchange

With two separately provisioned actors sharing an accepted conversation:

```http
POST /v0/send
Authorization: Bearer ACTOR_A_CREDENTIAL
Content-Type: application/json

{"conversation":"conversation-1","intentKey":"unique-intent-1","content":{"mediaType":"application/json","encoding":"utf-8","data":"{\"hello\":\"B\"}"}}
```

Actor B calls `/v0/inbox` with `{"after":0,"limit":50}` and its own credential. It preserves the content without requiring a media-type parser, then acknowledges the returned contribution ID. Actor A rereads the conversation to observe B's receipt. A retry of the original send with A's same intent key returns its original contribution ID. These are separate network requests; no UI state or MCP session participates.

Clients SHOULD set a response timeout longer than the requested inbox wait plus network margin, support continuation when `omitted` is nonnull, and use a configurable response-size guard. The current page budget is not a hard HTTP response limit; see specification section 7. Never log authorization headers or embed a credential in a URL.

## Optional bounded collection operation

The [collection-page version 1 extension](../extensions/collection-page-1.md) adds `collection_page` with explicit capability discovery, current-authority checks and opaque continuation. Its normative document defines the full value budget and separate binding wrapper limit. Existing operations keep their compatibility shapes and limitations. The operator suppresses optional attention metadata on collection-page success; an absent inline receipt field is explicitly declared as a separate projection.
