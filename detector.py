"""
Módulo de detecção de impedimento judicial.

Analisa PDFs de processos e verifica se o juiz convocado atuou
no primeiro grau, configurando impedimento legal.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber


# ---------------------------------------------------------------------------
# Padrões de detecção
# ---------------------------------------------------------------------------

# Títulos que indicam atuação como juiz de primeiro grau
_TITULOS_PRIMEIRO_GRAU = [
    r"ju[íi]z(?:a)?\s+de\s+direito",
    r"mm\.?\s*ju[íi]z(?:a)?",
    r"meritíssimo",
    r"dr\.?\s*ju[íi]z(?:a)?",
    r"ju[íi]z(?:a)?\s+titular",
    r"ju[íi]z(?:a)?\s+substitut[ao]",
    r"ju[íi]z(?:a)?\s+auxiliar",
    r"ju[íi]z(?:a)?\s+plantonista",
]

# Palavras-chave de atos jurisdicionais de primeiro grau
_ATOS_PRIMEIRO_GRAU = [
    r"\bvistos\b",
    r"\bdecido\b",
    r"\bsentenci[ao]\b",
    r"\bsenten[çc]a\b",
    r"\bdespacho\b",
    r"\bdecis[ãa]o\b",
    r"\baudien[çc]ia\b",
    r"\bjulgado\b",
    r"\bpublique-se\b",
    r"\bintimem-se\b",
    r"\bcite-se\b",
    r"\bante\s+o\s+exposto\b",
    r"\bisto\s+posto\b",
    r"\bex\s+positis\b",
    r"\bjulgo\b",
    r"\bacolho\b",
    r"\bcondemno\b",
    r"\babsolvo\b",
    r"\bhomologo\b",
    r"\bconcedo\b",
    r"\bnego\b",
    r"\bprescri[çc][ãa]o\b",
]

# Padrões que identificam a vara do juiz no cabeçalho do documento
_PADROES_VARA = [
    r"\d+[aª°]\s*vara\s+c[íi]vel",
    r"\d+[aª°]\s*vara\s+de\s+fam[íi]lia",
    r"\d+[aª°]\s*vara\s+criminal",
    r"vara\s+(?:(?:do|de|da)\s+)?\w+(?:\s+\w+)?",
    r"comarca\s+de\s+\w+",
    r"juizado\s+especial",
]

# Indicadores de tribunal (segundo grau) – para evitar falsos positivos
_INDICADORES_SEGUNDO_GRAU = [
    r"\btribunal\b",
    r"\bcamara\b",
    r"\bcâmara\b",
    r"\bdesembargador\b",
    r"\brelator\b",
    r"\bac[óo]rd[ãa]o\b",
    r"\bem\s+grau\s+de\s+recurso\b",
    r"\bapela[çc][ãa]o\b",
    r"\bagravo\s+de\s+instrumento\b",
    r"\bembargos\s+de\s+declara[çc][ãa]o\b",
]


# ---------------------------------------------------------------------------
# Estruturas de dados
# ---------------------------------------------------------------------------

@dataclass
class Ocorrencia:
    pagina: int
    contexto: str
    tipo: str  # "titulo", "assinatura", "vara", "ato_jurisdicional"


@dataclass
class ResultadoProcesso:
    arquivo: str
    impedimento_detectado: bool
    nivel_confianca: str  # "alto", "medio", "baixo"
    ocorrencias: list[Ocorrencia] = field(default_factory=list)
    vara_identificada: str = ""
    erro: str = ""

    @property
    def resumo(self) -> str:
        if self.erro:
            return f"Erro ao processar: {self.erro}"
        if self.impedimento_detectado:
            return f"IMPEDIMENTO DETECTADO (confiança: {self.nivel_confianca.upper()})"
        return "Sem impedimento identificado"


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas para comparação."""
    nfd = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return sem_acento.lower()


