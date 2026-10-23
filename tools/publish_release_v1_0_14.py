"""Publish verified local artifacts using the existing Git credential helper.

Never print or persist credentials. Create a draft first, verify all uploaded
assets, and only then make the release public. Existing tags are never replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.14"
TAG = "v" + VERSION
REPOSITORY = "SYNTEC-20101749/-"
API = "https://api.github.com/repos/" + REPOSITORY
RELEASE_FILES = [
    "README.md", "build_release_v1_0_11.ps1", "build_release_v1_0_12.ps1",
    "build_release_v1_0_13.ps1", "build_release_v1_0_14.ps1", "desktop_app.py",
    "docs/release-v1.0.14.md", "invoice_desktop/__init__.py", "invoice_desktop/archive.py",
    "invoice_desktop/mail_fetcher.py", "invoice_desktop/main.py", "invoice_desktop/printing.py",
    "invoice_desktop/secrets_store.py", "python_recognizer/__init__.py", "python_recognizer/cli.py",
    "python_recognizer/extractors.py", "python_recognizer/heuristics.py", "python_recognizer/pairing.py",
    "python_recognizer/trip_summary.py", "python_recognizer/types.py", "python_recognizer/workflow.py",
    "requirements-python.txt", "start_desktop.bat", "tests/test_trip_summary.py",
    "tools/publish_release_v1_0_14.py", "ui_config.txt", "version_info.txt",
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=str(ROOT)).decode("utf-8").strip()


def credential() -> str:
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        ["git", "credential", "fill"], input=b"protocol=https\nhost=github.com\n\n",
        cwd=str(ROOT), env=environment, capture_output=True, check=True,
    )
    values = dict(line.split("=", 1) for line in result.stdout.decode("utf-8").splitlines() if "=" in line)
    token = values.get("password", "")
    if not token:
        raise RuntimeError("No GitHub credential available; sign in using Git Credential Manager.")
    return token


def request(token: str, path: str, payload=None, method="GET"):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(path, data=data, method=method, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "User-Agent": "SYNTEC-InvoiceManager-Release",
    })
    with urlopen(req, timeout=120) as response:
        return json.load(response)


def upload(token: str, url: str, path: Path):
    target = urlsplit(url.split("{", 1)[0] + "?name=" + quote(path.name))
    if target.scheme != "https" or target.hostname != "uploads.github.com":
        raise RuntimeError("Unexpected upload endpoint.")
    connection = http.client.HTTPSConnection(target.hostname, timeout=180)
    try:
        connection.putrequest("POST", target.path + "?" + target.query)
        for key, value in {
            "Authorization": "Bearer " + token, "User-Agent": "SYNTEC-InvoiceManager-Release",
            "Content-Type": "application/octet-stream", "Content-Length": str(path.stat().st_size),
        }.items():
            connection.putheader(key, value)
        connection.endheaders()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                connection.send(chunk)
        response = connection.getresponse()
        result = json.loads(response.read())
        if response.status != 201 or result.get("size") != path.stat().st_size:
            raise RuntimeError("Asset upload failed: " + str(response.status) + " " + str(result.get("message", "")))
        return result
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-auth", action="store_true")
    args = parser.parse_args()
    token = credential()
    identity = request(token, "https://api.github.com/user")
    repository = request(token, API)
    if not repository.get("permissions", {}).get("push"):
        raise RuntimeError("GitHub credential has no push permission for this repository.")
    print("GitHub authentication OK:", identity["login"], "|", repository["full_name"])
    if args.check_auth:
        return

    release_dir = ROOT / "release"
    binary = release_dir / ("SYNTEC-InvoiceManager-" + TAG + ".zip")
    source_zip = release_dir / ("SYNTEC-InvoiceManager-Source-" + TAG + ".zip")
    checksum_file = release_dir / ("SYNTEC-InvoiceManager-" + TAG + "-SHA256.txt")
    report_path = release_dir / ("SYNTEC-InvoiceManager-" + TAG) / "BUILD-VERIFICATION.json"
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if report["version"] != VERSION + ".0" or not report["gui_startup"].startswith("passed"):
        raise RuntimeError("Missing successful build/startup verification.")
    with zipfile.ZipFile(binary) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Binary ZIP integrity check failed.")
    original_checksum = checksum_file.read_text(encoding="ascii").split()[0]
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if original_checksum != digest:
        raise RuntimeError("Binary ZIP checksum does not match build output.")
    for filename in RELEASE_FILES:
        if not (ROOT / filename).is_file():
            raise RuntimeError("Missing release source: " + filename)
    for filename, expected_hash in report["source_sha256"].items():
        if filename not in RELEASE_FILES:
            raise RuntimeError("Build input missing from source release: " + filename)
        if hashlib.sha256((ROOT / filename).read_bytes().replace(b"\r\n", b"\n")).hexdigest() != expected_hash:
            raise RuntimeError("Source changed after build; rebuild before publishing: " + filename)
    staged = git("diff", "--cached", "--name-only", "-z").split("\0")
    if set(filter(None, staged)) - set(RELEASE_FILES):
        raise RuntimeError("Unrelated changes already staged; refusing to include them.")
    if git("branch", "--show-current") != "release":
        raise RuntimeError("Expected release branch.")
    git("add", "--", *RELEASE_FILES)
    if git("diff", "--cached", "--name-only"):
        git("commit", "-m", "Release v1.0.14: split ride-hailing trip summary by actual date")
    commit = git("rev-parse", "HEAD")
    source_contents = {
        filename: subprocess.check_output(["git", "show", commit + ":" + filename], cwd=str(ROOT))
        for filename in RELEASE_FILES
    }
    for filename, expected_hash in report["source_sha256"].items():
        if hashlib.sha256(source_contents[filename].replace(b"\r\n", b"\n")).hexdigest() != expected_hash:
            raise RuntimeError("Committed source differs from build input: " + filename)
    with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in RELEASE_FILES:
            info = zipfile.ZipInfo("SYNTEC-InvoiceManager-Source-" + TAG + "/" + filename, (2026, 10, 23, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source_contents[filename])
    checksums = []
    for path in (binary, source_zip):
        checksums.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name)
    checksum_file.write_text("\n".join(checksums) + "\n", encoding="ascii")

    remote_tag = git("ls-remote", "--tags", "origin", "refs/tags/" + TAG, "refs/tags/" + TAG + "^{}")
    if remote_tag:
        tag_refs = dict(line.split()[::-1] for line in remote_tag.splitlines())
        remote_commit = tag_refs.get("refs/tags/" + TAG + "^{}", tag_refs.get("refs/tags/" + TAG))
        if remote_commit != commit:
            raise RuntimeError("Remote tag points to another commit; refusing to replace it.")
    else:
        if TAG in git("tag", "--list", TAG).splitlines():
            if git("rev-list", "-n", "1", TAG) != commit:
                raise RuntimeError("Local tag points to another commit.")
        else:
            git("tag", "-a", TAG, "-m", "Release " + TAG)
    git("push", "origin", "HEAD")
    if not remote_tag:
        git("push", "origin", TAG)
    body = (ROOT / "docs" / ("release-" + TAG + ".md")).read_text(encoding="utf-8")
    releases = request(token, API + "/releases?per_page=100")
    release = next((item for item in releases if item["tag_name"] == TAG), None)
    if release is None:
        release = request(token, API + "/releases", {
            "tag_name": TAG, "target_commitish": commit, "name": "SYNTEC 发票管理系统 " + TAG,
            "body": body, "draft": True, "prerelease": False,
        }, method="POST")
    existing_assets = {item["name"]: item for item in release.get("assets", [])}
    for path in (binary, source_zip, checksum_file):
        if path.name in existing_assets:
            existing = existing_assets[path.name]
            expected_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            if existing["size"] != path.stat().st_size or existing.get("digest") != expected_digest:
                raise RuntimeError("Existing asset differs; refusing to overwrite: " + path.name)
            print("Verified existing asset:", path.name)
            continue
        asset = upload(token, release["upload_url"], path)
        print("Uploaded:", asset["name"], "|", asset["size"], "bytes")
    expected = {path.name for path in (binary, source_zip, checksum_file)}
    uploaded = request(token, API + "/releases/" + str(release["id"]))
    if {asset["name"] for asset in uploaded["assets"]} != expected:
        raise RuntimeError("Draft assets incomplete; refusing to publish.")
    release = request(token, API + "/releases/" + str(release["id"]), {"draft": False, "make_latest": "true"}, method="PATCH")
    verified = request(token, API + "/releases/tags/" + TAG)
    if verified["draft"] or {asset["name"] for asset in verified["assets"]} != expected:
        raise RuntimeError("Published release asset verification failed.")
    print("RELEASE_URL=" + verified["html_url"])
    print("RELEASE_COMMIT=" + commit)


if __name__ == "__main__":
    main()