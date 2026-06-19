const DEFAULT_FILE_NAME = "Apache_2k.log";
const MESSAGES_PER_PAGE = 10;
const NLP_POLL_INTERVAL_MS = 5000;

let currentChart = null;
let currentMessagePage = 1;
let totalMessagePages = 1;
let currentLogFileId = null;
let currentLogFile = null;
let currentReportId = null;
let uploadedFiles = [];
let savedReports = [];
let nlpPollTimer = null;

const uploadForm = document.getElementById("uploadForm");
const logFileInput = document.getElementById("logFileInput");
const refreshUploadsBtn = document.getElementById("refreshUploadsBtn");
const clearUploadsBtn = document.getElementById("clearUploadsBtn");
const parseBtn = document.getElementById("parseBtn");
const loadBtn = document.getElementById("loadBtn");
const summarizeBtn = document.getElementById("summarizeBtn");
const reportBtn = document.getElementById("reportBtn");
const exportPdfBtn = document.getElementById("exportPdfBtn");
const levelSelect = document.getElementById("level");
const groupBySelect = document.getElementById("group_by");
const messageSortSelect = document.getElementById("message_sort");
const currentFileName = document.getElementById("currentFileName");
const currentFileMeta = document.getElementById("currentFileMeta");
const uploadedFilesList = document.getElementById("uploadedFilesList");
const refreshReportsBtn = document.getElementById("refreshReportsBtn");
const clearReportsBtn = document.getElementById("clearReportsBtn");
const savedReportsList = document.getElementById("savedReportsList");
const statsContainer = document.getElementById("statsContainer");
const summaryDiv = document.getElementById("summary");
const anomaliesList = document.getElementById("anomaliesList");
const anomalyMeta = document.getElementById("anomalyMeta");
const tableBody = document.querySelector("#messagesTable tbody");
const prevPageBtn = document.getElementById("prevPageBtn");
const nextPageBtn = document.getElementById("nextPageBtn");
const pageInfoSpan = document.getElementById("pageInfo");
const reportContainer = document.getElementById("reportContainer");
const reportText = document.getElementById("reportText");
const reportMeta = document.getElementById("reportMeta");
const messageBox = document.getElementById("messageBox");
const chartHint = document.getElementById("chartHint");
const heroUploadCount = document.getElementById("heroUploadCount");
const heroCurrentFormat = document.getElementById("heroCurrentFormat");
const heroCurrentEvents = document.getElementById("heroCurrentEvents");
const heroParseStatus = document.getElementById("heroParseStatus");

window.addEventListener("DOMContentLoaded", async () => {
    bindEvents();
    await loadUploads({ preferDefault: true, loadStats: true });
    await loadReports();
});

function bindEvents() {
    uploadForm.addEventListener("submit", handleUploadSubmit);
    refreshUploadsBtn.addEventListener("click", () => loadUploads({ preserveSelection: true }));
    if (clearUploadsBtn) {
        clearUploadsBtn.addEventListener("click", clearUploadedLogs);
    }
    refreshReportsBtn.addEventListener("click", () => loadReports({ preserveSelection: true }));
    if (clearReportsBtn) {
        clearReportsBtn.addEventListener("click", clearSavedReports);
    }
    parseBtn.addEventListener("click", parseCurrentLog);
    loadBtn.addEventListener("click", () => loadStatistics(1));
    summarizeBtn.addEventListener("click", startSummarization);
    reportBtn.addEventListener("click", generateReport);
    exportPdfBtn.addEventListener("click", downloadPdf);
    messageSortSelect.addEventListener("change", () => loadStatistics(1));

    prevPageBtn.addEventListener("click", () => {
        if (currentMessagePage > 1) {
            loadMessagesPage(currentMessagePage - 1);
        }
    });

    nextPageBtn.addEventListener("click", () => {
        if (currentMessagePage < totalMessagePages) {
            loadMessagesPage(currentMessagePage + 1);
        }
    });
}

