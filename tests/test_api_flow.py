import io
import unittest

from tests.test_support import cleanup_isolated_app, load_isolated_app


class ApiFlowTests(unittest.TestCase):
    def setUp(self):
        (
            self.temp_dir,
            self.main_module,
            self.database_module,
            self.models_module,
            self.client,
        ) = load_isolated_app()

        self.nginx_log = b"\n".join(
            [
                b'127.0.0.1 - - [01/May/2026:12:00:00 +0300] "GET /index.html HTTP/1.1" 200 1024 "-" "Mozilla/5.0"',
                b'127.0.0.1 - - [01/May/2026:12:01:00 +0300] "GET /missing HTTP/1.1" 404 128 "-" "Mozilla/5.0"',
                b'127.0.0.2 - - [01/May/2026:12:02:00 +0300] "GET /api HTTP/1.1" 500 64 "-" "curl/8.0"',
            ]
        )

    def tearDown(self):
        self.database_module.engine.dispose()
        cleanup_isolated_app(self.temp_dir)

    def test_end_to_end_flow_persists_all_major_results(self):
        upload = self.client.post(
            "/upload/",
            files={"file": ("e2e_nginx.log", io.BytesIO(self.nginx_log), "text/plain")},
        )
        self.assertEqual(upload.status_code, 200)
        upload_payload = upload.json()
        self.assertEqual(upload_payload["detected_format"], "nginx_access")
        self.assertEqual(upload_payload["parse_status"], "parsed")
        log_file_id = upload_payload["log_file_id"]

        stats = self.client.get(
            f"/stats/file/{log_file_id}?group_by=hour&message_sort=first_seen_desc"
        )
        self.assertEqual(stats.status_code, 200)
        stats_payload = stats.json()
        self.assertEqual(stats_payload["total_events"], 3)
        self.assertEqual(stats_payload["top_messages_meta"]["sort"], "first_seen_desc")

        anomalies = self.client.get(f"/anomalies/file/{log_file_id}")
        self.assertEqual(anomalies.status_code, 200)
        self.assertIn("anomalies", anomalies.json())

        summarize = self.client.post(f"/nlp/summarize?filename={log_file_id}")
        self.assertEqual(summarize.status_code, 200)
        self.assertEqual(summarize.json()["status"], "processing")

        summaries = self.client.get(
            f"/nlp/summaries?file={log_file_id}&message_sort=count_desc"
        )
        self.assertEqual(summaries.status_code, 200)
        summary_items = summaries.json()
        self.assertTrue(summary_items)
        self.assertTrue(all(item["summary"] for item in summary_items))

        report = self.client.post(
            f"/reports/generate?filename={log_file_id}&message_sort=count_desc"
        )
        self.assertEqual(report.status_code, 200)
        report_payload = report.json()
        self.assertIn("report_id", report_payload)
        self.assertGreater(report_payload["saved_summaries_total"], 0)

        reports = self.client.get(f"/reports/?log_file_id={log_file_id}")
        self.assertEqual(reports.status_code, 200)
        report_items = reports.json()["items"]
        self.assertEqual(len(report_items), 1)
        report_id = report_items[0]["report_id"]

        report_detail = self.client.get(f"/reports/{report_id}")
        self.assertEqual(report_detail.status_code, 200)
        self.assertEqual(report_detail.json()["log_file_id"], log_file_id)

        report_pdf = self.client.get(f"/reports/{report_id}/pdf")
        self.assertEqual(report_pdf.status_code, 200)
        self.assertEqual(report_pdf.headers["content-type"], "application/pdf")
        self.assertGreater(len(report_pdf.content), 1000)

        session = self.database_module.SessionLocal()
        try:
            MessageSummary = self.models_module.MessageSummary
            Report = self.models_module.Report
            AnalysisResult = self.models_module.AnalysisResult

            message_count = (
                session.query(MessageSummary)
                .filter(MessageSummary.log_file_id == log_file_id)
                .count()
            )
            report_count = (
                session.query(Report)
                .filter(Report.log_file_id == log_file_id)
                .count()
            )
            analysis_count = (
                session.query(AnalysisResult)
                .filter(AnalysisResult.log_file_id == log_file_id)
                .count()
            )
        finally:
            session.close()

        self.assertGreater(message_count, 0)
        self.assertEqual(report_count, 1)
        self.assertGreaterEqual(analysis_count, 3)

    def test_blocks_analysis_for_failed_parse(self):
        upload = self.client.post(
            "/upload/",
            files={"file": ("broken.log", io.BytesIO(b"definitely not a supported log"), "text/plain")},
        )
        self.assertEqual(upload.status_code, 200)
        upload_payload = upload.json()
        self.assertEqual(upload_payload["parse_status"], "failed")
        self.assertIsNotNone(upload_payload["auto_parse_error"])
        log_file_id = upload_payload["log_file_id"]

        stats = self.client.get(f"/stats/file/{log_file_id}")
        self.assertEqual(stats.status_code, 409)

        summarize = self.client.post(f"/nlp/summarize?filename={log_file_id}")
        self.assertEqual(summarize.status_code, 409)

        report = self.client.post(f"/reports/generate?filename={log_file_id}")
        self.assertEqual(report.status_code, 409)

    def test_clear_reports_and_uploads(self):
        upload = self.client.post(
            "/upload/",
            files={"file": ("cleanup_nginx.log", io.BytesIO(self.nginx_log), "text/plain")},
        )
        self.assertEqual(upload.status_code, 200)
        log_file_id = upload.json()["log_file_id"]

        stats = self.client.get(f"/stats/file/{log_file_id}")
        self.assertEqual(stats.status_code, 200)

        report = self.client.post(f"/reports/generate?filename={log_file_id}")
        self.assertEqual(report.status_code, 200)

        unconfirmed_upload_clear = self.client.delete("/upload/clear")
        self.assertEqual(unconfirmed_upload_clear.status_code, 400)

        upload_clear = self.client.delete("/upload/clear?confirm=true")
        self.assertEqual(upload_clear.status_code, 200)
        self.assertEqual(upload_clear.json()["deleted_log_files"], 1)
        self.assertEqual(upload_clear.json()["preserved_reports"], 1)
        self.assertGreater(upload_clear.json()["deleted_raw_logs"], 0)
        self.assertGreater(upload_clear.json()["deleted_parsed_events"], 0)

        uploads = self.client.get("/upload/")
        self.assertEqual(uploads.status_code, 200)
        self.assertEqual(uploads.json()["items"], [])

        reports = self.client.get("/reports/")
        self.assertEqual(reports.status_code, 200)
        report_items = reports.json()["items"]
        self.assertEqual(len(report_items), 1)

        saved_report = self.client.get(f"/reports/{report_items[0]['report_id']}")
        self.assertEqual(saved_report.status_code, 200)
        self.assertIn("report", saved_report.json())

        unconfirmed_report_clear = self.client.delete("/reports/clear")
        self.assertEqual(unconfirmed_report_clear.status_code, 400)

        report_clear = self.client.delete("/reports/clear?confirm=true")
        self.assertEqual(report_clear.status_code, 200)
        self.assertEqual(report_clear.json()["deleted_reports"], 1)

        reports_after_clear = self.client.get("/reports/")
        self.assertEqual(reports_after_clear.status_code, 200)
        self.assertEqual(reports_after_clear.json()["items"], [])


if __name__ == "__main__":
    unittest.main()
