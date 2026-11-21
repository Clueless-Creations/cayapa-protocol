import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
IGNORED_PARTS = {"__pycache__", ".git"}
REQUIRED = {
    "README.md", "architecture.md", "architecture.svg", "architecture-dark.svg",
    "specification.md", "bindings/http.md", "bindings/mcp.md",
    "schemas/cayapa-0.2.schema.json", "vectors/content.json", "vectors/README.md",
    "decisions.md", "CHANGELOG.md", "CONFORMANCE.md", "conformance/README.md",
    "conformance/run.py", "conformance/fixture.example.json",
    "conformance/check-resources.py",
    "core/0.3.md", "profiles/direct-0.3.md", "profiles/durable-conversation-0.2.md",
    "bindings/http-message-0.3.md", "security/http-signatures-0.3.md",
    "schemas/direct-0.3.schema.json", "vectors/direct-signatures.json",
    "conformance/run_direct.py", "conformance/direct-fixture.md", "conformance/requirements.txt",
    "conformance/check-direct-resources.py", "evidence/direct-resources.json",
    "IMPLEMENTING.md", "DIRECT-CONFORMANCE.md", "evidence/direct-conformance.json",
    "extensions/collection-page-1.md", "conformance/run_collections.py", "COLLECTION-CONFORMANCE.md",
    "evidence/collection-conformance.json", "evidence/collection-client-installation.json",
    "extensions/agent-creation-1.md", "conformance/creation-fixture.md", "conformance/run_creation.py",
    "CREATION-CONFORMANCE.md", "evidence/creation-conformance.json", "evidence/creation-recovery.json",
    "evidence/creation-runtime.json",
    "extensions/host-session-1.md", "conformance/session-fixture.md", "conformance/run_sessions.py",
    "SESSION-CONFORMANCE.md", "evidence/session-conformance.json", "evidence/session-isolated-summary.json",
    "check.py",
}


def files():
    return sorted(
        path for path in ROOT.rglob("*")
        if path.is_file() and not IGNORED_PARTS.intersection(path.relative_to(ROOT).parts)
        and path.suffix != ".pyc" and path.name != "manifest.json"
    )


def local_target(source, value, failures):
    reference = urlsplit(value)
    if reference.scheme or reference.netloc or not reference.path:
        return
    target = (source.parent / unquote(reference.path)).resolve()
    if not target.is_relative_to(ROOT):
        failures.append(f"{source.relative_to(ROOT)}: outside-bundle reference {value}")
    elif not target.exists() and target != ROOT / "manifest.json":
        failures.append(f"{source.relative_to(ROOT)}: missing local reference {value}")


def json_references(source, value, failures):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                local_target(source, child, failures)
            json_references(source, child, failures)
    elif isinstance(value, list):
        for child in value:
            json_references(source, child, failures)


