# Portable Cayapa 0.2 vectors

These data files are independent of the reference server and its programming language. They exercise the contract in [the specification](../specification.md) through either [HTTP](../bindings/http.md) or [MCP](../bindings/mcp.md). They are inputs for a conformance run, not evidence that a run happened. Keep actual credentials and generated actor/conversation IDs out of committed vector data.

## Literal send-body cases

[`content.json`](content.json) has this format:

```json
{
  "format": "cayapa-content-vectors-1",
  "protocolVersion": "0.2",
  "cases": [
    {
      "id": "content-empty-utf8",
      "sendBody": {
        "content": { "mediaType": "application/octet-stream", "encoding": "utf-8", "data": "" }
      },
      "accepted": true,
      "envelopeBytes": 69
    }
  ]
}
```

`sendBody` is a literal fragment of a `send` argument object. It deliberately may contain invalid data or an unknown field. Do not filter, repair, normalize, truncate, or remove those fields before exercising the operator. Add a valid `conversation` and a unique `intentKey` for the executing actor to form the complete request. Each case's diagnostic `id` is not an operator identifier.

For `accepted:true`, require a successful stored result, then read that contribution through the other tested binding and compare the body exactly with `sendBody`. Compare strings after JSON decoding, not raw response JSON escaping or object property order. The stored opposite body family must be null. `envelopeBytes`, when present, is the expected size of the normalized content object using specification section 6's compact JSON algorithm. A text body's raw byte limit is separate.

For `accepted:false`, require semantic code `invalid`, no stored contribution, and no successful send receipt. The `errorCode` field names that expected code. Error message wording and diagnostic request IDs are not fixed. Replacing the invalid body with a valid one under the same unused key can prove rejection did not consume the intent. The repaired send is an additional accepted contribution and must be considered when arranging rate-limit fixtures.

An optional future `normalized` field will mean the full normalized send-body fragment (`{"content":...}` or `{"text":...}`), not the content object by itself. It is absent in this version because accepted fragments already have the expected normalized values.

There are 42 literal cases: 12 accepted and 30 rejected. They include:

- Text preservation, blank rejection, and exact 8,192/8,193-byte boundaries.
- Empty opaque payloads, Unicode, JSON control escaping, and a media type whose data is intentionally not parsed.
- Canonical base64 for full and partial groups, and rejection of missing/excess padding, URL-safe alphabet, whitespace, and nonzero padding bits.
- Exact normalized 8,192/8,193-byte content-envelope boundaries.
- Unknown fields, ambiguous bodies, null/array/primitive values, unsupported encodings, and invalid descriptors.
- Unpaired-surrogate rejection for opaque UTF-8 data and fallback, plus blank fallback rejection.

Use separate fixture conversations or actors if repairs and repeated binding runs would exceed the current 30 fresh sends per actor per conversation per ten minutes. Do not change an expected result to accommodate rate limiting; report the setup problem and rerun with an appropriate isolated fixture. Oversized content cases still fit beneath the separate 65,536-byte raw HTTP/MCP request limit when serialized normally.

## Structural schema

[`../schemas/cayapa-0.2.schema.json`](../schemas/cayapa-0.2.schema.json) uses JSON Schema draft 2020-12. Its root validates a contribution. Named definitions cover operation inputs and values:

| Definition | Validates |
| --- | --- |
| `content` | Opaque envelope structure |
| `capabilities`, `whoamiValue` | Capability and identity responses |
| `whoamiInput`, `sendInput`, `readInput`, `inboxInput`, `acknowledgeInput`, `retractInput` | Messaging arguments |
| `listConversationsInput`, `listMembersInput` | Authorized discovery arguments |
| `sendValue`, `page`, `acknowledgeValue`, `retractValue` | Messaging operation values |
| `contribution`, `receipt`, `actor`, `owner` | Shared data structures |
| `listConversationsValue`, `listMembersValue`, `conversationSummary`, `member` | Discovery values |
| `httpResult`, `error` | HTTP wrapper and shared errors |

To select a definition, use the file with a fragment such as `cayapa-0.2.schema.json#/$defs/sendInput`, preserving the full document as the reference-resolution root. All schema references are internal to this one file. Response objects allow extension properties. Send and content objects reject them.

The schema is not a full validator of semantic conformance. It cannot independently establish current authority, history, retry identity, receipt state, normalized serialized byte limits, UTF-16 code-unit limits, canonical base64, blank Unicode text, or the absence of unpaired surrogates. Those are normative prose and live vector requirements. Some negative vectors intentionally pass the structural schema and must still fail semantic validation. No private Cayapa source code is needed to implement those checks.

## Stateful interoperability scenarios

The runner's report must separately exercise stateful properties that literal bodies cannot prove: two distinct actor attributions, cross-binding exact content preservation, duplicate/conflicting intent, conversation versus inbox cursor continuation, reader/outsider/revoked authority, history-hidden links, connection-specific unread receipts, and retraction. Credentials, memberships, and history floors are explicit fixture prerequisites, provisioned outside the messaging profile.

Both currently documented collection gaps must remain visible in reports: the contribution page's first-item byte-budget exception and wrapper exclusion, and discovery collections that are unbounded or omit records without continuation. A passing body vector set alone cannot justify a hard response-byte bound, independent-server interoperability, federation, a background runtime, or production delivery.
