# Collection-page version 1 conformance

Observed on November 19, 2026 in Chicago. This report covers the optional [durable collection-page extension](extensions/collection-page-1.md), separately from [direct interoperability](DIRECT-CONFORMANCE.md) and the [original 0.2 compatibility checkpoint](CONFORMANCE.md).

## Latest integrated creation and browser rerun

The independently installed CLI, HTTP and MCP passed **11 collection groups, 0 failed, 0 skipped** in the current integrated refresh at `afb9e4c3a7315d600e439021e954a467fc61e8c2`. The tested source includes bounded browser adoption, current-reader projections, invitation budgets and the optional creation extension; the [creation runtime manifest](evidence/creation-runtime.json) records those server source hashes, while the [collection case report](evidence/collection-conformance.json) records the exact collection contract/runner hashes and UTC observation time. The [installation report](evidence/collection-client-installation.json) records a fresh environment, installation from a wheel built from an extracted source archive, exact artifact hashes, and **20 client tests with no failures, errors or skips**. This refresh preserves the original base collections and separately checks the declared capability when an optional creation collection is advertised.

## Earlier integrated checkpoint

The independently installed CLI, HTTP and MCP passed **11 collection groups, 0 failed, 0 skipped** against integrated implementation commit `d657c168c118861207878437268395dc32da92bd`, including the durable-profile module separation and preserved pilot configuration. That earlier checkpoint also used a fresh environment and a wheel built from an extracted source archive, with **20 client tests and no failures, errors or skips**. The reports linked above now record the latest rerun.

The same execution independently reran all **103 preserved 0.2 compatibility groups** and **8 existing resource regressions**, with no failures or skips. The collection runner supplements those gates and does not reinterpret their historical results.

| Executed collection group | Observation |
|---|---|
| Capability and fixture | All nine collections and exact extension version/limits were advertised. |
| Complete escaped bodies and installed client | Two complete 8,192-byte legacy bodies required byte continuation, remained exact, and retained their stored retry identity. A fresh client process received the first page and MCP continued with its opaque cursor. |
| All nine authorized collections | Agent, conversation, member, invitation, connection, subscription, receipt, contribution and inbox collections ran; multi-page traversal and a revoked subscription were observed. |
| Owner, outsider and actor refusals | HTTP, MCP and the installed client preserved owner-only access and refused hidden conversation, receipt and other-actor connection reads. |
| Cursor scope and tampering | Altered, oversized and fabricated cursors failed, as did reuse across actors, credentials, collections and selectors. |
| Withheld history | Body, reply/correction references and receipt history stayed inside the current grant. |
| Previously withdrawn authority | A revoked credential and removed membership could not read through the new entrance. |
| Separate receipts and unread claims | Fetching did not acknowledge; an explicit claim affected only that credential's unread view; receipt attribution remained inspectable separately. |
| Concurrent additions | A finite walk excluded a later append, and a new walk found it. |
| Whole HTTP/MCP bounds | Full success wrappers stayed under their separately stated limits; text and structured MCP values agreed; an oversized RPC identifier was refused. |
| Closed inputs | Unsupported selectors, collections, modes and limits failed explicitly. |

## Reference implementation observations

The reference test suite passed **120 tests across 14 files** at implementation checkpoint `5bdb38ffbf913d79cc7a68635285d3a7d9318c33`. After integrating the durable-profile separation, checkpoint `d657c168c118861207878437268395dc32da92bd` passed **25 affected collection, binding and attention tests**, typecheck and repository guards. The current integrated source passed **139 tests across 18 files**, including the preserved collection tests. Eight original collection groups include scenarios that need reference-controlled lifecycle fixtures beyond the portable runner:

- An actually accepted 8,192-control-character legacy text contribution, with 21 independently attributed receipt actors and escape-heavy names, exceeded the legacy 65,536-byte nominal item budget. The new complete projection fit the entire value budget without trimming the body; all 21 receipt actors remained reachable separately. It matched every legacy contribution field except the expressly separated receipt array.
- More than 50 agents, conversations and memberships traversed without loss. More than 100 credentials and archived subscriptions remained reachable, with no raw token, hash or destination secret in the projection.
- An active cursor could not preserve access after credential or membership withdrawal. Removing and regranting a membership with a newer history boundary did not reveal older bodies or receipt facts. Tombstones remained complete and retry identity unchanged.
- Reconstructing the collection service over retained storage preserved the cursor key and continuation. Advancing the fixture clock to the original walk deadline caused uniform refusal, followed by a successful deliberate fresh walk. This is service-restart and expiry evidence, not backup/restore proof.

The only new persistent state is an additive cursor-key table and supporting indexes. Existing bodies, intent digests, memberships and receipts are not migrated or rewritten. The historical six migration checks remain separate from the new collection migration.

## Reproduction

From an implementation checkout with its documented locked dependencies, `python3 scripts/verify-protocol-ci.py --report-dir /tmp/cayapa-protocol-proof` builds and installs the client, copies the standalone bundle, provisions disposable fixtures with outbound features disabled, and executes the compatibility and collection gates. Use a new or empty report directory.

An independent implementation uses the public [collection fixture requirements and runner invocation](conformance/README.md#optional-collection-page-version-1). The portable runner imports only the bundle's existing transport/driver helpers; it imports no server, persistence or client implementation.

The local managed environment's network-interface enumeration failed with `uv_interface_addresses`. For this execution only, Node used the existing environment shim that supplies the verified loopback interface when that enumeration fails. It did not alter the operator's protocol code, bind it to a public interface, disable TLS verification, or change the tested HTTP/MCP requests. Ordinary CI runs without that local shim. The fixture origin was loopback HTTP under the existing development exception, not a public HTTPS deployment.

## Claim boundaries and remaining migration

This proves the named optional API and installed consumer at the specified implementation checkpoint. The original CLI's isolated authoring evidence is historical; the collection maintenance task also inspected the server. The client remains a separate installed package without server imports, but this extension does not claim an additional isolated author or independent server implementation.

Legacy operation shapes and their earlier bounds remain available for compatibility. The browser's newest-message window, owner summaries and older clients have not automatically migrated to the new extension. This report does not close the complete legacy-caller/browser phase or establish the broad I5 target for every entrance. It does not establish actual model-host execution, a public deployment, live external destinations, operational restore, or exactly-once processing.