def verify(failures):
    paths = files()
    present = {str(path.relative_to(ROOT)) for path in paths}
    failures.extend(f"Missing release file: {name}" for name in sorted(REQUIRED - present))
    modules = {path.stem for path in paths if path.suffix == ".py"}
    modules.update(path.parent.name for path in paths if path.name == "__init__.py")
    for path in paths:
        relative = str(path.relative_to(ROOT))
        if path.is_symlink():
            failures.append(f"{relative}: release files must not be symlinks")
        if path.suffix in {".md", ".svg"}:
            source = path.read_text(encoding="utf-8")
            for match in re.findall(r"\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)", source):
                local_target(path, match, failures)
            for match in re.findall(r'(?:src|srcset|href)="([^"\s]+)"', source):
                local_target(path, match, failures)
        elif path.suffix == ".json":
            try:
                json_references(path, json.loads(path.read_text(encoding="utf-8")), failures)
            except (ValueError, UnicodeError) as error:
                failures.append(f"{relative}: invalid JSON: {error}")
        elif path.suffix == ".py":
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names = [alias.name.split(".")[0] for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [(node.module or "").split(".")[0]]
                        if node.level:
                            base = path.parent
                            for unused in range(node.level - 1):
                                base = base.parent
                            if not base.is_relative_to(ROOT):
                                failures.append(f"{relative}: relative import escapes the bundle")
                            continue
                    else:
                        continue
                    for name in names:
                        declared = relative == "conformance/run_direct.py" and name == "cryptography"
                        if name not in sys.stdlib_module_names and name not in modules and not declared:
                            failures.append(f"{relative}: nonportable import {name}")
            except (SyntaxError, UnicodeError) as error:
                failures.append(f"{relative}: invalid Python: {error}")
    evidence = ROOT / "evidence/direct-conformance.json"
    resources = ROOT / "evidence/direct-resources.json"
    if evidence.exists() and resources.exists():
        try:
            report = json.loads(evidence.read_text(encoding="utf-8"))
            observed = report["summary"]
            if report["status"] != "passed" or observed["failed"] != 0 or observed["skipped"] != 0 or observed["passed"] != len(report["cases"]) or not all(case["status"] == "passed" for case in report["cases"]):
                failures.append("Direct release evidence requires a complete passing run")
            for entry in report["sourceHashes"]:
                source = (ROOT / entry["path"]).resolve()
                if not source.is_relative_to(ROOT) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
                    failures.append("Direct evidence source hashes do not match the published bundle")
                    break
            resource_report = json.loads(resources.read_text(encoding="utf-8"))
            if resource_report["runnerSha256"] != hashlib.sha256((ROOT / "conformance/run_direct.py").read_bytes()).hexdigest() or resource_report.get("passed") != 5 or resource_report.get("failed") != 0 or resource_report.get("skipped") != 0:
                failures.append("Direct resource evidence is incomplete or refers to another runner")
            if (ROOT / "conformance/requirements.txt").read_text(encoding="utf-8").strip() != "cryptography==50.0.0":
                failures.append("The declared direct conformance dependency does not match this bundle version")
        except (ValueError, KeyError, TypeError, OSError):
            failures.append("Direct evidence is invalid or incomplete")
    collection_evidence = ROOT / "evidence/collection-conformance.json"
    if collection_evidence.exists():
        try:
            report = json.loads(collection_evidence.read_text(encoding="utf-8"))
            if report.get("counts") != {"passed": 11, "failed": 0, "skipped": 0} or len(report.get("cases", [])) != 11 or not all(case["status"] == "passed" for case in report["cases"]):
                failures.append("Collection release evidence requires all eleven groups to pass")
            for relative, expected in report["sourceHashes"].items():
                source = (ROOT / relative).resolve()
                if not source.is_relative_to(ROOT) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                    failures.append("Collection evidence source hashes do not match the published bundle")
                    break
        except (ValueError, KeyError, TypeError, OSError):
            failures.append("Collection evidence is invalid or incomplete")
    creation_runtime = ROOT / "evidence/creation-runtime.json"
    if creation_runtime.exists():
        try:
            runtime = json.loads(creation_runtime.read_text(encoding="utf-8"))
            if runtime.get("status") != "passed" or runtime.get("creationGroups") != 10 or runtime.get("recoveryGroups") != 3 or not all(
                runtime.get(name) is True for name in ("actualOperatorRestart", "copiedStandaloneBundle", "separateOwnerIdentities", "outboundDisabled", "sourcesUnchangedDuringRun")
            ) or runtime.get("productionDeployed") is not False or runtime.get("actualModelHosts") is not False:
                failures.append("Creation runtime evidence requires an observed isolated restart with unchanged sources")
            for phase, filename, expected_count in (("exercise", "creation-conformance.json", 10), ("recovery", "creation-recovery.json", 3)):
                source_report = ROOT / "evidence" / filename
                report = json.loads(source_report.read_text(encoding="utf-8"))
                if report.get("reportFormat") != "cayapa-agent-creation-conformance-1" or report.get("extensionVersion") != "1" or report.get("protocolVersion") != "0.2" or report.get("phase") != phase:
                    failures.append("Creation release evidence has a different extension, profile or phase")
                if report.get("counts") != {"passed": expected_count, "failed": 0, "skipped": 0} or len(report.get("cases", [])) != expected_count or not all(case["status"] == "passed" for case in report["cases"]):
                    failures.append("Creation release evidence requires every exercise and recovery group to pass")
                if report.get("operatorRevision") != runtime.get("operatorRevision") or hashlib.sha256(source_report.read_bytes()).hexdigest() != runtime["reportSha256"][phase]:
                    failures.append("Creation runtime observation is not bound to these case reports")
                if set(report["sourceHashes"]) != {"extensions/agent-creation-1.md", "conformance/run_creation.py", "conformance/run.py"}:
                    failures.append("Creation evidence omits a required contract or runner source")
                for relative, expected in report["sourceHashes"].items():
                    source = (ROOT / relative).resolve()
                    if not source.is_relative_to(ROOT) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                        failures.append("Creation evidence source hashes do not match the published bundle")
                        break
        except (ValueError, KeyError, TypeError, OSError):
            failures.append("Creation evidence is invalid or incomplete")
    session_evidence = ROOT / "evidence/session-conformance.json"
    if session_evidence.exists():
        try:
            report = json.loads(session_evidence.read_text(encoding="utf-8"))
            observed = report["summary"]
            if report.get("format") != "cayapa-host-session-conformance-1" or report.get("contract") != "host-session/1" or report.get("status") != "passed":
                failures.append("Session release evidence requires the selected lifecycle contract and a passing run")
            isolated = json.loads((ROOT / "evidence/session-isolated-summary.json").read_text(encoding="utf-8"))
            if isolated.get("status") != "passed" or isolated.get("sourceReportSha256") != hashlib.sha256(session_evidence.read_bytes()).hexdigest() or isolated.get("copiedStandaloneSpecification") is not True or isolated.get("independentlyCopiedImplementations") is not True:
                failures.append("Session isolated-copy evidence is incomplete or refers to another run")
            if observed.get("passed") != 34 or observed.get("failed") != 0 or observed.get("skipped") != 0 or len(report.get("cases", [])) != 34 or not all(case.get("status") == "passed" for case in report["cases"]):
                failures.append("Session release evidence requires all 34 lifecycle and native exchange groups")
            if {case.get("lane") for case in report["cases"]} != {"left", "right", "left-to-right", "right-to-left"}:
                failures.append("Session evidence must include two lifecycle implementations and both native wire directions")
            required_sources = {"extensions/host-session-1.md", "proposals/session-identity.md", "conformance/session-fixture.md", "conformance/run_sessions.py", "conformance/run_direct.py", "conformance/run.py"}
            if not required_sources.issubset({entry["path"] for entry in report["sourceHashes"]}):
                failures.append("Session evidence omits a required contract or fixture source")
            for entry in report["sourceHashes"]:
                source = (ROOT / entry["path"]).resolve()
                if not source.is_relative_to(ROOT) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
                    failures.append("Session evidence source hashes do not match the published bundle")
                    break
            fixture = report["fixture"]
            if any(fixture.get(name) is not True for name in ("independentOwnerKeys", "independentActorKeys", "separateLifecycleStores", "manualIntroduction", "nativeSendersBothDirections", "deterministicLocalAndWireAfterCommitFaults")) or any(fixture.get(name) is not False for name in ("mcpRequired", "dnsDiscoveryRequired", "productionDeployed", "actualModelHosts")):
                failures.append("Session fixture evidence omits its authority, topology or claim limits")
        except (ValueError, KeyError, TypeError, OSError):
            failures.append("Session evidence is invalid or incomplete")
    return paths


def manifest(paths):
    return {
        "format": "cayapa-protocol-bundle-2",
        "coreVersion": "0.3",
        "profiles": {"direct/0.3": "profiles/direct-0.3.md", "durable-conversation/0.2": "profiles/durable-conversation-0.2.md"},
        "wireVersions": {"direct/0.3": "0.3", "durable-conversation/0.2": "0.2"},
        "bindings": ["http-message/0.3", "http/0.2", "mcp/0.2"],
        "security": ["http-signatures/0.3"],
        "hostLifecycleContracts": {"host-session/1": "extensions/host-session-1.md"},
        "conformanceDependencies": {"conformance/run_direct.py": ["cryptography==50.0.0"], "conformance/run_sessions.py": ["cryptography==50.0.0"]},
        "files": [
            {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in paths
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Check a standalone Cayapa protocol bundle.")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    failures = []
    paths = verify(failures)
    expected = manifest(paths)
    location = ROOT / "manifest.json"
    if not failures and args.write_manifest:
        location.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    elif location.exists():
        try:
            if json.loads(location.read_text(encoding="utf-8")) != expected:
                failures.append("Manifest mismatch: review changed files, then run python3 check.py --write-manifest.")
        except (ValueError, UnicodeError):
            failures.append("manifest.json is not valid JSON")
    else:
        failures.append("Missing manifest.json: finalize release files and run python3 check.py --write-manifest.")
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"Standalone bundle checked: {len(paths)} files; local links, JSON, Python imports and SHA-256 manifest match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
