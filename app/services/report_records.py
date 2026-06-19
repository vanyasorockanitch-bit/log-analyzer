import io
import os

import matplotlib
import matplotlib.pyplot as plt
from fastapi import HTTPException
from fpdf import FPDF

matplotlib.use("Agg")


class ReportPDF(FPDF):
    """Small PDF wrapper with a consistent footer for saved reports."""

    def footer(self):
        self.set_y(-12)
        self.set_font("ReportFont", "", 8)
        self.set_text_color(110, 118, 129)
        self.cell(0, 6, f"Страница {self.page_no()}", align="R")


def serialize_report(report, *, log_file=None) -> dict:
    """Return one saved report in a UI-friendly structure."""

    return {
        "report_id": report.id,
        "log_file_id": report.log_file_id,
        "filename": getattr(log_file, "original_filename", None),
        "detected_format": report.source_type,
        "language": report.language,
        "name": report.name,
        "description": report.description,
        "summary": report.summary_text,
        "report": report.report_text,
        "statistics": report.statistics or {},
        "anomalies": report.anomalies or [],
        "recommendations": report.recommendations or [],
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def serialize_report_list_item(report, *, log_file=None) -> dict:
    """Return compact metadata for the report history sidebar."""

    return {
        "report_id": report.id,
        "log_file_id": report.log_file_id,
        "filename": getattr(log_file, "original_filename", None),
        "detected_format": report.source_type,
        "language": report.language,
        "name": report.name,
        "summary": report.summary_text,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def build_saved_report_pdf(report_payload: dict) -> bytes:
    """
    Build a PDF from a previously saved report payload.

    The PDF is based only on persisted data, so opening an old report never
    recalculates statistics or depends on the current parser implementation.
    """

    font_regular, font_bold = _resolve_unicode_font_paths()

    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()
    pdf.add_font("ReportFont", "", font_regular)
    pdf.add_font("ReportFont", "B", font_bold)

    pdf.set_text_color(22, 27, 34)
    pdf.set_font("ReportFont", "B", 16)
    pdf.cell(
        0,
        10,
        report_payload.get("name") or "Сохранённый отчёт",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    pdf.set_text_color(90, 99, 110)
    pdf.set_font("ReportFont", "", 10)
    _write_pdf_line(
        pdf,
        f"Файл: {report_payload.get('filename') or 'не указан'} | "
        f"Загрузка: #{report_payload.get('log_file_id') or '-'} | "
        f"Отчёт: #{report_payload.get('report_id') or '-'}",
        line_height=5,
    )
    pdf.ln(2)

    summary = report_payload.get("summary") or "Краткое резюме отсутствует."
    _write_highlight_box(pdf, summary)

    _write_meta_block(pdf, report_payload)
    _write_statistics_block(pdf, report_payload.get("statistics") or {})
    _write_anomalies_block(pdf, report_payload.get("anomalies") or [])
    _write_recommendations_block(pdf, report_payload.get("recommendations") or [])
    _write_chart_block(pdf, report_payload.get("statistics") or {})
    _write_details_block(
        pdf,
        report_payload.get("report") or "",
        statistics=report_payload.get("statistics") or {},
    )
    _write_full_report_block(pdf, report_payload.get("report") or "")

    return bytes(pdf.output())


def ensure_saved_report_exists(report) -> None:
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")


def _resolve_unicode_font_paths() -> tuple[str, str]:
    regular_candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
    ]
    bold_candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf",
    ]

    regular_font = next((path for path in regular_candidates if os.path.exists(path)), None)
    if regular_font is None:
        raise HTTPException(
            status_code=500,
            detail="Unicode font was not found on this system, so PDF export is unavailable.",
        )

    bold_font = next((path for path in bold_candidates if os.path.exists(path)), regular_font)
    return regular_font, bold_font


def _write_section_title(pdf: FPDF, title: str) -> None:
    pdf.set_fill_color(237, 242, 247)
    pdf.set_text_color(22, 27, 34)
    pdf.set_font("ReportFont", "B", 12)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT", fill=True)


def _write_highlight_box(pdf: FPDF, text: str) -> None:
    pdf.set_fill_color(245, 248, 252)
    pdf.set_draw_color(210, 218, 230)
    pdf.set_text_color(33, 37, 41)
    pdf.set_font("ReportFont", "", 10)
    pdf.multi_cell(
        pdf.w - pdf.l_margin - pdf.r_margin,
        5,
        text,
        border=1,
        fill=True,
    )
    pdf.ln(2)


def _write_key_value(pdf: FPDF, label: str, value: str) -> None:
    label_width = 38
    value_width = pdf.w - pdf.l_margin - pdf.r_margin - label_width
    x = pdf.get_x()
    y = pdf.get_y()

    pdf.set_text_color(22, 27, 34)
    pdf.set_font("ReportFont", "B", 10)
    pdf.cell(label_width, 5, f"{label}:")

    pdf.set_xy(x + label_width, y)
    pdf.set_font("ReportFont", "", 10)
    pdf.multi_cell(value_width, 5, value, new_x="LMARGIN", new_y="NEXT")


def _write_bullet_list(pdf: FPDF, items: list[str], *, empty_text: str) -> None:
    pdf.set_font("ReportFont", "", 10)
    if not items:
        _write_pdf_line(pdf, empty_text)
        pdf.ln(1)
        return

    for item in items:
        _write_bullet_item(pdf, item)
    pdf.ln(1)


def _write_bullet_item(pdf: FPDF, text: str) -> None:
    bullet_width = 5
    text_width = pdf.w - pdf.l_margin - pdf.r_margin - bullet_width
    x = pdf.get_x()
    y = pdf.get_y()

    pdf.set_font("ReportFont", "", 10)
    pdf.cell(bullet_width, 5, "-")
    pdf.set_xy(x + bullet_width, y)
    pdf.multi_cell(text_width, 5, text, new_x="LMARGIN", new_y="NEXT")


def _format_mapping(values: dict) -> str:
    if not values:
        return "нет данных"
    return ", ".join(f"{key}: {value}" for key, value in values.items())


def _extract_detail_lines(report_text: str, *, max_items: int = 8) -> list[str]:
    """Take the most useful explanatory bullets from the saved text report."""

    lines = [line.strip() for line in report_text.splitlines() if line.strip()]
    collected = []
    in_details = False

    for line in lines:
        if line.startswith("5. "):
            in_details = True
            continue
        if line.startswith("6. "):
            break
        if in_details and line.startswith("- "):
            collected.append(line[2:])
        if len(collected) >= max_items:
            break

    return collected


def _detail_lines_from_statistics(statistics: dict, *, max_items: int = 8) -> list[str]:
    """Fallback source for explanations when the text report cannot be split reliably."""

    top_messages = statistics.get("top_messages") or []
    lines = []
    for item in top_messages[:max_items]:
        message = item.get("message") or "Сообщение не указано"
        count = item.get("count", 0)
        level = item.get("level") or "unknown"
        first_seen = item.get("first_seen") or "не определено"
        lines.append(
            f"{message}. Повторений: {count}. Уровень: {level}. Первое появление: {first_seen}."
        )
    return lines


def _write_meta_block(pdf: FPDF, report_payload: dict) -> None:
    _write_section_title(pdf, "Навигация")
    _write_key_value(pdf, "Отчёт", f"#{report_payload['report_id']}")
    _write_key_value(pdf, "Загрузка", f"#{report_payload['log_file_id']}")
    _write_key_value(pdf, "Файл", report_payload.get("filename") or "не указан")
    _write_key_value(pdf, "Формат", report_payload.get("detected_format") or "unknown")
    _write_key_value(pdf, "Дата создания", report_payload.get("created_at") or "не указана")
    pdf.ln(1)


def _write_statistics_block(pdf: FPDF, statistics: dict) -> None:
    _write_section_title(pdf, "Основная статистика")
    _write_key_value(pdf, "Всего событий", str(statistics.get("total_events", 0)))
    _write_key_value(pdf, "Период", _time_range_text(statistics.get("time_range") or {}))
    _write_key_value(pdf, "Уровни", _format_mapping(statistics.get("by_level") or {}))

    status_items = statistics.get("by_status") or {}
    if status_items:
        _write_key_value(pdf, "HTTP-статусы", _format_mapping(status_items))

    _write_key_value(pdf, "Доля error", f"{round(statistics.get('error_ratio', 0) * 100, 1)}%")
    _write_key_value(
        pdf,
        "Доля HTTP 5xx",
        f"{round(statistics.get('status_5xx_ratio', 0) * 100, 1)}%",
    )

    top_ips = statistics.get("top_ips") or []
    if top_ips:
        _write_bullet_list(
            pdf,
            [f"{item['ip_address']} — {item['count']}" for item in top_ips[:5]],
            empty_text="Активные IP-адреса не найдены.",
        )

    top_paths = statistics.get("top_paths") or []
    if top_paths:
        _write_bullet_list(
            pdf,
            [f"{item['request_path']} — {item['count']}" for item in top_paths[:5]],
            empty_text="Частые пути не найдены.",
        )

    pdf.ln(1)


def _write_anomalies_block(pdf: FPDF, anomalies: list[dict]) -> None:
    _write_section_title(pdf, "Аномалии")
    anomaly_lines = [
        f"{anomaly.get('title') or 'Аномалия'}: {anomaly.get('description') or ''}".strip()
        for anomaly in anomalies
    ]
    _write_bullet_list(pdf, anomaly_lines, empty_text="Явных аномалий не обнаружено.")


def _write_recommendations_block(pdf: FPDF, recommendations: list[str]) -> None:
    _write_section_title(pdf, "Рекомендации")
    _write_bullet_list(
        pdf,
        recommendations,
        empty_text="Отдельные рекомендации не сформированы.",
    )


def _write_chart_block(pdf: FPDF, statistics: dict) -> None:
    time_series = statistics.get("time_series") or []
    if not time_series:
        return

    chart_buffer = _build_time_series_chart(time_series)
    _write_section_title(pdf, "Временной ряд")
    available_width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.image(chart_buffer, w=available_width, x=pdf.l_margin)
    pdf.ln(2)


def _write_details_block(pdf: FPDF, report_text: str, *, statistics: dict) -> None:
    _write_section_title(pdf, "Ключевые объяснения")
    detail_lines = _extract_detail_lines(report_text)
    if not detail_lines:
        detail_lines = _detail_lines_from_statistics(statistics)
    _write_bullet_list(
        pdf,
        detail_lines,
        empty_text="Подробный текст отчёта отсутствует.",
    )


def _write_full_report_block(pdf: FPDF, report_text: str) -> None:
    _write_section_title(pdf, "Полный текст отчёта")
    pdf.set_font("ReportFont", "", 10)
    _write_pdf_line(pdf, report_text or "Текст отчёта отсутствует.")


def _build_time_series_chart(time_series: list[dict]) -> io.BytesIO:
    buckets = [item.get("bucket", "") for item in time_series]
    counts = [item.get("count", 0) for item in time_series]
    positions = list(range(len(buckets)))

    plt.figure(figsize=(7.8, 2.8))
    plt.plot(positions, counts, marker="o", linestyle="-", color="#1167D8", linewidth=2)
    plt.title("События по времени")
    plt.xlabel("Интервал")
    plt.ylabel("События")
    plt.grid(True, axis="y", linestyle="--", alpha=0.35)
    if buckets:
        step = max(len(buckets) // 8, 1)
        tick_positions = positions[::step]
        tick_labels = [buckets[index] for index in tick_positions]
        plt.xticks(tick_positions, tick_labels, rotation=30, ha="right")
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=120)
    plt.close()
    buffer.seek(0)
    return buffer


def _write_pdf_line(pdf: FPDF, text: str, *, line_height: int = 6) -> None:
    width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.multi_cell(width, line_height, text)


def _time_range_text(time_range: dict) -> str:
    start = time_range.get("start") or "не определён"
    end = time_range.get("end") or "не определён"
    return f"{start} - {end}"
