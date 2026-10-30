"""Explicit public source boundary; never infer publication from Git status."""
import hashlib
import ipaddress
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FIXED = (
    ".gitignore", ".github/workflows/ci.yaml", ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/ISSUE_TEMPLATE/compatibility.yml", ".github/ISSUE_TEMPLATE/config.yml",
    "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "repository.yaml",
    "requirements-dev.txt", "docs/TESTING.md", "docs/RELEASING.md",
    "beoremote_gateway/config.yaml", "beoremote_gateway/Dockerfile",
    "beoremote_gateway/.dockerignore", "beoremote_gateway/requirements.txt",
    "beoremote_gateway/README.md", "beoremote_gateway/DOCS.md", "beoremote_gateway/LICENSE",
    "beoremote_gateway/CHANGELOG.md",
    "blueprints/automation/beoremote_light_action.yaml",
    "tests/fixtures/verified_light_telegrams.json",
    "tools/check_release.py", "tools/package.py", "tools/discover.py",
    "tools/release_files.py", "tools/export_release.py", "tools/container_check.sh",
    "tests/test_gateway.py", "tests/test_discovery.py", "tests/test_reliability.py",
    "tests/test_public_release.py", "tests/test_setup.py",
    "beoremote_gateway/gateway/setup.html",
    "beoremote_gateway/translations/en.yaml", "beoremote_gateway/translations/nl.yaml",
)
MODULES = (
    "__init__.py", "__main__.py", "buttons.py", "config.py", "discovery.py",
    "events.py", "health.py", "protocol.py", "server.py", "xmlstream.py",
    "autodetect.py", "runtime.py", "setup.py", "web.py",
)


def public_files(root=ROOT):
    root = Path(root).resolve()
    names = sorted((*FIXED, *(f"beoremote_gateway/gateway/{name}" for name in MODULES)))
    for name in names:
        path = root / name
        if not path.is_file() or any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError(f"Missing or symlinked public file: {name}")
    return names


def privacy_issues(name, content):
    """Catch common accidental disclosures; does not replace a human review."""
    issues = []
    if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                 r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|"
                 r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", content):
        issues.append(f"{name}: possible credential")
    if re.search(r"/(?:Users|home)/[^/\s]+/", content):
        issues.append(f"{name}: personal absolute path")
    for value in set(re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", content)):
        try:
            address = ipaddress.IPv4Address(value)
        except ValueError:
            continue
        if str(address) != "172.30.32.2" and any(address in network for network in (
            ipaddress.IPv4Network((0x0A000000, 8)), ipaddress.IPv4Network((0xAC100000, 12)),
            ipaddress.IPv4Network((0xC0A80000, 16)))):
            issues.append(f"{name}: private LAN address")
    # The only product-style device ID allowed is the deliberately synthetic fixture ID.
    for value in re.findall(r"\b\d{4}\.\d+\.\d+@products\.bang-olufsen\.com", content):
        if value != "7980.1234567.12345678@products.bang-olufsen.com":
            issues.append(f"{name}: non-synthetic device identity")
    return issues


def manifest(root=ROOT):
    result, issues = {}, []
    for name in public_files(root):
        data = (root / name).read_bytes()
        issues.extend(privacy_issues(name, data.decode("utf-8")))
        result[name] = hashlib.sha256(data).hexdigest()
    if issues:
        raise ValueError("Public source review failed:\n" + "\n".join(issues))
    return result
