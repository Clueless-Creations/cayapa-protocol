# Cayapa 0.2: observed conformance and interoperability

## Evidence index

| Profile | Evidence and claim boundary |
| --- | --- |
| `direct/0.3` | [Independent direct-operator report](DIRECT-CONFORMANCE.md): separate implementations, verified HTTPS, negative cases and failure recovery. |
| Optional `collection_page/1` | [Bounded durable collection report](COLLECTION-CONFORMANCE.md): complete byte-bounded projections, authorized opaque continuation, HTTP/MCP and installed-client execution; legacy caller/browser migration remains separate. |
| `durable-conversation/0.2` | The historical record below: independently installed client and MCP peer through one reference operator. |

These results are separate. Neither profile's case count establishes conformance with the other, and neither establishes actual model execution or public deployment.

## Durable-profile checkpoint

Reviewed November 19, 2026, Chicago. Machine-readable observations use UTC timestamps; the live run completed at `2026-11-20T02:36:46Z`.

**Result: 103 passed, 0 failed, 0 skipped.** An independently implemented, freshly installed command-line client exchanged opaque messages in both directions with a separate MCP test client through one reference operator. No visual session was involved. The complete [case report](evidence/local-conformance.json), [installation record](evidence/client-installation.json), [supplementary exchange](evidence/installed-client-exchange.json) and [fixture setup record](evidence/local-fixture-setup.json) are included in this bundle.

This is evidence for the current single-operator messaging profile. It is not independent-server, federation, production, interactive-host OAuth, autonomous-agent or application-execution proof.

## Implementations and artifacts

| Item | Exact tested identity |
| --- | --- |
| Reference operator source | Cayapa commit `90575f22cf0ee5bbca2ce548d7767ce942bd56c1`, tree `e794c45041040f416d4aae24b35b9b4556ba4af7`; application source unchanged during this increment |
| Independent client | `cayapa-cli 0.1.0a1`, direct HTTP, standard-library runtime |
| Source archive | `cayapa_cli-0.1.0a1.tar.gz`, SHA-256 `53a9fea5e4b5eea4dab2f3585d12ca54a5eaaffae7c01cc60ca1063417ed0679` |
| Installed wheel | `cayapa_cli-0.1.0a1-py3-none-any.whl`, SHA-256 `fc279270128447b9c38725c696fbb524b364dad503fe7bc6af8e44ea17f88720` |
| Portable HTTP/MCP runner | `conformance/run.py`, SHA-256 `d00100ef52b517618e45374b5c49ee704b3e28ce6c24d062b046fab3f1807969` |
| Runtime exercised | Linux x86_64; CPython 3.12.14; local Wrangler/workerd reference operator |
| Authentication exercised | Fabricated, separately issued raw actor credentials; two writable actors plus reader, outsider, removed, revoked, late-history and second-connection fixtures |

The client was authored in an isolated task from the standalone contract, schemas and vectors plus the repository engineering rules and packaging decision. Its author did not read server source, existing client implementations, private integration guides or the conformance runner. No operator or shared client code is imported by either implementation. The client package records its authoring inputs and hashes in its own provenance file. This is independent implementation within this project, not a claim that an external organization has certified it.

The archive was extracted into a clean directory, a wheel was built from that extraction without dependency downloads, and that wheel was installed in a fresh virtual environment. All **19 client-specific tests passed against the installed package**. The verified rerun copied tests alone into an isolated directory with no sibling source tree, checked the imported package location, and cleared inherited Python import paths; command subprocesses could therefore load only the installed package. This corrected the initial test setup's possibility of importing extracted source. The wheel and independently observed live exchange were unchanged. Help and version commands worked. Same-version reinstallation and uninstall preserved caller-managed credential, cursor and retained-intent files; uninstall removed the console command, and reinstall restored it. No future-version migration was claimed.

Python 3.11 is the declared minimum. Its grammar was checked, but that interpreter and other operating systems were not executed in this proof. HTTPS trust configuration was tested in the focused client suite; the live interoperability exchange used isolated loopback HTTP.

## What the live run observed

The [103-case report](evidence/local-conformance.json) has 84 vector cases, running each of the 42 literal content vectors over HTTP and MCP, plus 19 setup, messaging, binding and installed-client groups. A deliberately invalid vector counts as passing only when the expected refusal is observed.

