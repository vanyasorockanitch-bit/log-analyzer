from __future__ import annotations

from datetime import datetime
import re

from app.parsers.base import BaseLogParser, ParsedLine


NGINX_ACCESS_PATTERN = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) (?P<protocol>[^"]+)" '
    r'(?P<status>\d{3}) (?P<body_bytes>\d+|-)'
    r'(?: "(?P<referrer>[^"]*)" "(?P<user_agent>[^"]*)")?$'
)


def parse_nginx_timestamp(timestamp_str: str) -> datetime | None:
    """Convert Nginx access timestamps into datetime objects."""

    try:
        return datetime.strptime(timestamp_str, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def status_to_level(status_code: int) -> str:
    """Map HTTP statuses to a simple severity useful for shared analytics."""

    if status_code >= 500:
        return "error"
    if status_code >= 400:
        return "warning"
    return "info"


class NginxAccessParser(BaseLogParser):
    format_name = "nginx_access"

    def detect(self, lines: list[str]) -> int:
        matches = sum(1 for line in lines if NGINX_ACCESS_PATTERN.match(line.strip()))
        if not lines:
            return 0
        return int(matches / len(lines) * 100)

    def parse_line(self, line: str) -> ParsedLine | None:
        match = NGINX_ACCESS_PATTERN.match(line.strip())
        if not match:
            return None

        raw = match.groupdict()
        status_code = int(raw["status"])
        method = raw["method"]
        path = raw["path"]

        return ParsedLine(
            timestamp=parse_nginx_timestamp(raw["timestamp"]),
            level=status_to_level(status_code),
            source=self.format_name,
            message=f"{method} {path} -> {status_code}",
            ip_address=raw["ip"],
            status_code=status_code,
            http_method=method,
            request_path=path,
            parsed_data={
                "original": line.strip(),
                "timestamp_str": raw["timestamp"],
                "protocol": raw["protocol"],
                "body_bytes": raw["body_bytes"],
                "referrer": raw.get("referrer"),
                "user_agent": raw.get("user_agent"),
            },
        )
