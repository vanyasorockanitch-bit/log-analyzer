from __future__ import annotations

from datetime import datetime
import re

from app.parsers.base import BaseLogParser, ParsedLine


APACHE_ERROR_PATTERN = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\] \[(?P<level>[^\]]+)\] (?P<message>.*)$"
)


def parse_apache_timestamp(timestamp_str: str) -> datetime | None:
    """Convert Apache error timestamps into datetime objects."""

    try:
        return datetime.strptime(timestamp_str, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        try:
            without_weekday = " ".join(timestamp_str.split()[1:])
            return datetime.strptime(without_weekday, "%b %d %H:%M:%S %Y")
        except ValueError:
            return None


class ApacheErrorParser(BaseLogParser):
    format_name = "apache_error"

    def detect(self, lines: list[str]) -> int:
        matches = sum(1 for line in lines if APACHE_ERROR_PATTERN.match(line.strip()))
        if not lines:
            return 0
        return int(matches / len(lines) * 100)

    def parse_line(self, line: str) -> ParsedLine | None:
        match = APACHE_ERROR_PATTERN.match(line.strip())
        if not match:
            return None

        raw = match.groupdict()
        return ParsedLine(
            timestamp=parse_apache_timestamp(raw["timestamp"]),
            level=raw["level"],
            source=self.format_name,
            message=raw["message"],
            parsed_data={
                "original": line.strip(),
                "timestamp_str": raw["timestamp"],
                "level": raw["level"],
                "message": raw["message"],
            },
        )
