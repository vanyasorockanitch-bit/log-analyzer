from __future__ import annotations

from collections import OrderedDict

from sqlalchemy.orm import Session

from app.models import ParsedEvent, RawLog
from app.services.analytics import MESSAGE_SORT_LABELS, message_groups
from app.services.event_explanations import EventExplanation, explain_event
from app.services.local_model import generate_local_text


def explain_unique_messages(
    db: Session,
    log_file_id: int,
    language: str = "ru",
    message_sort: str = "count_desc",
) -> list[dict]:
    """
    Explain every unique message in the selected log.

    Messages are grouped only to avoid repeating identical explanations; no
    message is skipped just because it is rare.
    """

    base_query = (
        db.query(ParsedEvent)
        .join(RawLog, ParsedEvent.raw_log_id == RawLog.id)
        .filter(RawLog.log_file_id == log_file_id)
    )
    rows = message_groups(base_query, message_sort).all()

    explained = []
    for row in rows:
        sample_event = (
            base_query
            .filter(ParsedEvent.message == row.message)
            .order_by(ParsedEvent.id)
            .first()
        )
        explanation = explain_event(sample_event, language=language)
        explained.append(
            {
                "message": row.message,
                "count": row.count,
                "level": row.level or "unknown",
                "first_seen": _format_dt(row.first_seen),
                "last_seen": _format_dt(row.last_seen),
                "event_type": explanation.event_type,
                "severity": explanation.severity,
                "summary": explanation.summary,
                "recommendation": explanation.recommendation,
            }
        )

    return explained


def collect_recommendations(explanations: list[dict], anomalies: list[dict]) -> list[str]:
    """Build a compact recommendation list without duplicating the same advice."""

    ordered = OrderedDict()

    for anomaly in anomalies:
        if anomaly["severity"] == "high":
            ordered[anomaly["description"]] = None

    for item in explanations:
        if item["severity"] in {"high", "medium"}:
            ordered[item["recommendation"]] = None

    if not ordered:
        ordered["Критичных признаков не обнаружено; продолжить плановый мониторинг журнала."] = None

    return list(ordered.keys())[:8]


def build_human_report(
    *,
    log_file,
    stats: dict,
    anomalies: list[dict],
    explanations: list[dict],
    language: str = "ru",
    message_sort: str = "count_desc",
) -> dict:
    """
    Build a structured human-readable report from deterministic facts.

    The local model may add a short narrative summary, but the final report does
    not depend on it: rule-based text remains the source of truth.
    """

    recommendations = collect_recommendations(explanations, anomalies)
    narrative = _build_model_narrative(log_file, stats, anomalies, explanations, language)
    if narrative is None:
        narrative = _build_rule_based_narrative(log_file, stats, anomalies)

    top_messages = explanations[:10]
    top_message_lines = [
        (
            f"- {item['summary']} Повторений: {item['count']}. "
            f"Уровень: {item['level']}. "
            f"Первое появление: {item['first_seen'] or 'не определено'}. "
            f"Рекомендация: {item['recommendation']}"
        )
        for item in top_messages
    ]

    anomaly_lines = [
        f"- {item['title']}: {item['description']}" for item in anomalies
    ] or ["- Явных аномалий по текущим правилам не найдено."]

    recommendation_lines = [f"- {item}" for item in recommendations]

    report_text = "\n".join(
        [
            "Аналитический отчёт по журналу событий",
            "",
            "1. Навигация",
            f"Файл: {log_file.original_filename}",
            f"ID загрузки: {log_file.id}",
            f"Формат: {log_file.detected_format}",
            f"Период: {stats['time_range']['start'] or 'не определён'} - {stats['time_range']['end'] or 'не определён'}",
            "",
            "2. Краткое резюме",
            narrative,
            "",
            "3. Основная статистика",
            f"Всего событий: {stats['total_events']}",
            f"Уровни событий: {_format_dict(stats['by_level'])}",
            f"HTTP-статусы: {_format_dict(stats['by_status']) or 'не применимо'}",
            f"Доля error: {round(stats['error_ratio'] * 100, 1)}%",
            f"Доля HTTP 5xx: {round(stats['status_5xx_ratio'] * 100, 1)}%",
            "",
            "4. Аномалии",
            *anomaly_lines,
            "",
            "5. Объяснение уникальных сообщений",
            f"Порядок сортировки: {MESSAGE_SORT_LABELS.get(message_sort, MESSAGE_SORT_LABELS['count_desc'])}.",
            f"Всего объяснено уникальных сообщений: {len(explanations)}.",
            *top_message_lines,
            "",
            "6. Рекомендации",
            *recommendation_lines,
        ]
    )

    return {
        "summary_text": narrative,
        "report_text": report_text,
        "recommendations": recommendations,
    }


def _build_model_narrative(log_file, stats: dict, anomalies: list[dict], explanations: list[dict], language: str) -> str | None:
    if language != "ru":
        return None

    prompt = (
        "Составь 3 коротких предложения на русском языке для отчёта по журналу. "
        "Не придумывай факты, используй только данные ниже.\n"
        f"Файл: {log_file.original_filename}. "
        f"Формат: {log_file.detected_format}. "
        f"Всего событий: {stats['total_events']}. "
        f"Уровни: {_format_dict(stats['by_level'])}. "
        f"Аномалии: {', '.join(item['title'] for item in anomalies) or 'нет'}. "
        f"Частые типы событий: {', '.join(item['event_type'] for item in explanations[:5])}."
    )
    text = generate_local_text(prompt, max_length=160)
    if text is None or len(text) < 20:
        return None
    return text


def _build_rule_based_narrative(log_file, stats: dict, anomalies: list[dict]) -> str:
    parts = [
        f"Проанализирован файл {log_file.original_filename} в формате {log_file.detected_format}.",
        f"В журнале найдено {stats['total_events']} событий за выбранный период.",
    ]
    if anomalies:
        parts.append(
            f"Система обнаружила {len(anomalies)} важных сигналов, которые стоит проверить отдельно."
        )
    else:
        parts.append("По текущим правилам критичных аномалий не обнаружено.")
    return " ".join(parts)


def _format_dict(values: dict) -> str:
    return ", ".join(f"{key}: {value}" for key, value in values.items())


def _format_dt(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
