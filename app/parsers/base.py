from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ParsedLine:
    """Normalized representation of one parsed log event."""

    timestamp: datetime | None
    level: str | None
    source: str
    message: str
    ip_address: str | None = None
    status_code: int | None = None
    http_method: str | None = None
    request_path: str | None = None
    parsed_data: dict[str, Any] | None = None


class BaseLogParser:
    """Shared interface for every supported log format parser."""

    format_name = "unknown"

    def detect(self, lines: list[str]) -> int:
        """
        Return a confidence score between 0 and 100 for the provided sample.

        A higher score means the parser is more confident that the file belongs
        to its format. The registry picks the parser with the highest score.
        """

        raise NotImplementedError

    def parse_line(self, line: str) -> ParsedLine | None:
        """Parse one line into the normalized event shape."""

        raise NotImplementedError
