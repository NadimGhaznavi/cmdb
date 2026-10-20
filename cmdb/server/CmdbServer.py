"""Run the CMDB HTTP server."""

import argparse
from cmdb.server.CmdbHTTPServer import CmdbHTTPServer
import os
import signal

from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment
from cmdb.interface.Network import Network
from cmdb.server.CmdbHandler import CmdbHandler
from cmdb.activity.InventoryCoordinator import InventoryCoordinator
from cmdb.activity.BackupManager import BackupManager


def main() -> None:
    interface, port = Network.binding("http")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=interface)
    parser.add_argument("--port", type=int, default=port)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")
    DatabaseEnvironment.validate({key: os.environ.get(key, "") for key in
                                  ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")})

    def stop(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        with CmdbHTTPServer((args.host, args.port), CmdbHandler) as server:
            print(f"CMDB: http://{args.host}:{server.server_port}/", flush=True)
            coordinator = InventoryCoordinator(server.status_messages)
            server.backup_manager = BackupManager()
            server.inventory_coordinator = coordinator
            coordinator.start()
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                coordinator.stop()
                server.backup_manager.stop()
    finally:
        signal.signal(signal.SIGTERM, previous)
