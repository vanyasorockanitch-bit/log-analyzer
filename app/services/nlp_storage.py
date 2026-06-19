import hashlib


def message_summary_hash(log_file_id: int, language: str, message: str) -> str:
    """
    Build a stable per-file hash for one summarized message.

    The same text can appear in different uploaded files, so the upload id and
    language are part of the hash. This keeps NLP results linked to the exact
    log used in a report.
    """

    source = f"{log_file_id}|{language}|{message}"
    return hashlib.md5(source.encode("utf-8")).hexdigest()