async function handleUploadSubmit(event) {
    event.preventDefault();

    if (!logFileInput.files.length) {
        showMessage("Выбери файл перед загрузкой.", "error");
        return;
    }

    const formData = new FormData();
    formData.append("file", logFileInput.files[0]);

    setActionButtonsDisabled(true);
    showMessage("Файл загружается, формат определяется автоматически...", "info");

    try {
        const response = await fetch("/upload/", {
            method: "POST",
            body: formData,
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const uploaded = await response.json();
        logFileInput.value = "";
        await loadUploads({ selectId: uploaded.log_file_id });
        const parseNote = uploaded.parse_status === "parsed"
            ? ` Парсинг выполнен автоматически: ${uploaded.auto_parse?.parsed ?? 0} строк.`
            : " Автопарсинг не выполнен, запусти ручной парсинг.";
        showMessage(
            `Файл ${uploaded.filename} загружен. Формат определён как ${uploaded.detected_format}.${parseNote}`,
            "info"
        );
    } catch (error) {
        showMessage(`Ошибка загрузки: ${error.message}`, "error");
    } finally {
        setActionButtonsDisabled(false);
    }
}

async function loadUploads(options = {}) {
    try {
        const response = await fetch("/upload/");
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const payload = await response.json();
        uploadedFiles = payload.items || [];
        renderUploadedFilesList();
        updateUploadCounters();

        const selectedId = chooseLogFileId(options);
        if (selectedId !== null) {
            const selected = uploadedFiles.find((item) => item.log_file_id === selectedId);
            const shouldLoadStats = Boolean(options.loadStats && selected?.parse_status === "parsed");
            selectLogFile(selectedId, { loadStats: shouldLoadStats });
        } else {
            clearCurrentLogFile({ keepReport: Boolean(options.keepReport) });
        }
    } catch (error) {
        showMessage(`Не удалось загрузить список файлов: ${error.message}`, "error");
    }
}

async function loadReports(options = {}) {
    try {
        const response = await fetch("/reports/");
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const payload = await response.json();
        savedReports = payload.items || [];
        renderSavedReportsList();

        if (options.selectId) {
            currentReportId = options.selectId;
        } else if (options.preserveSelection) {
            const exists = savedReports.some((item) => item.report_id === currentReportId);
            if (!exists) {
                currentReportId = null;
            }
        }

        renderSavedReportsList();
        updateActionButtonAvailability();
    } catch (error) {
        showMessage(`Не удалось загрузить историю отчётов: ${error.message}`, "error");
    }
}

async function clearUploadedLogs() {
    const confirmed = window.confirm(
        "Удалить все загруженные логи, распарсенные события, статистику и суммаризации из локальной БД? Сохранённые отчёты останутся."
    );
    if (!confirmed) {
        return;
    }

    setActionButtonsDisabled(true);
    try {
        const response = await fetch("/upload/clear?confirm=true", {
            method: "DELETE",
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const result = await response.json();
        uploadedFiles = [];
        clearCurrentLogFile({ keepReport: true });
        await loadUploads({ keepReport: true });
        await loadReports({ preserveSelection: true });
        showMessage(
            `Очищено загрузок: ${result.deleted_log_files}. Сохранённые отчёты оставлены: ${result.preserved_reports}.`,
            "info"
        );
    } catch (error) {
        showMessage(`Не удалось очистить загрузки: ${error.message}`, "error");
    } finally {
        setActionButtonsDisabled(false);
    }
}

async function clearSavedReports() {
    const confirmed = window.confirm(
        "Удалить все сохранённые отчёты из локальной БД? Загруженные логи и события останутся."
    );
    if (!confirmed) {
        return;
    }

    setActionButtonsDisabled(true);
    try {
        const response = await fetch("/reports/clear?confirm=true", {
            method: "DELETE",
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const result = await response.json();
        currentReportId = null;
        reportContainer.style.display = "none";
        await loadReports();
        showMessage(`Очищено отчётов: ${result.deleted_reports}.`, "info");
    } catch (error) {
        showMessage(`Не удалось очистить отчёты: ${error.message}`, "error");
    } finally {
        setActionButtonsDisabled(false);
    }
}

function chooseLogFileId(options) {
    if (options.selectId) {
        return options.selectId;
    }

    if (options.preserveSelection && currentLogFileId !== null) {
        const exists = uploadedFiles.some((item) => item.log_file_id === currentLogFileId);
        if (exists) {
            return currentLogFileId;
        }
    }

    if (options.preferDefault) {
        const defaultFile = uploadedFiles.find((item) => item.filename === DEFAULT_FILE_NAME);
        if (defaultFile) {
            return defaultFile.log_file_id;
        }
    }

    return uploadedFiles.length ? uploadedFiles[0].log_file_id : null;
}

function renderUploadedFilesList() {
    uploadedFilesList.innerHTML = "";

    if (!uploadedFiles.length) {
        uploadedFilesList.innerHTML = '<div class="empty-state">Пока нет загруженных логов. Начни с формы загрузки выше.</div>';
        return;
    }

    uploadedFiles.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "file-item";
        if (item.log_file_id === currentLogFileId) {
            button.classList.add("active");
        }

        button.innerHTML = `
            <div class="file-item-title">
                <span>${escapeHtml(item.filename)}</span>
                <span>#${item.log_file_id}</span>
            </div>
            <small>Загрузка: #${escapeHtml(item.log_file_id)}</small>
            <small>Формат: ${escapeHtml(item.detected_format || "unknown")}</small>
            <small>Статус: ${escapeHtml(translateParseStatus(item.parse_status))}</small>
            <small>Загружен: ${escapeHtml(formatDateTime(item.uploaded_at))}</small>
        `;

        button.addEventListener("click", () => selectLogFile(item.log_file_id, { loadStats: item.parse_status === "parsed" }));
        uploadedFilesList.appendChild(button);
    });
}

function renderSavedReportsList() {
    savedReportsList.innerHTML = "";

    if (!savedReports.length) {
        savedReportsList.innerHTML = '<div class="empty-state">Пока нет сохранённых отчётов. Сгенерируй первый отчёт для выбранного лога.</div>';
        return;
    }

    savedReports.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "file-item";
        if (item.report_id === currentReportId) {
            button.classList.add("active");
        }

        button.innerHTML = `
            <div class="file-item-title">
                <span>${escapeHtml(item.name || `Отчёт #${item.report_id}`)}</span>
                <span>#${item.report_id}</span>
            </div>
            <small>Загрузка: #${escapeHtml(item.log_file_id ?? "—")}</small>
            <small>Файл: ${escapeHtml(item.filename || "не указан")}</small>
            <small>Создан: ${escapeHtml(formatDateTime(item.created_at))}</small>
        `;

        button.addEventListener("click", () => openSavedReport(item.report_id));
        savedReportsList.appendChild(button);
    });
}

function selectLogFile(logFileId, options = {}) {
    const selected = uploadedFiles.find((item) => item.log_file_id === logFileId);
    if (!selected) {
        clearCurrentLogFile();
        return;
    }

    currentLogFileId = selected.log_file_id;
    currentLogFile = selected;
    if (!options.keepReport) {
        currentReportId = null;
        reportContainer.style.display = "none";
    }
    renderUploadedFilesList();
    renderSavedReportsList();
    renderCurrentLogFileCard();
    updateHeroMetrics();

    if (options.loadStats) {
        loadStatistics(1);
    }
}

function clearCurrentLogFile(options = {}) {
    currentLogFileId = null;
    currentLogFile = null;
    if (!options.keepReport) {
        currentReportId = null;
    }
    currentFileName.textContent = "Файл ещё не выбран";
    currentFileMeta.innerHTML = '<div class="empty-state">Выбери загрузку слева, чтобы перейти к разбору и статистике.</div>';
    statsContainer.style.display = "none";
    if (!options.keepReport) {
        reportContainer.style.display = "none";
    }
    renderUploadedFilesList();
    renderSavedReportsList();
    updateHeroMetrics();
    updateActionButtonAvailability();
}

function renderCurrentLogFileCard() {
    if (!currentLogFile) {
        clearCurrentLogFile();
        return;
    }

    currentFileName.textContent = currentLogFile.filename;
    currentFileMeta.innerHTML = [
        createMetaCard("ID загрузки", `#${currentLogFile.log_file_id}`),
        createMetaCard("Формат", currentLogFile.detected_format || "unknown"),
        createMetaCard("Статус", translateParseStatus(currentLogFile.parse_status)),
        createMetaCard("Строк", String(currentLogFile.line_count ?? 0)),
        createMetaCard("Загружен", formatDateTime(currentLogFile.uploaded_at)),
        createMetaCard("Последний парсинг", formatDateTime(currentLogFile.last_parsed_at)),
    ].join("");
    updateActionButtonAvailability();
}

function createMetaCard(label, value) {
    return `
        <div class="meta-card">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value || "—")}</strong>
        </div>
    `;
}

function updateUploadCounters() {
    heroUploadCount.textContent = String(uploadedFiles.length);
}

function updateHeroMetrics(totalEvents = null) {
    heroCurrentFormat.textContent = currentLogFile?.detected_format || "—";
    heroParseStatus.textContent = currentLogFile ? translateParseStatus(currentLogFile.parse_status) : "—";
    heroCurrentEvents.textContent = totalEvents === null ? "—" : String(totalEvents);
}

async function parseCurrentLog() {
    if (!currentLogFileId) {
        showMessage("Сначала выбери или загрузи лог.", "error");
        return;
    }

    setActionButtonsDisabled(true);
    showMessage("Лог разбирается. После завершения статистика откроется автоматически.", "info");

    try {
        const response = await fetch(`/parse/file/${currentLogFileId}`, { method: "POST" });
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const result = await response.json();
        await loadUploads({ selectId: currentLogFileId, loadStats: false });
        showMessage(
            `Парсинг завершён: распознано ${result.parsed} из ${result.total_lines} строк.`,
            "info"
        );
        await loadStatistics(1);
    } catch (error) {
        showMessage(`Ошибка парсинга: ${error.message}`, "error");
    } finally {
        setActionButtonsDisabled(false);
    }
}

async function loadStatistics(page = 1) {
    if (!currentLogFileId) {
        showMessage("Сначала выбери лог для анализа.", "error");
        return;
    }
    if (!isCurrentLogParsed()) {
        showMessage("Статистика доступна только после успешного парсинга файла.", "error");
        return;
    }

    const level = levelSelect.value;
    const groupBy = groupBySelect.value;
    const messageSort = messageSortSelect.value;
    const url = `/stats/file/${encodeURIComponent(String(currentLogFileId))}?group_by=${groupBy}&page=${page}&limit=${MESSAGES_PER_PAGE}` +
        `&message_sort=${encodeURIComponent(messageSort)}` +
        (level ? `&level=${encodeURIComponent(level)}` : "");

    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const data = normalizeStatisticsResponse(await response.json());
        currentMessagePage = data.top_messages_meta.page;
        totalMessagePages = data.top_messages_meta.pages;
        applyLogFileMetadata(data.log_file);
        renderStatistics(data);
        updateHeroMetrics(data.total_events);
        hideMessage();
        statsContainer.style.display = "block";
    } catch (error) {
        statsContainer.style.display = "none";
        updateHeroMetrics();
        showMessage(`Не удалось загрузить статистику: ${error.message}`, "error");
    }
}

async function loadMessagesPage(page) {
    if (!currentLogFileId) {
        return;
    }

    const level = levelSelect.value;
    const messageSort = messageSortSelect.value;
    const url = `/stats/file/${encodeURIComponent(String(currentLogFileId))}/messages?page=${page}&limit=${MESSAGES_PER_PAGE}` +
        `&message_sort=${encodeURIComponent(messageSort)}` +
        (level ? `&level=${encodeURIComponent(level)}` : "");

    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const data = await response.json();
        currentMessagePage = data.page;
        totalMessagePages = data.pages;
        renderMessagesTable(data.messages);
        updatePaginationButtons();
        hideMessage();
    } catch (error) {
        showMessage(`Не удалось загрузить список сообщений: ${error.message}`, "error");
    }
}

function applyLogFileMetadata(logFile) {
    if (!logFile) {
        return;
    }

    const index = uploadedFiles.findIndex((item) => item.log_file_id === logFile.id);
    const normalized = {
        log_file_id: logFile.id,
        filename: logFile.filename,
        detected_format: logFile.detected_format,
        parse_status: logFile.parse_status,
        line_count: logFile.line_count,
        uploaded_at: logFile.uploaded_at,
        last_parsed_at: logFile.last_parsed_at,
    };

    if (index >= 0) {
        uploadedFiles[index] = { ...uploadedFiles[index], ...normalized };
    } else {
        uploadedFiles.unshift(normalized);
    }

    currentLogFile = { ...currentLogFile, ...normalized };
    renderCurrentLogFileCard();
    renderUploadedFilesList();
}

async function startSummarization() {
    if (!currentLogFileId) {
        showMessage("Сначала выбери лог для суммаризации.", "error");
        return;
    }
    if (!isCurrentLogParsed()) {
        showMessage("Суммаризация не может запуститься до парсинга файла.", "error");
        return;
    }

    try {
        const response = await fetch(`/nlp/summarize?filename=${encodeURIComponent(String(currentLogFileId))}`, {
            method: "POST",
        });
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const result = await response.json();
        if (result.status === "processing") {
            showMessage("Суммаризация запущена. Таблица обновится автоматически после завершения.", "info");
            if (nlpPollTimer) {
                clearInterval(nlpPollTimer);
            }
            nlpPollTimer = setInterval(() => pollSummaries(currentLogFileId), NLP_POLL_INTERVAL_MS);
        }
    } catch (error) {
        showMessage(`Ошибка запуска суммаризации: ${error.message}`, "error");
    }
}

async function pollSummaries(logFileId) {
    try {
        const response = await fetch(
            `/nlp/summaries?file=${encodeURIComponent(String(logFileId))}` +
            `&message_sort=${encodeURIComponent(messageSortSelect.value)}`
        );
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const summaries = await response.json();
        const allDone = summaries.length > 0 && summaries.every((item) => item.summary !== null);
        if (allDone) {
            clearInterval(nlpPollTimer);
            nlpPollTimer = null;
            hideMessage();
            loadMessagesPage(currentMessagePage);
        }
    } catch (error) {
        clearInterval(nlpPollTimer);
        nlpPollTimer = null;
        showMessage(`Ошибка получения суммаризаций: ${error.message}`, "error");
    }
}

async function openSavedReport(reportId) {
    try {
        const response = await fetch(`/reports/${reportId}`);
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const report = await response.json();
        currentReportId = report.report_id;
        if (report.log_file_id) {
            const selected = uploadedFiles.find((item) => item.log_file_id === report.log_file_id);
            if (selected) {
                selectLogFile(report.log_file_id, { keepReport: true, loadStats: true });
            }
        }

        renderSavedReport(report);
        renderSavedReportsList();
        updateActionButtonAvailability();
        hideMessage();
    } catch (error) {
        showMessage(`Не удалось открыть сохранённый отчёт: ${error.message}`, "error");
    }
}

function renderSavedReport(report) {
    currentReportId = report.report_id;
    reportText.textContent = report.report || "";
    reportMeta.textContent = (
        `Отчёт #${report.report_id}, загрузка #${report.log_file_id}, файл ${report.filename || "не указан"}, ` +
        `формат ${report.detected_format || "unknown"}, создан ${formatDateTime(report.created_at)}`
    );
    reportContainer.style.display = "block";
}

async function generateReport() {
    if (!currentLogFileId) {
        showMessage("Сначала выбери лог для отчёта.", "error");
        return;
    }
    if (!isCurrentLogParsed()) {
        showMessage("Отчёт можно сформировать только после парсинга файла.", "error");
        return;
    }

    const level = levelSelect.value;
    const messageSort = messageSortSelect.value;
    try {
        const response = await fetch(
            `/reports/generate?filename=${encodeURIComponent(String(currentLogFileId))}` +
            `&message_sort=${encodeURIComponent(messageSort)}` +
            (level ? `&level=${encodeURIComponent(level)}` : ""),
            { method: "POST" }
        );
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const data = await response.json();
        renderSavedReport(data);
        reportMeta.textContent += `, объяснено сообщений: ${data.explained_messages_total}`;
        await loadReports({ selectId: data.report_id });
        hideMessage();
    } catch (error) {
        showMessage(`Ошибка генерации отчёта: ${error.message}`, "error");
    }
}

async function downloadPdf() {
    if (!currentReportId) {
        showMessage("Сначала сгенерируй новый отчёт или открой сохранённый.", "error");
        return;
    }

    try {
        const response = await fetch(`/reports/${currentReportId}/pdf`);
        if (!response.ok) {
            throw new Error(await response.text());
        }

        const blob = await response.blob();
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        const downloadName = `report_${currentReportId}.pdf`;
        link.download = downloadName;
        link.click();
        URL.revokeObjectURL(link.href);
        hideMessage();
    } catch (error) {
        showMessage(`Ошибка скачивания PDF: ${error.message}`, "error");
    }
}

function renderStatistics(data) {
    const range = {
        start: data.time_range.start || "—",
        end: data.time_range.end || "—",
    };
    const levelsStr = formatDictionary(data.by_level);
    const statusesStr = formatDictionary(data.by_status);
    const topIp = data.top_ips.length ? `${data.top_ips[0].ip_address} (${data.top_ips[0].count})` : "—";
    const topPath = data.top_paths.length ? `${data.top_paths[0].request_path} (${data.top_paths[0].count})` : "—";
    const errorRatio = `${formatPercent(data.error_ratio)} / 5xx ${formatPercent(data.status_5xx_ratio)}`;
    const sortLabel = data.top_messages_meta.sort_label || "частые сначала";

    summaryDiv.innerHTML = [
        createSummaryCard("Файл", data.filename, "summary-card-file"),
        createSummaryCard("ID загрузки", `#${data.log_file_id}`, "summary-card-upload-id"),
        createSummaryCard("Формат", data.detected_format || "unknown"),
        createSummaryCard("Всего событий", String(data.total_events)),
        createSummaryCard("Уровни", levelsStr || "—"),
        createSummaryCard("HTTP-статусы", statusesStr || "—", "summary-card-http-status"),
        createSummaryCard("Период", createValueLines([range.start, range.end]), "summary-card-period", true),
        createSummaryCard("Топ IP", topIp, "summary-card-top-ip"),
        createSummaryCard("Топ путь", topPath),
        createSummaryCard("Доля ошибок", errorRatio),
        createSummaryCard("Сортировка", sortLabel),
    ].join("");

    chartHint.textContent = `Агрегация: ${translateGroupBy(data.group_by)}. Источник данных: загрузка #${data.log_file_id}.`;
    anomalyMeta.textContent = `Найдено аномалий: ${data.anomalies.length}. Формат: ${data.detected_format}.`;
    renderAnomalies(data.anomalies);

    const ctx = document.getElementById("timeSeriesChart").getContext("2d");
    if (currentChart) {
        currentChart.destroy();
    }

    currentChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: data.time_series.map((item) => item.bucket),
            datasets: [
                {
                    label: "Количество событий",
                    data: data.time_series.map((item) => item.count),
                    borderColor: "rgb(17, 103, 216)",
                    backgroundColor: "rgba(17, 103, 216, 0.16)",
                    tension: 0.28,
                    fill: true,
                    pointRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: "Количество событий",
                    },
                },
                x: {
                    title: {
                        display: true,
                        text: "Временной интервал",
                    },
                },
            },
        },
    });

    renderMessagesTable(data.top_messages);
    updatePaginationButtons();
}

