"""
sources/cvm.py — coleta no Portal de Dados Abertos da CVM (Comissão de
Valores Mobiliários), conjunto "Cias Abertas: Documentos: Periódicos e
Eventuais (IPE)".

Fonte confirmada de acesso (estrutura real, não é suposição):
  https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe
  Arquivo por ano: https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ANO}.zip
  Dicionário de dados: https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/META/meta_ipe_cia_aberta.txt

Colunas confirmadas no CSV (dentro do zip): Assunto, Categoria,
CNPJ_Companhia, Codigo_CVM, Data_Entrega, Data_Referencia, Especie,
Link_Download, Nome_Companhia, Protocolo_Entrega, Tipo, Tipo_Apresentacao,
Versao.

Essa base cobre apenas COMPANHIAS ABERTAS (capital na bolsa) — é um
complemento ao DJEN/DataJud, não um substituto: pega o sinal de RJ/falência
direto do regulador do mercado de capitais, geralmente mais rápido e mais
confiável para empresas listadas do que aguardar a publicação judicial.

Categorias relevantes filtradas (coluna Categoria):
  - "Informações Companhias em Falência"
  - "Informações de Companhias em Recuperação Judicial ou Extrajudicial"
  - "Fato Relevante" (filtrado também pelo texto do Assunto, pois cobre
    qualquer assunto relevante, não só RJ/falência)

Nota: este ambiente de geração do projeto não teve saída de rede para
dados.cvm.gov.br — a estrutura foi confirmada via busca/fetch de página,
mas o download efetivo do CSV não pôde ser testado ao vivo. Rode
`python -c "import sources.cvm as cvm; print(cvm.collect([2026])[:3])"`
localmente para validar.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import datetime, timezone

import requests

from classify import classify_setor

BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
TIMEOUT = 60

CATEGORIAS_DIRETAS = {
    "Informações Companhias em Falência": "Falência",
    "Informações de Companhias em Recuperação Judicial ou Extrajudicial": "Recuperação Judicial",
}
PALAVRAS_FATO_RELEVANTE = ["recupera", "falência", "falencia"]


def _make_id(row: dict) -> str:
    base = row.get("Protocolo_Entrega") or f"{row.get('CNPJ_Companhia','')}-{row.get('Data_Entrega','')}-{row.get('Assunto','')[:50]}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()


def _classificar(row: dict) -> str | None:
    categoria = (row.get("Categoria") or "").strip()
    if categoria in CATEGORIAS_DIRETAS:
        tipo = CATEGORIAS_DIRETAS[categoria]
        assunto = (row.get("Assunto") or "").lower()
        if tipo == "Recuperação Judicial" and "extrajudicial" in assunto:
            return "Recuperação Extrajudicial"
        return tipo
    if categoria == "Fato Relevante":
        assunto = (row.get("Assunto") or "").lower()
        if any(p in assunto for p in PALAVRAS_FATO_RELEVANTE):
            if "extrajudicial" in assunto:
                return "Recuperação Extrajudicial"
            if "falência" in assunto or "falencia" in assunto:
                return "Falência"
            return "Recuperação Judicial"
    return None


def _formatar_cnpj(cnpj_bruto: str) -> str | None:
    d = "".join(c for c in (cnpj_bruto or "") if c.isdigit())
    if len(d) != 14:
        return cnpj_bruto or None
    return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"


def collect(anos: list[int]) -> list[dict]:
    """Baixa e filtra os documentos da CVM relevantes para os anos indicados."""
    registros: dict[str, dict] = {}
    for ano in anos:
        url = BASE_URL.format(ano=ano)
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[cvm] erro baixando {url}: {e}")
            continue

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            nomes_csv = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            for nome in nomes_csv:
                with zf.open(nome) as f:
                    texto = io.TextIOWrapper(f, encoding="latin-1")
                    reader = csv.DictReader(texto, delimiter=";")
                    for row in reader:
                        tipo = _classificar(row)
                        if not tipo:
                            continue
                        reg = _parse_row(row, tipo)
                        registros[reg["id"]] = reg

    return list(registros.values())


def _parse_row(row: dict, tipo: str) -> dict:
    empresa = (row.get("Nome_Companhia") or "").strip() or None
    cnpj = _formatar_cnpj(row.get("CNPJ_Companhia", ""))
    data_pub = row.get("Data_Entrega") or row.get("Data_Referencia") or ""
    assunto = row.get("Assunto") or ""

    return {
        "id": _make_id(row),
        "numero_processo": "",
        "tribunal": "",
        "orgao": "",
        "uf": None,  # não vem na CVM; pode ser preenchido depois via enriquecimento RFB pelo CNPJ
        "tipo": tipo,
        "empresa": empresa,
        "cnpj": cnpj,
        "setor": classify_setor((empresa or "") + " " + assunto),
        "data_publicacao": str(data_pub)[:10],
        "data_coleta": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte": "CVM",
        "link": row.get("Link_Download") or "",
        "texto": f"[{row.get('Categoria','')}] {assunto}"[:1500],
        "raw_json": row,
    }
