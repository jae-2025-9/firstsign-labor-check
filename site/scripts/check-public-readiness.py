#!/usr/bin/env python3
"""Check reachable Git history and publishable files without printing matched values."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys


SECRET_NAMES = (
    "UPSTAGE_API_KEY", "CONTRACT_AGENT_ID", "CONTRACT_CONFIG_ID",
    "CRITERIA_AGENT_ID", "CRITERIA_CONFIG_ID", "REVIEW_AGENT_ID", "REVIEW_CONFIG_ID",
)
PATTERNS = {
    "api_token": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})"),
    "slack_token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}"),
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "jwt": re.compile(rb"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}"),
    "personal_absolute_path": re.compile(rb"/(?:Users|home)/[^/\s\"'`<>]+|[A-Za-z]:\\Users\\[^\\\s\"'`<>]+"),
}
ASSIGNMENT = re.compile(
    rb"(?im)^[ \t]*(?:export[ \t]+)?[\"']?([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)|"
    + b"|".join(name.encode() for name in SECRET_NAMES)
    + rb")[\"']?[ \t]*[:=][ \t]*[\"']?([^\s\"',;#}]+)"
)
EXAMPLE_SUFFIXES = (".example", ".sample", ".template")
LARGE_THRESHOLD = 2_000_000


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.DEVNULL)


def placeholder(value):
    lower = value.lower()
    return (
        len(value) < 8
        or lower.startswith((b"test", b"dummy", b"example", b"your", b"replace", b"placeholder", b"mock", b"fake"))
        or lower.startswith((b"$", b"<", b"process.", b"os.", b"env.", b"config.", b"re.compile("))
    )


def reference_values(path):
    if path is None:
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
        if not match or match[1] not in SECRET_NAMES:
            continue
        value = match[2]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        encoded = value.encode()
        if not placeholder(encoded):
            values[match[1]] = encoded
    return values


def content_types(data, references):
    found = {name for name, pattern in PATTERNS.items() if pattern.search(data)}
    for match in ASSIGNMENT.finditer(data):
        if not placeholder(match[2]):
            found.add("credential_assignment")
    for name, value in references.items():
        if value in data:
            found.add(f"known_secret:{name}")
    return sorted(found)


def path_types(path):
    name = Path(path).name
    found = []
    if not name.endswith(EXAMPLE_SUFFIXES) and (name == ".env" or name.startswith(".env.") or name == ".dev.vars" or name.startswith(".dev.vars.")):
        found.append("local_environment_file")
    if re.search(r"(^|/)(?:logs?|node_modules|dist|\.next|\.wrangler)(/|$)|\.log(?:\.|$)|(^|/)rollout[-_]", path, re.I):
        found.append("log_or_generated_artifact")
    return found


def necessity(path):
    if path.endswith((".ttf", ".otf")):
        return "Korean PDF font; retain unless an equivalent licensed font replaces it."
    if path.startswith(("fixtures/", "tests/fixtures/")):
        return "Recorded inputs or parity evidence; review test coverage before reducing it."
    if path.endswith(".pdf"):
        return "PDF input asset; confirm the sample or criteria consumer before removal."
    return "Manual review required."


def self_test():
    assert "github_token" in content_types(b"ghp_" + b"A" * 30, {})
    assert "personal_absolute_path" in content_types(b"/" + b"Users/example/work", {})
    assert "known_secret:UPSTAGE_API_KEY" in content_types(b"synthetic-reference", {"UPSTAGE_API_KEY": b"synthetic-reference"})
    assert not content_types(b"UPSTAGE_API_KEY=test-key", {})
    assert not content_types(b"UPSTAGE_API_KEY=\nCONTRACT_AGENT_ID=\n", {})
    assert "credential_assignment" in content_types(b"UPSTAGE_API_KEY=" + b"Z" * 32, {})
    message = b"Update configuration\n\n" + b"synthetic-reference"
    assert "known_secret:UPSTAGE_API_KEY" in content_types(message, {"UPSTAGE_API_KEY": b"synthetic-reference"})
    assert "personal_absolute_path" in content_types(b"Update files under /" + b"Users/example/work", {})
    assert not content_types(b"Update configuration and tests", {})
    assert path_types(".dev.vars") == ["local_environment_file"]
    assert not path_types(".env.example")
    assert path_types("outputs/run.log") == ["log_or_generated_artifact"]


def scan(root, references):
    commits = git("rev-list", "--all", cwd=root).decode().splitlines()
    blobs = {}
    findings = []
    sizes = {}

    def inspect(data, path, commit, object_id=None):
        if object_id is not None and object_id in blobs:
            kinds = blobs[object_id]
        else:
            kinds = content_types(data, references)
            if object_id is not None:
                blobs[object_id] = kinds
        for kind in sorted(set(kinds + path_types(path))):
            findings.append({"path": path, "commit": commit, "type": kind})
        if len(data) >= LARGE_THRESHOLD:
            key = (path, object_id or "working_tree")
            item = sizes.setdefault(key, {"path": path, "object": object_id, "bytes": len(data), "commits": [], "necessity": necessity(path)})
            item["commits"].append(commit)

    for commit in commits:
        message = git("show", "-s", "--format=%B", commit, cwd=root)
        for kind in content_types(message, references):
            findings.append({"path": "<commit-message>", "commit": commit, "type": kind})
        entries = git("ls-tree", "-rz", commit, cwd=root).split(b"\0")
        for entry in entries:
            if not entry:
                continue
            metadata, path_bytes = entry.split(b"\t", 1)
            _, kind, object_bytes = metadata.split()
            if kind != b"blob":
                continue
            object_id = object_bytes.decode()
            data = git("cat-file", "blob", object_id, cwd=root)
            inspect(data, path_bytes.decode("utf-8", "replace"), commit, object_id)

    paths = sorted(set(git("ls-files", "-z", "--cached", "--others", "--exclude-standard", cwd=root).split(b"\0")) - {b""})
    current_count = 0
    for path_bytes in paths:
        path = path_bytes.decode("utf-8", "replace")
        target = root / path
        if target.is_symlink():
            data = str(target.readlink()).encode()
        elif target.is_file():
            data = target.read_bytes()
        else:
            continue
        current_count += 1
        inspect(data, path, "working_tree")

    secret_types = set(PATTERNS) - {"personal_absolute_path"}
    blockers = [item for item in findings if item["type"] in secret_types or item["type"].startswith("known_secret:") or item["type"] in {"credential_assignment", "local_environment_file"}]
    ignored = {path: subprocess.run(["git", "check-ignore", "-q", path], cwd=root, capture_output=True).returncode == 0 for path in [".env", ".env.local", ".dev.vars", ".dev.vars.local", "node_modules/example", "dist/example", "outputs/qa/example.json", "HANDOFF.md"]}
    local_environment_files = []
    for target in sorted(set(root.glob(".env*")) | set(root.glob(".dev.vars*"))):
        if target.is_file() and not target.name.endswith(EXAMPLE_SUFFIXES):
            local_environment_files.append({
                "path": target.name,
                "ignored": subprocess.run(["git", "check-ignore", "-q", target.name], cwd=root, capture_output=True).returncode == 0,
                "tracked": subprocess.run(["git", "ls-files", "--error-unmatch", target.name], cwd=root, capture_output=True).returncode == 0,
                "contents_read": False,
            })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": git("rev-parse", "HEAD", cwd=root).decode().strip(),
        "scope": "Messages and file blobs from all reachable commits across all local refs, plus tracked and non-ignored untracked working files.",
        "commit_count": len(commits),
        "commit_message_count": len(commits),
        "history_blob_count": len(blobs),
        "working_file_count": current_count,
        "known_reference_comparison": bool(references),
        "known_reference_count": len(references),
        "secret_values_recorded": False,
        "blocking_finding_count": len(blockers),
        "review_finding_count": len(findings) - len(blockers),
        "findings": findings,
        "large_file_threshold_bytes": LARGE_THRESHOLD,
        "large_files": sorted(sizes.values(), key=lambda item: (item["path"], item["object"] or "")),
        "ignore_checks": ignored,
        "local_environment_files": local_environment_files,
        "ready_without_further_review": not findings and all(ignored.values()),
        "limits": ["Pattern matching cannot prove that every secret is absent.", "Unreachable objects and ignored local files are excluded.", "Large files require a separate necessity review."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/qa/github-readiness.json"))
    parser.add_argument("--reference-env", type=Path, help="Optional environment file. Values remain in process memory.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test()
    if args.self_test:
        print("Scanner self-test passed.")
        return 0
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    references = reference_values(args.reference_env)
    report = scan(root, references)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["commit_count", "history_blob_count", "working_file_count", "blocking_finding_count", "review_finding_count"]}))
    return 1 if report["blocking_finding_count"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.CalledProcessError, ValueError):
        print("The readiness scan failed. Check file access and Git state.", file=sys.stderr)
        sys.exit(2)
