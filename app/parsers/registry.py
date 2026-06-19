from __future__ import annotations

from app.parsers.apache_error import ApacheErrorParser
from app.parsers.base import BaseLogParser
from app.parsers.nginx_access import NginxAccessParser


PARSERS: list[BaseLogParser] = [
    ApacheErrorParser(),
    NginxAccessParser(),
]


def detect_log_format(lines: list[str]) -> str:
    """
    Detect the most likely log format from a small sample of lines.

    Unknown is returned when no parser reaches a useful confidence score.
    """

    best_parser: BaseLogParser | None = None
    best_score = 0

    for parser in PARSERS:
        score = parser.detect(lines)
        if score > best_score:
            best_score = score
            best_parser = parser

    if best_parser is None or best_score < 30:
        return "unknown"
    return best_parser.format_name


def get_parser(format_name: str) -> BaseLogParser | None:
    for parser in PARSERS:
        if parser.format_name == format_name:
            return parser
    return None
