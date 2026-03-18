/**
 * Codice Civile Sistematico — Frontend Application
 */
(function () {
    "use strict";

    // --- State ---
    let sessionToken = "";
    let history = [];
    const MAX_HISTORY = 10;

    // --- DOM refs ---
    const queryInput = document.getElementById("query-input");
    const btnSearch = document.getElementById("btn-search");
    const btnReset = document.getElementById("btn-reset");
    const themeToggle = document.getElementById("theme-toggle");
    const themeIcon = document.getElementById("theme-icon");
    const llmBadge = document.getElementById("llm-badge");
    const welcome = document.getElementById("welcome");
    const resultsArea = document.getElementById("results-area");
    const llmAnswerCard = document.getElementById("llm-answer-card");
    const llmAnswerText = document.getElementById("llm-answer-text");
    const searchResults = document.getElementById("search-results");
    const loading = document.getElementById("loading");
    const ingestBanner = document.getElementById("ingest-banner");
    const ingestMessage = document.getElementById("ingest-message");
    const ingestPercent = document.getElementById("ingest-percent");
    const ingestProgress = document.getElementById("ingest-progress");
    const historyList = document.getElementById("history-list");
    const filterLibro = document.getElementById("filter-libro");
    const filterTipo = document.getElementById("filter-tipo");

    // --- Auth: extract token from URL or fetch from API ---
    function getTokenFromURL() {
        const params = new URLSearchParams(window.location.search);
        return params.get("token") || "";
    }

    // --- API helper ---
    async function apiCall(method, path, body) {
        const opts = {
            method: method,
            headers: {
                "Content-Type": "application/json",
                "X-Session-Token": sessionToken,
            },
        };
        if (body) {
            opts.body = JSON.stringify(body);
        }
        const url = path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(sessionToken);
        const res = await fetch(url, opts);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ error: res.statusText }));
            throw new Error(err.error || `HTTP ${res.status}`);
        }
        return res.json();
    }

    // --- Theme ---
    function initTheme() {
        const saved = localStorage.getItem("theme") || "light";
        document.documentElement.setAttribute("data-theme", saved);
        themeIcon.textContent = saved === "dark" ? "\u2600" : "\u263E";
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute("data-theme");
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("theme", next);
        themeIcon.textContent = next === "dark" ? "\u2600" : "\u263E";
    }

    // --- Mode ---
    function getSelectedMode() {
        const checked = document.querySelector('input[name="mode"]:checked');
        return checked ? checked.value : "search";
    }

    function setMode(mode) {
        const radio = document.querySelector(`input[name="mode"][value="${mode}"]`);
        if (radio) radio.checked = true;
    }

    // --- History ---
    function addToHistory(query) {
        history = history.filter((h) => h !== query);
        history.unshift(query);
        if (history.length > MAX_HISTORY) history.pop();
        renderHistory();
    }

    function renderHistory() {
        historyList.innerHTML = "";
        history.forEach((q) => {
            const li = document.createElement("li");
            li.textContent = q;
            li.title = q;
            li.addEventListener("click", () => {
                queryInput.value = q;
                performSearch();
            });
            historyList.appendChild(li);
        });
    }

    // --- Ingestion status polling ---
    let ingestPollTimer = null;

    async function checkIngestStatus() {
        try {
            const data = await apiCall("GET", "/api/status");
            sessionToken = data.token || sessionToken;

            // LLM badge
            if (data.has_llm) {
                llmBadge.textContent = "LLM: Attivo";
                llmBadge.className = "badge badge-on";
            } else {
                llmBadge.textContent = "LLM: Non configurato";
                llmBadge.className = "badge badge-off";
            }

            const ingest = data.ingest;
            if (ingest.status === "in_progress") {
                ingestBanner.classList.remove("hidden");
                ingestMessage.textContent = ingest.message || "Indicizzazione in corso...";
                ingestPercent.textContent = Math.round(ingest.progress) + "%";
                ingestProgress.style.width = ingest.progress + "%";
                if (!ingestPollTimer) {
                    ingestPollTimer = setInterval(checkIngestStatus, 3000);
                }
            } else if (ingest.status === "completed") {
                ingestBanner.classList.add("hidden");
                if (ingestPollTimer) {
                    clearInterval(ingestPollTimer);
                    ingestPollTimer = null;
                }
            } else if (ingest.status === "error") {
                ingestBanner.classList.remove("hidden");
                ingestMessage.textContent = "Errore: " + (ingest.error || "sconosciuto");
                ingestPercent.textContent = "";
                ingestProgress.style.width = "0%";
                if (ingestPollTimer) {
                    clearInterval(ingestPollTimer);
                    ingestPollTimer = null;
                }
            } else if (ingest.status === "not_started" && !data.indexed) {
                ingestBanner.classList.remove("hidden");
                ingestMessage.textContent = "In attesa del file PDF per l'indicizzazione...";
                ingestPercent.textContent = "";
                ingestProgress.style.width = "0%";
                if (!ingestPollTimer) {
                    ingestPollTimer = setInterval(checkIngestStatus, 5000);
                }
            } else {
                ingestBanner.classList.add("hidden");
            }
        } catch (e) {
            console.error("Status check failed:", e);
        }
    }

    // --- Search ---
    async function performSearch() {
        const query = queryInput.value.trim();
        if (!query || query.length < 3) return;

        const mode = getSelectedMode();
        const libro = filterLibro.value || null;
        const tipo = filterTipo.value || null;

        // UI: show loading
        welcome.classList.add("hidden");
        resultsArea.classList.add("hidden");
        loading.classList.remove("hidden");
        llmAnswerCard.classList.add("hidden");
        searchResults.innerHTML = "";

        addToHistory(query);

        try {
            const data = await apiCall("POST", "/api/query", {
                question: query,
                mode: mode,
                libro_filter: libro,
                tipo_filter: tipo,
            });

            loading.classList.add("hidden");
            resultsArea.classList.remove("hidden");

            // LLM answer
            if (data.answer) {
                llmAnswerCard.classList.remove("hidden");
                llmAnswerText.textContent = data.answer;
            }

            // Search results cards
            if (data.results && data.results.length > 0) {
                renderResults(data.results);
            } else {
                searchResults.innerHTML = '<p class="no-results">Nessun risultato trovato.</p>';
            }
        } catch (e) {
            loading.classList.add("hidden");
            resultsArea.classList.remove("hidden");
            llmAnswerCard.classList.remove("hidden");
            llmAnswerText.textContent = "Errore: " + e.message;
        }
    }

    // --- Render results ---
    function renderResults(results) {
        searchResults.innerHTML = "";
        results.forEach((r, idx) => {
            const card = document.createElement("div");
            card.className = "result-card";

            const meta = r.metadata || {};
            const tipo = meta.tipo_contenuto || "norma";
            const articles = meta.articoli || [];
            const artStr = articles.length > 0
                ? articles.map((a) => "Art. " + a + " c.c.").join(", ")
                : "";

            const locationParts = [];
            if (meta.libro) locationParts.push(meta.libro);
            if (meta.titolo) locationParts.push(meta.titolo);
            if (meta.capo) locationParts.push(meta.capo);

            const scorePercent = Math.round((r.score || 0) * 100);

            card.innerHTML = `
                <div class="result-header">
                    <div class="result-meta">
                        <span class="tag tag-${tipo}">${formatTipo(tipo)}</span>
                        ${artStr ? `<span class="result-articles">${escapeHTML(artStr)}</span>` : ""}
                        <span class="tag tag-page">Pag. ${meta.pagina || "?"}</span>
                        <span class="score-bar" title="Rilevanza: ${scorePercent}%">
                            <span class="score-fill" style="width: ${scorePercent}%"></span>
                        </span>
                    </div>
                    <div class="result-actions">
                        <button class="copy-btn" data-idx="${idx}" title="Copia testo">&#128203;</button>
                    </div>
                </div>
                ${locationParts.length > 0 ? `<div class="result-location">${escapeHTML(locationParts.join(" > "))}</div>` : ""}
                <div class="result-text">${escapeHTML(r.content)}</div>
            `;

            // Copy button
            card.querySelector(".copy-btn").addEventListener("click", () => {
                const text = r.content;
                navigator.clipboard.writeText(text).then(() => {
                    const btn = card.querySelector(".copy-btn");
                    btn.textContent = "\u2713";
                    setTimeout(() => { btn.innerHTML = "&#128203;"; }, 1500);
                });
            });

            searchResults.appendChild(card);
        });
    }

    function formatTipo(tipo) {
        const map = {
            norma: "Norma",
            relazione: "Relazione",
            giurisprudenza: "Giurisprudenza",
            fonte_storica: "Fonte storica",
        };
        return map[tipo] || tipo;
    }

    function escapeHTML(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // --- Copy answer ---
    document.querySelectorAll(".copy-btn[data-target]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-target");
            const el = document.getElementById(targetId);
            if (el) {
                navigator.clipboard.writeText(el.textContent).then(() => {
                    btn.textContent = "\u2713";
                    setTimeout(() => { btn.innerHTML = "&#128203;"; }, 1500);
                });
            }
        });
    });

    // --- Example buttons ---
    document.querySelectorAll(".example-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            queryInput.value = btn.getAttribute("data-query");
            const mode = btn.getAttribute("data-mode");
            if (mode) setMode(mode);
            performSearch();
        });
    });

    // --- Event listeners ---
    btnSearch.addEventListener("click", performSearch);

    queryInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") performSearch();
    });

    btnReset.addEventListener("click", () => {
        filterLibro.value = "";
        filterTipo.value = "";
        setMode("search");
        queryInput.value = "";
        welcome.classList.remove("hidden");
        resultsArea.classList.add("hidden");
        loading.classList.add("hidden");
    });

    themeToggle.addEventListener("click", toggleTheme);

    // --- Init ---
    function init() {
        initTheme();
        sessionToken = getTokenFromURL();

        // Try to get token from API if not in URL
        if (!sessionToken) {
            apiCall("GET", "/api/status")
                .then((data) => {
                    sessionToken = data.token || "";
                    checkIngestStatus();
                })
                .catch(() => {
                    // Token required - show message
                    llmAnswerCard.classList.remove("hidden");
                    resultsArea.classList.remove("hidden");
                    welcome.classList.add("hidden");
                    llmAnswerText.textContent =
                        "Autenticazione richiesta. Usa il link con il token fornito all'avvio del server.";
                });
        } else {
            checkIngestStatus();
        }
    }

    init();
})();
