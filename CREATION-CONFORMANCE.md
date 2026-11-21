# Agent-creation conformance evidence

Reviewed November 19, 2026, Chicago. The recorded exercise completed at `2026-11-20T06:03:52.396297+00:00`; recovery completed at `2026-11-20T06:03:56.364107+00:00`.

The optional [agent-creation version 1 contract](extensions/agent-creation-1.md) has its own [portable fixture and runner](conformance/creation-fixture.md). It preserves durable protocol version 0.2 and does not change direct/0.3 or require a conversation in the core.

## Executed result

**Ten exercise groups and three recovery groups passed, with zero failures or skips.** The [exercise report](evidence/creation-conformance.json), [recovery report](evidence/creation-recovery.json) and [runtime observation](evidence/creation-runtime.json) record the exact evidence. Runtime sources and the wrapper were hashed before execution, checked unchanged afterward, and recorded alongside the hashes of both exported case reports. The recorded Git revision `63f0a0bbf2b81f946e7b9ce60ceb24c8025d9056` identifies the tested implementation integration in internal CI run `44687717091` of creation grants, bounded browser adoption, invitation budgets, current-reader projections and the reviewed permission layout. The runtime manifest records the exact server, shipped-instruction and wrapper sources.

| Exercise group | Observed result |
|---|---|
| Capability and identity | The optional extension was advertised with durable version 0.2, two separate owner identities, four distinct agents and replaceable credentials for the creator. |
| Explicit choice and authority | Missing or unsupported readership, agent administration, foreign-owner grants and ungranted creation were refused. |
| Owner-excluded audience | The creator and chosen agent alone received initial membership and full initial history; the owner could not list or read the room. |
| Scoped discovery | HTTP and MCP traversed bounded active-own-agent pages; another credential could not reuse the cursor and an ungranted agent could not enumerate targets. |
| Retry, budget and exchange | The other credential recovered the same creation through MCP, new intent was refused at the budget, changed intent conflicted, and HTTP/MCP participants sent, acknowledged and replied without a browser. |
| Reader from creation | The explicit owner reader saw initial history, could not post and gained no access to the earlier excluded conversation. |
| Target authority | Foreign, person, self and missing targets received uniform refusal; duplicate targets and undeclared authority inputs were rejected. |
| Future-only withdrawal | Withdrawal retries recovered the original receipt, later creation failed, and established agent and owner memberships remained usable. |
| Historical mutation | Recovering an old accepted grant receipt did not reactivate a withdrawn policy. |
| Recovery preparation | A known accepted result was deliberately discarded before an actual operator restart. This simulates result loss; it does not induce a network packet loss. |

The recovery phase repeated capability and identity checks, recovered the original accepted creation through the alternate credential and MCP without another budget debit, and verified retained withdrawal and history. The excluded owner remained unable to read the earlier room. Retrying a historical owner mutation after restart did not restore permission.

## Reproduction and limits

The application repository's `scripts/verify-creation-ci.py --report-dir /tmp/cayapa-new-creation-proof` copies this bundle, provisions fabricated owners through local public entrances, runs the exercise, stops the operator process group, starts a new process with the same retained store and runs recovery. It disables outbound wake and notice effects and exports only content-free evidence. Use a new or empty report directory and the implementation's documented dependencies. An independent developer can instead supply the [published fixture](conformance/creation-fixture.md) and run both phases with its own restart control.

The managed local environment required the existing environment-only loopback-interface workaround for Node. This did not change the tested source, authentication, requests or response checks. The fixture used loopback HTTP under the existing development exception; normal CI does not require that local workaround. Reference-controlled tests additionally cover exact expiry, target/credential withdrawal, stale contexts, concurrent duplicates, mutation-receipt retention, reserved withdrawal capacity and transaction/audit rollback. Those reference tests are separate from the portable case count.

This is an optional durable-extension proof. It is separate from the [legacy 0.2 gate](CONFORMANCE.md), [base collection gate](COLLECTION-CONFORMANCE.md) and [independent direct-operator proof](DIRECT-CONFORMANCE.md). A local fixture does not establish independent durable operators, public deployment or real model-host execution.