def _montar_regex_nome(nome_juiz: str) -> re.Pattern:
    """
    Monta um padrão que casa o nome do juiz de forma flexível:
    - ignora acentuação
    - permite variações de espaçamento
    - case-insensitive
    """
    partes = nome_juiz.strip().split()
    # Aceita qualquer parte do nome com pelo menos 4 caracteres como ancora
    partes_relevantes = [p for p in partes if len(p) >= 4]
    if not partes_relevantes:
        partes_relevantes = partes

    # Monta regex: cada parte pode ter acentuação variada
    fragmentos = []
    for parte in partes_relevantes:
        # Substitui letras acentuadas por classe de caracteres
        frag = ""
        for c in parte:
            cn = _normalizar(c)
            if cn != c.lower():
                frag += f"[{c}{cn}]"
            else:
                classes = {
                    "a": "[aáâãà]", "e": "[eéêè]", "i": "[iíî]",
                    "o": "[oóôõò]", "u": "[uúûù]", "c": "[cç]",
                }
                frag += classes.get(c.lower(), re.escape(c))
        fragmentos.append(frag)

    # Padrão: nome completo OU pelo menos dois fragmentos consecutivos
    padrao_completo = r"\s+".join(fragmentos)
    return re.compile(padrao_completo, re.IGNORECASE)


def _extrair_contexto(texto: str, pos_inicio: int, pos_fim: int, janela: int = 300) -> str:
    """Extrai trecho de texto ao redor da ocorrência."""
    inicio = max(0, pos_inicio - janela)
    fim = min(len(texto), pos_fim + janela)
    trecho = texto[inicio:fim].strip()
    # Limpa quebras de linha excessivas
    trecho = re.sub(r"\n{3,}", "\n\n", trecho)
    return trecho


def _paginas_sao_segundo_grau(texto_pagina: str) -> bool:
    """Heurística: verifica se a página é predominantemente de segundo grau."""
    texto_norm = _normalizar(texto_pagina)
    contagem = sum(
        1 for p in _INDICADORES_SEGUNDO_GRAU
        if re.search(p, texto_norm)
    )
    return contagem >= 2


# ---------------------------------------------------------------------------
# Detector principal
# ---------------------------------------------------------------------------