function renderAnomalies(anomalies) {
    anomaliesList.innerHTML = "";

    if (!anomalies.length) {
        anomaliesList.innerHTML = '<div class="empty-state">Явных аномалий по текущим правилам не найдено. Это тоже полезный результат для отчёта.</div>';
        return;
    }

    anomalies.forEach((anomaly) => {
        const item = document.createElement("div");
        item.className = "anomaly-item";
        item.innerHTML = `
            <small>${escapeHtml(anomaly.severity)}</small>
            <strong>${escapeHtml(anomaly.title)}</strong>
            <div>${escapeHtml(anomaly.description)}</div>
        `;
        anomaliesList.appendChild(item);
    });
}

function normalizeStatisticsResponse(data) {
    const safeData = { ...data };
    safeData.by_level = safeData.by_level || {};
    safeData.by_status = safeData.by_status || {};
    safeData.top_ips = Array.isArray(safeData.top_ips) ? safeData.top_ips : [];
    safeData.top_paths = Array.isArray(safeData.top_paths) ? safeData.top_paths : [];
    safeData.top_messages = Array.isArray(safeData.top_messages) ? safeData.top_messages : [];
    safeData.anomalies = Array.isArray(safeData.anomalies) ? safeData.anomalies : [];
    safeData.time_series = Array.isArray(safeData.time_series) ? safeData.time_series : [];
    safeData.time_range = safeData.time_range || { start: null, end: null };
    safeData.top_messages_meta = safeData.top_messages_meta || {
        page: 1,
        pages: 1,
        total: safeData.top_messages.length,
        limit: MESSAGES_PER_PAGE,
    };
    safeData.log_file = safeData.log_file || (currentLogFile ? {
        id: currentLogFile.log_file_id,
        filename: currentLogFile.filename,
        detected_format: currentLogFile.detected_format,
        parse_status: currentLogFile.parse_status,
        line_count: currentLogFile.line_count,
        uploaded_at: currentLogFile.uploaded_at,
        last_parsed_at: currentLogFile.last_parsed_at,
    } : null);
    safeData.error_ratio = Number(safeData.error_ratio || 0);
    safeData.status_5xx_ratio = Number(safeData.status_5xx_ratio || 0);
    return safeData;
}

