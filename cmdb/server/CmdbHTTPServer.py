"""Own shared status history for one CMDB server lifetime."""

from http.server import ThreadingHTTPServer

from cmdb.entity.StatusMessages import StatusMessages


class CmdbHTTPServer(ThreadingHTTPServer):
    def __init__(self, address, handler):
        self.status_messages = StatusMessages()
        super().__init__(address, handler)
