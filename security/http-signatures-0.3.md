# HTTP signatures security profile 0.3

Identifier: `http-signatures/0.3`. Applied to the [HTTP message binding](../bindings/http-message-0.3.md). Use existing [HTTP Message Signatures, RFC 9421](https://www.rfc-editor.org/rfc/rfc9421.html), [Content-Digest, RFC 9530](https://www.rfc-editor.org/rfc/rfc9530.html), [JWS, RFC 7515](https://www.rfc-editor.org/rfc/rfc7515.html), [JWT, RFC 7519](https://www.rfc-editor.org/rfc/rfc7519.html), [proof-of-possession confirmation, RFC 7800](https://www.rfc-editor.org/rfc/rfc7800.html), [JWK, RFC 7517](https://www.rfc-editor.org/rfc/rfc7517.html), [OKP keys, RFC 8037](https://www.rfc-editor.org/rfc/rfc8037.html) and [fully specified JOSE algorithms, RFC 9864](https://www.rfc-editor.org/rfc/rfc9864.html). The restrictions below form a narrow interoperable application profile; implementations need not offer a generic signature service.

## 1. Trust and roles

A receiver has explicit local pins mapping each trusted owner URI and owner key identifier to its Ed25519 public key. Pinning is an authorized local introduction, not public name verification. Each recipient separately has standing admissions naming sender owner, sender actor, recipient actor, `cayapa:deliver`, validity interval and active state. Trust in an issuer alone is not admission.

Actor and owner keys are distinct. The receiving operator needs only issuer public keys, not remote owner/actor private keys. A sender owner signs a delegation; the actor signs each request using the key named by that delegation. The initial proof uses independent owner and actor key pairs on each side. TLS endpoint identity is separate from both.

A receiver MUST reject a delegation whose actor public key equals **any current owner public key pinned at that receiver**, including the issuer's or recipient owner's key. Compare the raw public-key bytes, not key identifiers. This prevents locally known control keys from also being accepted as delegated delivery keys. It does not claim detection of key reuse with an unknown remote owner.

No token-supplied `jku`, `x5u`, embedded owner `jwk`, arbitrary URL or `keyid` causes a key fetch. Unknown pins are refused. There is no mandatory global CA for actor/owner identity, Cayapa issuer, registry or DID method. TLS still requires normal endpoint verification against the configured trust store.

## 2. Owner delegation

`Cayapa-Delegation` carries one JWS Compact Serialization token, using canonical unpadded base64url segments. Header fields are exactly:

```json
{"typ":"cayapa-delegation+jwt","alg":"Ed25519","kid":"owner key URI"}
```

The signed payload fields are exactly:

```json
{
  "iss":"owner URI",
  "sub":"actor URI",
  "aud":"recipient actor URI",
  "iat":1795147200,
  "nbf":1795147200,
  "exp":1795147800,
  "jti":"delegation-1",
  "scope":"cayapa:deliver",
  "cnf":{"jwk":{"kty":"OKP","crv":"Ed25519","x":"base64url public key","kid":"actor key URI"}}
}
```

Header/payload/nested objects reject duplicate names, unknown fields and invalid Unicode. Decode as strict UTF-8 JSON. `iss`, `sub`, `aud` and key IDs follow the binding's absolute-URI rule; `jti` follows its message-id rule. The issuer pin is selected by both verified owner identifier and header `kid`. A key ID never establishes trust by itself.

`cnf` has exactly `jwk`; that JWK has exactly `kty`, `crv`, `x`, `kid`. `x` decodes to 32 bytes. Private `d`, another curve, `EdDSA`, `none`, symmetric algorithms, critical headers and alternative token types are refused. Verify the compact JWS signing input using the trusted owner key. The JOSE algorithm string is case-sensitive `Ed25519`; HTTP signatures separately use lowercase `ed25519`.

Time claims are nonnegative JSON integer number tokens at most `9007199254740991`, with decimal digits only and no leading zero except zero itself. Boolean, string, fractional or exponent notation is refused even when mathematically integral. Require `iat <= nbf < exp`, `exp - iat <= 900`, `iat <= now + 30`, `nbf <= now`, and `now < exp`. There is no expiry or not-before grace. The 30-second allowance applies only to issuer creation time. Short lifetime bounds unpropagated remote withdrawal to at most 900 seconds from issuance; an owner can explicitly withdraw sooner at the receiver.

The destination validates audience against its logical recipient, scope exactly, the body actor/owner/destination against these claims, and the signature key against `cnf.jwk.kid`. It checks the persistent `(iss,jti)` revocation set and recipient admission at acceptance. Replacement delegations do not change message identity or retry equivalence.

## 3. Digest and signature wire form

Compute SHA-256 over the exact HTTP content bytes and encode it with canonical padded base64:

```text
Content-Digest: sha-256=:BASE64_DIGEST:
```

Only that single digest member is supported. Message deliveries use exactly this ordered covered-component list and parameter order:

```text
Signature-Input: sig1=("@method" "@target-uri" "content-type" "content-digest" "cayapa-delegation");created=1795147200;expires=1795147260;nonce="32_lowercase_hex_characters";keyid="actor key URI";alg="ed25519";tag="cayapa-delivery-0.3"
Signature: sig1=:BASE64_ED25519_SIGNATURE:
```

Owner withdrawal requests omit `Cayapa-Delegation`, omit that component from the list, use an owner key ID, and set `tag="cayapa-control-0.3"`. Their content type is exactly `application/json`. No other signature labels, covered components, parameters, parameter reordering or extra whitespace in the value are permitted in this restricted profile. The placeholders above are illustrative, not valid signatures. Header field names remain HTTP case-insensitive.

The RFC 9421 signature base is UTF-8, LF-separated lines without a final LF. For delivery:

```text
"@method": POST
"@target-uri": https://receiver.example/cayapa/v0.3/messages
"content-type": application/cloudevents+json
"content-digest": sha-256=:BASE64_DIGEST:
"cayapa-delegation": COMPACT_JWS
"@signature-params": ("@method" "@target-uri" "content-type" "content-digest" "cayapa-delegation");created=1795147200;expires=1795147260;nonce="32_lowercase_hex_characters";keyid="actor key URI";alg="ed25519";tag="cayapa-delivery-0.3"
```

The control base analogously excludes the delegation line and component. Sign/verify using standard Ed25519 with a 64-byte signature, not a custom curve implementation. URI/key-id values cannot contain quotes or backslashes under the binding rule, so no string-escape ambiguity exists in this restricted form. The executable [signature vectors](../vectors/direct-signatures.json) include exact bytes, expected bases, public keys and deliberately nonsecret synthetic signing material.

## 4. Verification and replay

Require exactly one Host matching the configured HTTPS origin authority, the exact request path without a query, and POST. Derive `@target-uri` from that verified origin plus exact path. Do not trust forwarding headers by default. Verify content type, complete digest, signature coverage and signature parameters before acceptance.

`created` and `expires` are decimal integers without signs, leading zeros (except zero) or fractions. Require `created <= now + 30`, `created < expires`, `expires - created <= 60` and `now < expires`. A delivery signature also has `expires <= delegation.exp`. A nonce is 16 random bytes encoded as exactly 32 lowercase hexadecimal characters. Each authenticated attempt uses a fresh nonce, including exact message/control retries.

Replay identity is `(verified signing key's public bytes, nonce)` at this receiver, independent of route, token or HTTP connection. Persist consumed nonces through `expires + 30`. A repeated live nonce is `replay`; nonce checks and reservation are atomic with mutation. Rejected authenticated requests MAY consume their nonce. Invalid unauthenticated requests MUST NOT consume a trusted principal's nonce or message identity. Live replay records cannot be evicted for capacity; refuse `capacity` instead.

For message acceptance, recheck signature time, delegation time, revocation, admission and message expiry at the transaction's linearization point. For control, authenticate the owner pin and operation authority, then recheck the signature time window and still-current owner pin/control authority at the mutation's linearization point. A request that waited past validity cannot commit under stale checks. A fresh nonce does not repair an expired or revoked delegation. An old accepted receipt does not bypass current authority.

## 5. Withdrawal, rotation and limits

The [HTTP control operations](../bindings/http-message-0.3.md#4-owner-withdrawal-operations) bind issuer, recipient, target and stable request ID through the signature. Owner delegation withdrawal is effective at this receiver after its tombstone commit. Recipient admission withdrawal is effective after its local grant commit. Both serialize with delivery acceptance and survive process restart.

Remote withdrawal cannot be inferred before an authenticated update arrives. A network failure leaves propagation unknown; an unexpired delegation can still be used at a receiver that has not learned of withdrawal. A successful response names the receiver-local boundary. Actor-key rotation can use a new owner-signed delegation and withdrawal of the old jti; owner root-key rotation requires a separately authorized local re-trust procedure in this release. Automatic controller transfer and disaster recovery are not claimed.

Verified TLS authenticates response origin. Responses are not signed transferable receipts. A dishonest recipient can lie about its custody; this profile does not provide external auditing of that operator. Plaintext is visible at the recipient and any disclosed trusted terminator. Tokens, private keys, message bodies and full headers MUST NOT appear in logs or public evidence. Implementations must use the binding's bounds and bounded local state, and reject before promising responsibility they cannot retain.