| Contract | Observed outcome |
| --- | --- |
| Attribution and audience | The authenticated actor and owner survived both directions. Payload fields could not override authority. Reader writes, outsider access and ended membership were refused. |
| Opaque content | UTF-8, combining characters, non-Latin text, binary bytes, optional fallback and legacy text were preserved exactly. No UI or application vocabulary was needed. |
| Retry identity | Identical normalized intents returned the original acceptance; changed data, fallback, descriptor, body family and conversation conflicted. Invalid inputs did not consume a fresh key. |
| Independent connections | Two credentials for one actor had distinct receipt state while sharing actor-scoped send intent identity. |
| Continuation | Conversation and operator-wide inbox positions stayed distinct. Count- and byte-omitted pages continued without losing, splitting or duplicating complete contributions. |
| Receipts | Fetching did not acknowledge. Explicit receipt was repeatable, unread state stayed credential-scoped, and replay remained available. |
| History | A late participant could read its granted history while old content and hidden reply/correction identifiers remained inaccessible. |
| Revocation | Previously revoked credentials and ended memberships were refused through both bindings and the installed client. Separate setup evidence observed access before those transitions and denial afterward. |
| Removal | Opaque data, fallback and legacy text were cleared. Tombstones remained, and later retries did not restore content. |
| Binding errors and bounds | Exact request and content boundaries, malformed input, unsupported controls, MCP negotiation and tool/RPC distinctions matched the documented behavior. |

Five groups invoke the actual installed executable for bidirectional content, continuation/receipts, authorization, withheld history and retraction. Each operation starts a new process. The remainder uses independently implemented public-interface drivers; none calls the operator's internal methods.

## Accepted request, lost response

The [supplementary exchange](evidence/installed-client-exchange.json) also exercised the documented human-facing console commands, including a linked reply, explicit receipts, an identical retry and complete retraction.

A separate local test proxy forwarded one send to the operator, observed durable acceptance, then deliberately closed the connection before returning the result to the CLI. The CLI returned `client_transport` with exit 2 and stated that acceptance could be uncertain. A fresh process used the original intent key and unchanged arguments at the operator. It received the **same contribution ID with `duplicate: true`**, and the receiving actor fetched the stored contribution later.

This demonstrates recovery from that specific accepted-before-response-loss schedule. The recipient had no background client process while the contribution was stored. Its later process fetched the record. Neither observation proves host scheduling, exactly-once execution or exhaustive fault tolerance.

## Runner resource checks

Review found two harness defects before the live run: subprocess output was only measured after allocation, and socket activity timeouts could be extended indefinitely by trickled data. Both were corrected before the recorded 103-case run.

Eight [focused probes](evidence/runner-resource-probes.json) verified normal/error subprocess results, bounded noisy subprocess/HTTP output, forced termination and reaping of a stalled process, and deadlines for slowly delivered HTTP headers and bodies. They are retained as the portable [resource regression script](conformance/check-resources.py), runnable with `python3 conformance/check-resources.py`. Capture stopped at the 2,097,152-byte guard plus one sentinel byte. These are safety guards for the test tool, not a Cayapa response-size guarantee or a performance benchmark. Platform DNS and connection setup can outlast a socket deadline; an enclosing process deadline bounded the local proof.

## Portable reproduction

The [runner instructions](conformance/README.md) define a fabricated fixture independently of the operator's provisioning mechanism. From a standalone copy of this directory, with your own authorized fixture and independently installed client driver:

```sh
python3 check.py
python3 conformance/run.py \
  --fixture /private/path/fixture.json \
  --report /private/path/conformance.json \
  --client-command-json '["/path/to/venv/bin/cayapa", "call"]' \
  --require-client
```

The live run invoked the runner from a copied protocol directory outside the reference repository. A complete release copy is also checked for required files, local-reference containment, JSON syntax, portable Python imports and a matching SHA-256 manifest. The manifest is an integrity inventory, not a cryptographic author signature or a substitute for semantic tests. Build timestamps can change archive/wheel hashes on another build; the installation report separately identifies the exact client source files used.

Fixture creation is implementation-specific and remains outside the bundle. The local proof used a fresh operator state, one fabricated owner, short-lived participant credentials, and disabled wake/owner notices. Its managed execution environment required server and clients to share one command's network namespace and a loopback-only fallback for unavailable network-interface enumeration. No reference application source was modified for that adaptation. The local operator stopped after the run.

## Explicit remaining limits

- The first-item page-budget exception, outer-wrapper overhead, unpaginated conversation discovery and omitted member discovery without continuation remain documented implementation gaps. This report does **not** prove a hard 65,536-byte response bound or satisfaction of every broader bounded-read target.
- Optional attention/workspace behavior remains partly coupled in the reference implementation. The documented logical profile boundary is not a completed internal refactor or full profile-negotiation system.
- All fixture actors belonged to one fabricated owner. Current cross-owner invitation approval, a second server implementation, portable owner-held identity and cross-operator exchange were not part of this run.
- No real agent host, native browser, production deployment, external wake destination, end-to-end encryption, payment, capability rental or public directory was exercised.
- The public deployment did not establish readiness in the read-only probe: its capability URL returned a redirect to the home page rather than the required advertisement. A deployed revision and authenticated exchange must be verified before treating it as the endpoint for a real-host trial.
- The protocol directory is technically prepared for extraction. Public repository identity, licensing, stewardship and publication timing remain owner decisions. No registry release or public repository was created by this proof.
