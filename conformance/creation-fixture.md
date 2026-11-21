# Disposable fixture for agent-creation version 1

The [creation contract](../extensions/agent-creation-1.md) is optional. Its [runner](run_creation.py) uses Python's standard library, the shared public HTTP/MCP harness and no operator code. It mutates owner grants and creates conversations only for explicitly disposable fabricated identities. Do not point it at real owners or agents.

Provide a private JSON file outside the repository with `creationFixtureVersion:1`, `disposable:true`, `baseUrl`, `bindings:["http","mcp"]`, optional `operatorRevision`, and `credentials` containing exactly these raw credentials:

| Role | Starting condition |
|---|---|
| `owner` | A fabricated owner person who owns creator, peer and spare |
| `foreign_owner` | A distinct fabricated owner person |
| `creator` | A live agent of owner with no creation grant |
| `creator2` | A separate live credential for that same creator actor |
| `peer` | Another live agent of owner, without a creation grant |
| `spare` | A third live agent of owner, without a creation grant |
| `outsider` | A live agent of foreign_owner |

These are the only active agents owned by owner so the discovery assertion has an exact expected audience. Delegations and credentials must remain live for at least two hours. No pre-existing conversation is needed. Provisioning is implementation-specific and is outside the portable runner. The owner credentials explicitly authorize the fixture's grant mutations. MCP and HTTP must resolve each raw credential to the same actor and connection.

From a standalone protocol directory:

```bash
python3 conformance/run_creation.py --fixture /tmp/private-creation-fixture.json \
  --report /tmp/creation-exercise.json --checkpoint /tmp/private-creation-checkpoint.json
```

The exercise performs ten assertion groups. It leaves a private mode-0600 checkpoint of fabricated intent/receipt data, with no credentials. It sets and replaces both explicit readership choices, creates a headless handoff, verifies the receipt and linked reply, exercises cross-binding and cross-credential retries, bounded lookup, uniform target refusal, budgets and future-only withdrawal, and prepares a known accepted result for recovery. Treat discarding this result as simulated outcome loss, not an induced network failure.

Restart the operator through its own authorized fixture control plane, preserving its store, then run:

```bash
python3 conformance/run_creation.py --fixture /tmp/private-creation-fixture.json \
  --report /tmp/creation-recovery.json --checkpoint /tmp/private-creation-checkpoint.json \
  --phase recovery
```

The recovery phase performs three groups, including fresh capability/identity checks, original-intent recovery through the other credential and binding, retained creation usage, retained withdrawal, no owner-history backfill and no revival by retrying a historical owner mutation. The runner cannot itself attest that a restart occurred; the surrounding observation must identify that control. Both phases must pass with no failed or skipped case. Source hashes bind the published contract and runner to each report.

Reports contain no fixture credentials or message bodies. The shared HTTP harness refuses redirects, enforces response and wall-time limits, and accepts plain HTTP only for loopback. Exit 0 means all cases for that phase passed, 1 means a failed/skipped case, and 2 means fixture/report setup failed. A fresh fixture and new checkpoint are required for a new exercise.

The reference wrapper `scripts/verify-creation-ci.py` in the application repository creates two fabricated owners through local public entrances, copies this bundle, runs the exercise, actually stops/restarts its local operator with the same store, then runs recovery. That wrapper is an implementation-specific convenience and is not needed to implement the standard. Reference tests additionally cover transaction rollback, administrative receipt-capacity reservations, mutation retention, exact expiry, target withdrawal and stale authenticated contexts. Neither layer proves independent durable-operator interoperability, production deployment or actual model-host scheduling.
