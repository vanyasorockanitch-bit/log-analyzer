import unittest
from pathlib import Path

from app.parsers.apache_error import ApacheErrorParser
from app.parsers.nginx_access import NginxAccessParser
from app.parsers.registry import detect_log_format


SAMPLE_DIR = Path(__file__).resolve().parents[1] / "logs" / "samples"


def read_sample_lines(filename: str, limit: int = 200) -> list[str]:
    """Читает начало демонстрационного лога, чтобы тесты оставались быстрыми."""
    lines: list[str] = []
    with (SAMPLE_DIR / filename).open(encoding="utf-8", errors="replace") as file:
        for line in file:
            lines.append(line.rstrip("\n"))
            if len(lines) >= limit:
                break
    return lines


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.apache_line = (
            "[Sun Dec 04 04:47:44 2005] [notice] "
            "workerEnv.init() ok /etc/httpd/conf/workers2.properties"
        )
        self.nginx_line = (
            '127.0.0.1 - - [01/May/2026:12:00:00 +0300] '
            '"GET /index.html HTTP/1.1" 200 1024 "-" "Mozilla/5.0"'
        )

    def test_detects_apache_error_format(self):
        detected = detect_log_format([self.apache_line, self.apache_line])
        self.assertEqual(detected, "apache_error")

    def test_detects_nginx_access_format(self):
        detected = detect_log_format([self.nginx_line, self.nginx_line])
        self.assertEqual(detected, "nginx_access")

    def test_returns_unknown_for_unmatched_lines(self):
        detected = detect_log_format(["not a log line", "still not a log"])
        self.assertEqual(detected, "unknown")

    def test_detects_main_apache_sample_file(self):
        detected = detect_log_format(read_sample_lines("Apache_2k.log"))
        self.assertEqual(detected, "apache_error")

    def test_detects_main_nginx_sample_file(self):
        detected = detect_log_format(read_sample_lines("access.log"))
        self.assertEqual(detected, "nginx_access")

    def test_parses_apache_error_line(self):
        parser = ApacheErrorParser()
        parsed = parser.parse_line(self.apache_line)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.level, "notice")
        self.assertEqual(parsed.source, "apache_error")
        self.assertIn("workerEnv.init()", parsed.message)
        self.assertIsNotNone(parsed.timestamp)

    def test_parses_nginx_access_line(self):
        parser = NginxAccessParser()
        parsed = parser.parse_line(self.nginx_line)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.source, "nginx_access")
        self.assertEqual(parsed.level, "info")
        self.assertEqual(parsed.ip_address, "127.0.0.1")
        self.assertEqual(parsed.status_code, 200)
        self.assertEqual(parsed.http_method, "GET")
        self.assertEqual(parsed.request_path, "/index.html")
        self.assertEqual(parsed.message, "GET /index.html -> 200")


if __name__ == "__main__":
    unittest.main()
