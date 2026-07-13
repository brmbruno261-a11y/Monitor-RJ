"""
classify.py — heurísticas de classificação usadas pelo Monitor RJ.

Nenhuma dessas classificações é 100% precisa: publicações judiciais são texto
livre. O objetivo é dar um ponto de partida razoável para o dashboard; casos
importantes devem ser conferidos manualmente antes de qualquer decisão.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- tipo do caso

TIPO_KEYWORDS = {
    "Falência": [
        "decretação de falência", "decretacao de falencia", "falência da empresa",
        "falencia da empresa", "quebra da sociedade", "massa falida", "sentença de falência",
        "sentenca de falencia", "convolação em falência", "convolacao em falencia",
    ],
    "Recuperação Extrajudicial": [
        "recuperação extrajudicial", "recuperacao extrajudicial",
    ],
    "Recuperação Judicial": [
        "recuperação judicial", "recuperacao judicial",
    ],
}

# ordem importa: falência e extrajudicial são mais específicas, checar antes
TIPO_ORDEM = ["Falência", "Recuperação Extrajudicial", "Recuperação Judicial"]


def _strip_accents(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")


def classify_tipo(texto: str) -> str | None:
    if not texto:
        return None
    t = _strip_accents(texto.lower())
    for tipo in TIPO_ORDEM:
        for kw in TIPO_KEYWORDS[tipo]:
            if _strip_accents(kw.lower()) in t:
                return tipo
    return None


# ---------------------------------------------------------------- setor (heurístico)

SETOR_KEYWORDS = {
    "Agropecuária": ["agro", "agricola", "agropecuari", "pecuaria", "fazenda", "grãos", "graos", "cooperativa agr"],
    "Construção": ["construtora", "construção", "construcao", "incorporadora", "engenharia civil"],
    "Comércio/Varejo": ["comercio", "comércio", "varejo", "supermercado", "loja", "atacad", "magazine"],
    "Indústria": ["industria", "indústria", "fabril", "manufatura", "metalurg", "textil", "têxtil"],
    "Transporte/Logística": ["transporte", "transportadora", "logistica", "logística", "rodoviari"],
    "Energia": ["energia", "biocombustive", "biofuels", "usina", "combustivel", "combustível"],
    "Serviços": ["serviços", "servicos", "consultoria", "prestadora de serviço"],
    "Saúde": ["hospital", "clinica", "clínica", "saude", "saúde", "farmaceutic"],
    "Tecnologia": ["tecnologia", "software", "tecnologia da informacao", "tecnologia da informação"],
    "Imobiliário": ["imobiliaria", "imobiliária", "imoveis", "imóveis"],
}


def classify_setor(texto_ou_nome: str) -> str:
    if not texto_ou_nome:
        return "Não classificado"
    t = _strip_accents(texto_ou_nome.lower())
    for setor, kws in SETOR_KEYWORDS.items():
        for kw in kws:
            if _strip_accents(kw.lower()) in t:
                return setor
    return "Não classificado"


# ---------------------------------------------------------------- extração de entidades

CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")

# nomes empresariais costumam terminar em LTDA, S.A., S/A, EIRELI, ME, EPP, e outros
EMPRESA_RE = re.compile(
    r"([A-ZÀ-Ú0-9][A-ZÀ-Ú0-9\.\-&' ]{3,80}?\s(?:LTDA|S\.?A\.?|S/A|EIRELI|ME|EPP|EM RECUPERA[ÇC][ÃA]O JUDICIAL))",
    re.IGNORECASE,
)

UF_SIGLAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def extract_cnpj(texto: str) -> str | None:
    if not texto:
        return None
    m = CNPJ_RE.search(texto)
    return m.group(0) if m else None


def extract_empresa(texto: str) -> str | None:
    if not texto:
        return None
    m = EMPRESA_RE.search(texto)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(" .-")
    return None


def uf_from_tribunal(sigla_tribunal: str | None) -> str | None:
    """Deriva a UF a partir da sigla do tribunal, ex: TJSP -> SP, TRT2 -> SP (aprox.)."""
    if not sigla_tribunal:
        return None
    s = sigla_tribunal.upper()
    # tribunais estaduais: TJ + UF (TJSP, TJRJ, TJMG...)
    if s.startswith("TJ") and s[2:4] in UF_SIGLAS:
        return s[2:4]
    # último recurso: procura uma sigla de UF conhecida dentro do texto
    for uf in UF_SIGLAS:
        if s.endswith(uf):
            return uf
    return None
