from __future__ import annotations

from dataclasses import dataclass

from app.models import ParsedEvent


@dataclass
class EventExplanation:
    """Human-readable interpretation of one log event or repeated message."""

    event_type: str
    severity: str
    summary: str
    recommendation: str


def explain_event(event: ParsedEvent, language: str = "ru") -> EventExplanation:
    """
    Explain a parsed event in human language.

    The current diploma version is Russian-first. The language parameter is kept
    in the interface so an English branch can be added without changing callers.
    """

    if language != "ru":
        return _explain_event_ru(event)
    return _explain_event_ru(event)


def _explain_event_ru(event: ParsedEvent) -> EventExplanation:
    message = (event.message or "").lower()

    if event.source == "nginx_access" and event.status_code is not None:
        return _explain_http_event(event)

    if "workerenv.init() ok" in message:
        return EventExplanation(
            event_type="service_initialization",
            severity="info",
            summary="Компонент Apache/mod_jk успешно инициализировал рабочее окружение.",
            recommendation="Действия не требуются: это штатное служебное сообщение.",
        )

    if "workerenv in error state" in message:
        return EventExplanation(
            event_type="worker_error_state",
            severity="high",
            summary="Один из рабочих процессов mod_jk находился в ошибочном состоянии.",
            recommendation="Проверить состояние backend-сервиса, настройки worker и частоту повторения ошибки.",
        )

    if "found child" in message and "scoreboard" in message:
        return EventExplanation(
            event_type="apache_child_process",
            severity="info",
            summary="Apache обнаружил дочерний процесс в таблице состояния процессов.",
            recommendation="Действия обычно не требуются, если рядом нет повторяющихся ошибок worker.",
        )

    if "error" in message or event.level == "error":
        return EventExplanation(
            event_type="generic_error",
            severity="high",
            summary="В журнале зафиксирована ошибка, требующая внимания администратора.",
            recommendation="Сопоставить время события с нагрузкой сервера и соседними сообщениями журнала.",
        )

    if event.level in {"notice", "info"}:
        return EventExplanation(
            event_type="service_notice",
            severity="info",
            summary="Система записала информационное служебное событие.",
            recommendation="Использовать это сообщение как контекст; отдельного вмешательства оно обычно не требует.",
        )

    return EventExplanation(
        event_type="unclassified_event",
        severity="medium",
        summary="Событие не попало в известные правила классификации, но сохранено для анализа.",
        recommendation="При частом повторении добавить отдельное правило объяснения для этого типа сообщения.",
    )


def _explain_http_event(event: ParsedEvent) -> EventExplanation:
    method = event.http_method or "HTTP"
    path = event.request_path or "неизвестный путь"
    status_code = event.status_code or 0

    if status_code >= 500:
        return EventExplanation(
            event_type="http_server_error",
            severity="high",
            summary=f"Сервер не смог корректно обработать запрос {method} {path} и вернул HTTP {status_code}.",
            recommendation="Проверить приложение за этим маршрутом, серверные логи и состояние зависимых сервисов.",
        )

    if status_code == 404:
        return EventExplanation(
            event_type="http_not_found",
            severity="medium",
            summary=f"Клиент запросил отсутствующий ресурс {path}, сервер вернул HTTP 404.",
            recommendation="Проверить корректность ссылок, маршрутов приложения и возможные сканирующие запросы.",
        )

    if 400 <= status_code < 500:
        return EventExplanation(
            event_type="http_client_error",
            severity="medium",
            summary=f"Запрос {method} {path} завершился клиентской ошибкой HTTP {status_code}.",
            recommendation="Проверить параметры запроса, права доступа и ожидаемость такого поведения.",
        )

    if 300 <= status_code < 400:
        return EventExplanation(
            event_type="http_redirect",
            severity="info",
            summary=f"Запрос {method} {path} завершился перенаправлением HTTP {status_code}.",
            recommendation="Убедиться, что перенаправление соответствует логике сайта.",
        )

    return EventExplanation(
        event_type="http_success",
        severity="info",
        summary=f"Запрос {method} {path} успешно обработан, сервер вернул HTTP {status_code}.",
        recommendation="Действия не требуются, это нормальное событие доступа.",
    )