function createSummaryCard(label, value, extraClass = "", valueIsHtml = false) {
    const className = ["summary-card", extraClass].filter(Boolean).join(" ");
    const safeValue = valueIsHtml ? value : escapeHtml(value || "—");
    return `
        <div class="${className}">
            <span>${escapeHtml(label)}</span>
            <strong>${safeValue}</strong>
        </div>
    `;
}

function createValueLines(values) {
    const lines = values.map((value) => `<div>${escapeHtml(value || "—")}</div>`).join("");
    return `<span class="summary-value-lines">${lines}</span>`;
}

function renderMessagesTable(messages) {
    tableBody.innerHTML = "";

    if (!messages.length) {
        const row = tableBody.insertRow();
        const cell = row.insertCell(0);
        cell.colSpan = 6;
        cell.textContent = "Для текущих фильтров сообщений не найдено.";
        return;
    }

    messages.forEach((messageItem) => {
        const row = tableBody.insertRow();
        row.insertCell(0).textContent = messageItem.message;
        row.insertCell(1).textContent = messageItem.count;
        row.insertCell(2).textContent = messageItem.level || "—";
        row.insertCell(3).textContent = formatDateTime(messageItem.first_seen);
        row.insertCell(4).textContent = formatDateTime(messageItem.last_seen);
        row.insertCell(5).textContent = messageItem.summary || "Суммаризация ещё не выполнена.";
    });
}

