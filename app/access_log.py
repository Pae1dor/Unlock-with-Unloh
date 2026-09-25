"""Keep visitors' locations out of the server's access log.

The mosque finder's requests carry where the visitor is (map bbox, GPS lat/lng) or what
place they searched for in the query string. uvicorn logs every request line verbatim, so
for these paths the query string is replaced with "[redacted]".
"""
import logging

REDACTED_PATHS = frozenset({"/api/mosques/nearby", "/api/mosques/nearest", "/api/geocode"})


class RedactLocationQuery(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access records: args = (client_addr, method, full_path, http_version, status_code)
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path, sep, _query = args[2].partition("?")
            if sep and path in REDACTED_PATHS:
                record.args = args[:2] + (f"{path}?[redacted]",) + args[3:]
        return True


def install() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactLocationQuery) for f in logger.filters):
        logger.addFilter(RedactLocationQuery())
