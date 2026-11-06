"""Mac-only, sandboxed identity/policy checks for the dedicated Queen vault route.

No source secret is read by this launcher. Publication transport is separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "https://app.infisical.com"
PROJECT = "72a466bb-8c3f-482f-a214-cff243afb7e4"
BUNDLE = "local-scummhd-queen"
PLACEHOLDER = "hf_scummhd_queen_proxy_placeholder"
PIN = "37B2E08145ECC058462ED12FE12BE6AE2B78B1B3F021CD8FEC54CC302D369E37"


def run(action):
    expected = {"version": 1, "general": {"domain": INSTANCE},
                "secrets-management": {"project-id": PROJECT, "environment": "dev",
                                       "secret-path": "/agents/huggingface-queen"}}
    if json.loads((ROOT / ".infisical.yaml").read_text()) != expected:
        raise ValueError("Unreviewed Infisical source binding")
    home = Path.home().resolve()
    cli = home / ".config/infisical/cli/0.44.13/infisical"
    ca = home / ".config/infisical/agent-vault-ca.pem"
    certificate = ca.read_text()
    if hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate)).hexdigest().upper() != PIN:
        raise ValueError("Proxy CA pin mismatch")
    scratch = ROOT / ".internal/hf-vault"
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    ignored = subprocess.run(["git", "check-ignore", "-q", str(scratch)], cwd=ROOT,
                             capture_output=True)
    tracked = subprocess.run(["git", "ls-files", "--", ".internal"], cwd=ROOT,
                             capture_output=True, check=True)
    if ignored.returncode or tracked.stdout:
        raise ValueError("Private workspace must be ignored and untracked")
    with tempfile.TemporaryDirectory(prefix="check-", dir=scratch) as temporary:
        temp = Path(temporary).resolve()
        public_ca = temp / "proxy-ca.pem"
        public_ca.write_text(certificate)
        profile = temp / "client.sb"
        protected = [".config/infisical", ".infisical", ".ssh", ".config/gh",
                     ".git-credentials", ".netrc", ".cache/huggingface", ".huggingface",
                     "Library/Keychains", "Library/Application Support/BraveSoftware",
                     "Library/Application Support/Google/Chrome"]
        quote = json.dumps
        rules = ['(version 1)', '(allow default)', '(deny network*)',
                 '(allow network-outbound (remote ip "localhost:8283"))',
                 '(deny file-write*)',
                 f'(allow file-write* (subpath {quote(str(temp))}) (literal "/dev/null"))',
                 '(deny mach-lookup (global-name "com.apple.securityd") '
                 '(global-name "com.apple.security.agent"))']
        rules += [f'(deny file-read* (subpath {quote(str(home / path))}))' for path in protected]
        profile.write_text("\n".join(rules) + "\n")
        environment = {
            "HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HF_TOKEN": PLACEHOLDER, "HF_HOME": str(temp / "hf"),
            "NETRC": "/dev/null", "SSL_CERT_FILE": str(public_ca),
            "REQUESTS_CA_BUNDLE": str(public_ca), "CURL_CA_BUNDLE": str(public_ca),
            "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DISABLE_XET": "1", "DO_NOT_TRACK": "1",
        }
        command = [str(cli), "agent-vault", "run", "--domain=" + INSTANCE,
                   "--access-bundle=" + BUNDLE, "--proxy=127.0.0.1:8283", "--ttl=30m",
                   "--ca-fingerprint=SHA256:" + ":".join(PIN[i:i+2] for i in range(0, 64, 2)),
                   "--no-ca-trust", "--no-skills", "--silent", "--telemetry=false", "--",
                   "/usr/bin/sandbox-exec", "-f", str(profile), sys.executable,
                   "-I", str(ROOT / "scripts/hf_vault_probe.py"), action, str(temp), str(home)]
        result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                text=True, timeout=90)
        lines = [line.removeprefix("SCUMMHD_RESULT ") for line in result.stdout.splitlines()
                 if line.startswith("SCUMMHD_RESULT ")]
        if len(lines) != 1:
            diagnostic = (result.stdout + result.stderr).lower()
            print(json.dumps({"client_started": False, "exit_code": result.returncode,
                "diagnostic_flags": {word: word in diagnostic for word in
                    ["sandbox", "operation not permitted", "syntax", "keychain", "login", "proxy", "unauthorized", "no such file", "unknown flag", "not found", "certificate"]}}))
            raise ValueError("Vault check failed; provider output withheld. Check the Infisical login and local proxy.")
        report = json.loads(lines[0])
        print(json.dumps(report, indent=2))
        return result.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "test-policy"])
    args = parser.parse_args()
    try:
        sys.exit(run(args.action))
    except (OSError, ValueError, subprocess.SubprocessError):
        sys.exit("Vault check failed; credentials and provider output withheld. Verify configuration, login and proxy.")
