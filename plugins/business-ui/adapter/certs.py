"""Self-signed TLS material for the reference adapter (tests / local demo)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def write_self_signed(directory: Path, hostname: str = "127.0.0.1") -> tuple[Path, Path, str]:
    cert_path = directory / "server.pem"
    key_path = directory / "server.key"
    san = f"IP:{hostname}" if hostname.replace(".", "").isdigit() else f"DNS:{hostname}"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "7",
            "-nodes",
            "-subj",
            f"/CN={hostname}",
            "-addext",
            f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return cert_path, key_path, cert_path.read_text(encoding="utf-8")
