"""python -m adapter — local HTTPS reference server (fixture, not production)."""

from __future__ import annotations

import argparse
from pathlib import Path

from .app import AdapterState, serve_tls
from .certs import write_self_signed


def main() -> None:
    parser = argparse.ArgumentParser(description="Reference Business UI Adapter")
    parser.add_argument("--token", default="dev-connection-token")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--cert-dir", default="")
    args = parser.parse_args()
    directory = Path(args.cert_dir or Path.cwd() / ".adapter-certs")
    directory.mkdir(parents=True, exist_ok=True)
    cert, key, _pem = write_self_signed(directory, args.host)
    state = AdapterState(args.token)
    httpd = serve_tls(state, certfile=str(cert), keyfile=str(key), host=args.host, port=args.port)
    bound = httpd.socket.getsockname()[1]
    print(f"reference adapter https://{args.host}:{bound} token={args.token}")
    print("NOT a customer business system. TLS cert is self-signed for local demo.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
