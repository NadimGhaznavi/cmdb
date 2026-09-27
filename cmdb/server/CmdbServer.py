"""Run the CMDB HTTP server."""

import argparse
from http.server import ThreadingHTTPServer
import os
import signal

from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment
from cmdb.server.CmdbHandler import CmdbHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DCmdb.HOST)
    parser.add_argument("--port", type=int, default=DCmdb.PORT)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")
    DatabaseEnvironment.validate({key: os.environ.get(key, "") for key in
                                  ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")})

    def stop(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        with ThreadingHTTPServer((args.host, args.port), CmdbHandler) as server:
            print(f"CMDB: http://{args.host}:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        signal.signal(signal.SIGTERM, previous)