function updatePaginationButtons() {
    pageInfoSpan.textContent = `Страница ${currentMessagePage} из ${totalMessagePages}`;
    prevPageBtn.disabled = currentMessagePage <= 1;
    nextPageBtn.disabled = currentMessagePage >= totalMessagePages;
}

function setActionButtonsDisabled(disabled) {
    if (disabled) {
        parseBtn.disabled = true;
        loadBtn.disabled = true;
        summarizeBtn.disabled = true;
        reportBtn.disabled = true;
        exportPdfBtn.disabled = true;
    } else {
        updateActionButtonAvailability();
    }
    refreshUploadsBtn.disabled = disabled;
    if (clearUploadsBtn) {
        clearUploadsBtn.disabled = disabled;
    }
    refreshReportsBtn.disabled = disabled;
    if (clearReportsBtn) {
        clearReportsBtn.disabled = disabled;
    }
}

function isCurrentLogParsed() {
    return currentLogFile?.parse_status === "parsed";
}

function updateActionButtonAvailability() {
    const hasFile = Boolean(currentLogFileId);
    const parsed = isCurrentLogParsed();
    parseBtn.disabled = !hasFile;
    loadBtn.disabled = !hasFile || !parsed;
    summarizeBtn.disabled = !hasFile || !parsed;
    reportBtn.disabled = !hasFile || !parsed;
    exportPdfBtn.disabled = !currentReportId;
    refreshUploadsBtn.disabled = false;
    refreshReportsBtn.disabled = false;
    if (clearUploadsBtn) {
        clearUploadsBtn.disabled = uploadedFiles.length === 0;
    }
    if (clearReportsBtn) {
        clearReportsBtn.disabled = savedReports.length === 0;
    }
}

function showMessage(message, type = "info") {
    messageBox.textContent = message;
    messageBox.className = `message-box ${type}`;
}

function hideMessage() {
    messageBox.textContent = "";
    messageBox.className = "message-box";
}

function formatDictionary(values) {
    return Object.entries(values || {})
        .map(([key, value]) => `${key}: ${value}`)
        .join(", ");
}

function formatPercent(value) {
    return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function translateParseStatus(status) {
    const map = {
        uploaded: "загружен",
        parsed: "распарсен",
        failed: "ошибка парсинга",
    };
    return map[status] || status || "—";
}

function translateGroupBy(groupBy) {
    const map = {
        day: "по дням",
        hour: "по часам",
        minute: "по минутам",
    };
    return map[groupBy] || groupBy;
}

function formatDateTime(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return date.toLocaleString("ru-RU");
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