class DetectorImpedimento:
    """
    Analisa um PDF e determina se o juiz convocado atuou
    no primeiro grau do processo.
    """

    def __init__(self, nome_juiz: str, vara_juiz: str = ""):
        self.nome_juiz = nome_juiz.strip()
        self.vara_juiz = vara_juiz.strip()
        self._re_nome = _montar_regex_nome(nome_juiz)
        self._re_titulos = [
            re.compile(p, re.IGNORECASE) for p in _TITULOS_PRIMEIRO_GRAU
        ]
        self._re_atos = [
            re.compile(p, re.IGNORECASE) for p in _ATOS_PRIMEIRO_GRAU
        ]
        self._re_vara_patterns = [
            re.compile(p, re.IGNORECASE) for p in _PADROES_VARA
        ]
        self._re_vara_juiz: re.Pattern | None = None
        if vara_juiz:
            self._re_vara_juiz = re.compile(
                re.escape(vara_juiz), re.IGNORECASE
            )

    # ------------------------------------------------------------------
    # Análise por página
    # ------------------------------------------------------------------

    def _verificar_pagina(
        self, texto: str, num_pagina: int
    ) -> list[Ocorrencia]:
        ocorrencias: list[Ocorrencia] = []

        # Ignora páginas claramente de segundo grau
        if _paginas_sao_segundo_grau(texto):
            return ocorrencias

        # 1. Nome do juiz na página?
        matches_nome = list(self._re_nome.finditer(texto))
        if not matches_nome:
            return ocorrencias

        for match in matches_nome:
            contexto = _extrair_contexto(texto, match.start(), match.end())
            contexto_norm = _normalizar(contexto)

            # 2. Nome próximo a título de primeiro grau?
            for re_titulo in self._re_titulos:
                if re_titulo.search(contexto):
                    ocorrencias.append(Ocorrencia(
                        pagina=num_pagina,
                        contexto=contexto,
                        tipo="titulo",
                    ))
                    break

            # 3. Nome próximo a ato jurisdicional de primeiro grau?
            for re_ato in self._re_atos:
                if re_ato.search(contexto_norm):
                    ocorrencias.append(Ocorrencia(
                        pagina=num_pagina,
                        contexto=contexto,
                        tipo="ato_jurisdicional",
                    ))
                    break

            # 4. Nome em bloco de assinatura (fim de decisão)?
            if re.search(
                r"(juiz[ao]?\s+de\s+direito|ass\.?\s*:|assinado\s+por)",
                contexto,
                re.IGNORECASE,
            ):
                ocorrencias.append(Ocorrencia(
                    pagina=num_pagina,
                    contexto=contexto,
                    tipo="assinatura",
                ))

        # 5. Vara do juiz mencionada na página?
        if self._re_vara_juiz and self._re_vara_juiz.search(texto):
            m = self._re_vara_juiz.search(texto)
            ocorrencias.append(Ocorrencia(
                pagina=num_pagina,
                contexto=_extrair_contexto(texto, m.start(), m.end(), 200),
                tipo="vara",
            ))

        return ocorrencias

    def _identificar_vara_no_texto(self, texto: str) -> str:
        """Tenta identificar a vara do processo no texto."""
        for re_v in self._re_vara_patterns:
            m = re_v.search(texto)
            if m:
                return m.group(0).strip()
        return ""

    # ------------------------------------------------------------------
    # Análise do arquivo
    # ------------------------------------------------------------------

    def analisar_pdf(self, caminho_pdf: Path) -> ResultadoProcesso:
        resultado = ResultadoProcesso(
            arquivo=caminho_pdf.name,
            impedimento_detectado=False,
            nivel_confianca="baixo",
        )

        try:
            with pdfplumber.open(caminho_pdf) as pdf:
                texto_completo = ""
                for num_pagina, pagina in enumerate(pdf.pages, start=1):
                    texto = pagina.extract_text() or ""
                    texto_completo += f"\n{texto}"

                    ocorrencias_pagina = self._verificar_pagina(texto, num_pagina)
                    resultado.ocorrencias.extend(ocorrencias_pagina)

                # Identifica vara mencionada no documento
                resultado.vara_identificada = self._identificar_vara_no_texto(
                    texto_completo[:3000]  # cabeçalho do processo
                )

        except Exception as exc:
            resultado.erro = str(exc)
            return resultado

        # ------------------------------------------------------------------
        # Classificação final
        # ------------------------------------------------------------------
        if not resultado.ocorrencias:
            resultado.impedimento_detectado = False
            resultado.nivel_confianca = "alto"  # alto = certeza de ausência
            return resultado

        tipos = {o.tipo for o in resultado.ocorrencias}

        # Alta confiança: título + ato OU assinatura
        if ("titulo" in tipos and "ato_jurisdicional" in tipos) or "assinatura" in tipos:
            resultado.impedimento_detectado = True
            resultado.nivel_confianca = "alto"

        # Média confiança: título sozinho ou vara + nome
        elif "titulo" in tipos or ("vara" in tipos and len(resultado.ocorrencias) >= 2):
            resultado.impedimento_detectado = True
            resultado.nivel_confianca = "medio"

        # Baixa confiança: apenas ato jurisdicional ou apenas vara
        elif "ato_jurisdicional" in tipos or "vara" in tipos:
            resultado.impedimento_detectado = True
            resultado.nivel_confianca = "baixo"

        return resultado

    def analisar_lote(self, arquivos: list[Path]) -> list[ResultadoProcesso]:
        """Analisa múltiplos PDFs e retorna lista de resultados."""
        resultados = []
        for arquivo in arquivos:
            r = self.analisar_pdf(arquivo)
            resultados.append(r)
        return resultados
