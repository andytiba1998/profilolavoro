# Codice Civile Sistematico — Assistente Giuridico AI

Applicazione web locale per la ricerca semantica e l'analisi giuridica del Codice Civile italiano, con supporto RAG (Retrieval Augmented Generation).

## Funzionalita

- **Ricerca semantica**: cerca articoli per parola chiave o concetto giuridico
- **Ricerca per articolo**: cerca direttamente un articolo (es. "art. 1453")
- **Analisi casistica**: analizza situazioni giuridiche concrete con risposta strutturata
- **Filtri**: filtra per Libro (I-VI), tipo contenuto (norma, relazione, giurisprudenza, fonte storica)
- **Metadati strutturali**: ogni risultato mostra Libro, Titolo, Capo, numero pagina PDF
- **Fallback senza LLM**: funziona anche senza API key (solo ricerca semantica)
- **Tema chiaro/scuro**
- **Sicurezza**: accesso solo da localhost, token di sessione, rate limiting, sanitizzazione input

## Requisiti

- Python 3.10+
- Il file `Codice-civile-Sistematico.pdf` nella cartella `data/`

## Installazione e avvio

```bash
# 1. Installa le dipendenze
pip install -r requirements.txt

# 2. Configura il file .env
cp .env.example .env
# Modifica .env inserendo la tua API key (Anthropic o OpenAI)

# 3. Posiziona il PDF
# Copia Codice-civile-Sistematico.pdf nella cartella data/

# 4. Avvia il server
python app/main.py
```

Al primo avvio verra stampato un token di accesso nella console. Apri il link mostrato nel browser:

```
http://localhost:8000/?token=IL_TUO_TOKEN
```

La prima indicizzazione del PDF (1.486 pagine) richiede 5-15 minuti. Una barra di progresso viene mostrata nell'interfaccia. Ai successivi avvii il vector store viene ricaricato istantaneamente.

## Stack tecnico

| Componente | Tecnologia |
|---|---|
| Backend | Python + FastAPI |
| Vector store | ChromaDB (locale) |
| Embedding | sentence-transformers (paraphrase-multilingual-mpnet-base-v2) |
| PDF parsing | pdfplumber |
| LLM | Anthropic Claude / OpenAI (configurabile) |
| Frontend | HTML5 + CSS3 + JavaScript vanilla |
| Sicurezza | Token auth, localhost-only, rate limiting, CSP headers |

## Struttura del progetto

```
codice-civile-ai/
├── app/
│   ├── main.py         # Entry point FastAPI + middleware sicurezza
│   ├── ingest.py       # Estrazione PDF e indicizzazione ChromaDB
│   ├── retriever.py    # Pipeline RAG (ricerca + risposta LLM)
│   ├── models.py       # Schemi Pydantic con validazione input
│   └── config.py       # Configurazione + token sessione
├── static/
│   ├── index.html      # Interfaccia utente
│   ├── style.css       # Stili (tema chiaro/scuro)
│   └── app.js          # Logica frontend
├── data/               # PDF + vector store (non committati)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Disclaimer

Questa applicazione non costituisce consulenza legale. Per consulenza specifica, rivolgersi a un avvocato.
