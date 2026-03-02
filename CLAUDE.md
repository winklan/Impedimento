# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**Sistema de Detecção de Impedimento Judicial** — a web application that analyzes judicial process PDFs and detects whether a summoned judge (*juiz convocado*) acted at the first degree, which would constitute a legal impediment to act at the second degree.

**Language**: Portuguese (Brazil)
**Tech Stack**: Python 3.10+, Streamlit, pdfplumber, pandas, openpyxl
**Entry point**: `app.py` (run with `streamlit run app.py`)

## File Structure

- `app.py` — Streamlit web interface, Excel/CSV export logic
- `detector.py` — Core detection engine (`DetectorImpedimento` class)
- `requirements.txt` — Python dependencies
- `iniciar.bat` — Windows launcher (activates venv and runs Streamlit)

## Architecture

### Core Class: `DetectorImpedimento` (`detector.py`)

Instantiated with the judge's name and optionally their court (*vara*). Exposes two public methods:

- `analisar_pdf(caminho_pdf: Path) -> ResultadoProcesso` — analyzes a single PDF
- `analisar_lote(arquivos: list[Path]) -> list[ResultadoProcesso]` — batch analysis

**Detection pipeline per page:**

1. Skip pages that are predominantly second-degree (acórdão, câmara, desembargador etc.) — `_paginas_sao_segundo_grau()`
2. Search for the judge's name using a flexible accent/spacing-tolerant regex — `_montar_regex_nome()`
3. For each name match, check the surrounding context (300-char window) for:
   - First-degree titles (`_TITULOS_PRIMEIRO_GRAU`)
   - Jurisdictional acts (`_ATOS_PRIMEIRO_GRAU`)
   - Signature blocks (`juiz de direito`, `ass.:`, `assinado por`)
4. Optionally search for the judge's court string across the full page

**Confidence classification (final result):**

| Level | Criteria |
|-------|----------|
| `alto` | `titulo` + `ato_jurisdicional`, or `assinatura` present |
| `medio` | `titulo` alone, or `vara` + ≥2 occurrences |
| `baixo` | only `ato_jurisdicional` or only `vara` |

### Data Classes (`detector.py`)

```python
@dataclass
class Ocorrencia:
    pagina: int
    contexto: str
    tipo: str   # "titulo" | "assinatura" | "ato_jurisdicional" | "vara"

@dataclass
class ResultadoProcesso:
    arquivo: str
    impedimento_detectado: bool
    nivel_confianca: str        # "alto" | "medio" | "baixo"
    ocorrencias: list[Ocorrencia]
    vara_identificada: str
    erro: str
```

### Interface (`app.py`)

- Sidebar: judge name input, optional court name input, confidence legend
- Main area: PDF uploader, analyze button, results table, per-process expanders with occurrence details
- Export: Excel (two tabs: Resumo + Ocorrências Detalhadas) and CSV download

## Development Workflow

### Running the application

```bash
# Activate virtual environment
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/macOS

streamlit run app.py
```

Or double-click `iniciar.bat` on Windows.

### Installing dependencies

```bash
pip install -r requirements.txt
```

### Testing changes

Streamlit auto-reloads on file save. For changes to `detector.py`, refresh the browser page. Check the terminal for Python errors.

There is no automated test suite — manual testing via the UI or direct Python calls is used:

```python
from pathlib import Path
from detector import DetectorImpedimento

d = DetectorImpedimento("João da Silva", "3ª Vara Cível")
r = d.analisar_pdf(Path("processo.pdf"))
print(r.resumo, r.ocorrencias)
```

## Important Notes

1. **Regex construction**: `_montar_regex_nome()` builds an accent-tolerant pattern. When names have fewer than two parts with 4+ characters, all parts are used. Be careful when modifying this — overly loose patterns cause false positives.

2. **Second-degree filter**: `_paginas_sao_segundo_grau()` requires **2 or more** second-degree indicators on a page to skip it. Raising this threshold reduces false negatives but increases false positives.

3. **Context window**: Occurrence context is extracted with a ±300-character window around the name match (`_extrair_contexto()`). Changing the window size affects both accuracy and readability of exported results.

4. **Vara identification**: `_identificar_vara_no_texto()` only scans the first 3000 characters of the full document text (assumed to be the header). This is intentional to avoid matching court names from the body.

5. **No persistent state**: The application is stateless — results exist only in the current Streamlit session. There is no database or file storage.

6. **PDF text extraction**: Uses `pdfplumber`. Scanned PDFs without an OCR text layer will produce empty text and result in no detections (not an error). The `erro` field on `ResultadoProcesso` captures actual exceptions (e.g., corrupt PDF).

## Common Tasks

### Adding a new first-degree title pattern

Add a regex string to `_TITULOS_PRIMEIRO_GRAU` in `detector.py`:

```python
_TITULOS_PRIMEIRO_GRAU = [
    ...
    r"novo\s+padr[ãa]o",
]
```

### Adding a new jurisdictional act keyword

Add to `_ATOS_PRIMEIRO_GRAU` in `detector.py`. Prefer `\b` word boundaries to avoid partial matches.

### Adding a new export format

Implement a function similar to `gerar_excel()` in `app.py` and add a `st.download_button` in the export section.

### Adjusting the second-degree filter sensitivity

Change the threshold in `_paginas_sao_segundo_grau()`:

```python
return contagem >= 2   # increase to 3 to be less aggressive
```
