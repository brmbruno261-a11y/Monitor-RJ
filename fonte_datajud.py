"""
sources/datajud.py — coleta via API Pública do DataJud (CNJ).

Diferente do DJEN (que traz o texto de publicações), o DataJud traz
metadados estruturados do PROCESSO (classe, assuntos, órgão julgador,
datas, movimentações), indexados em Elasticsearch, um índice por tribunal.

IMPORTANTE — leia antes de usar:
  * Exige uma API Key. Duas formas de obter, conforme documentação vigente
    do CNJ (https://datajud-wiki.cnj.jus.br/api-publica/acesso/):
      1) Chave pública compartilhada, divulgada na wiki acima (pode mudar
         a qualquer momento por decisão do CNJ); ou
      2) Cadastro individual gratuito em https://datajud.cnj.jus.br
    Configure a chave na variável de ambiente DATAJUD_API_KEY ou cole-a
    diretamente no campo da barra lateral do dashboard.
  * Não existe endpoint único "todos os tribunais": é preciso consultar o
    índice de cada tribunal separadamente
    (https://api-publica.datajud.cnj.jus.br/api_publica_{alias}/_search).
    Este módulo já traz uma lista dos principais TJs; ajuste TRIBUNAIS conforme
    sua necessidade (adicionar TRTs, TRFs, STJ etc.).
  * A busca usa "match" textual nos campos assuntos.nome e classe.nome, que é
    o padrão observado em exemplos de uso da API — não há confirmação formal
    de que todo tribunal preenche esses campos da mesma forma, então trate
    resultados vazios com ceticismo (pode ser "não achou" ou "esse tribunal
    não indexa esse campo").
  * Este ambiente de geração do projeto não tem saída de rede para
    api-publica.datajud.cnj.jus.br — não foi testado ao vivo. Valide localmente.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone

import requests

from classify import classify_setor, classify_tipo, extract_cnpj, extract_empresa, uf_from_tribunal

BASE_URL = "https://api-publica.datajud.cnj.jus.br"
REQUEST_DELAY = 1.0
TIMEOUT = 30

# principais tribunais estaduais — adicione outros aliases conforme necessário
# (ex: "trf1".."trf6", "trt1".."trt24", "stj")
TRIBUNAIS = [
    "tjsp", "tjrj", "tjmg", "tjrs", "tjpr", "tjsc", "tjba", "tjgo",
    "tjpe", "tjce", "tjmt", "tjms", "tjes", "tjpa", "tjdft",
]

TERMOS_PADRAO = ["recuperação judicial", "recuperação extrajudicial", "falência"]


def _api_key() -> str | None:
    return os.environ.get("DATAJUD_API_KEY")


def _make_id(tribunal: str, hit: dict) -> str:
    base = f"datajud-{tribunal}-{hit.get('_id', '')}"
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()


def _query_dsl(termos: list[str], tamanho: int = 100) -> dict:
    return {
        "size": tamanho,
        "query": {
            "bool": {
                "should": [
                    {"match": {"assuntos.nome": termo}} for termo in termos
                ] + [
                    {"match": {"classe.nome": termo}} for termo in termos
                ],
                "minimum_should_match": 1,
            }
        },
    }


def buscar_tribunal(tribunal: str, termos: list[str], api_key: str, tamanho: int = 100) -> list[dict]:
    url = f"{BASE_URL}/api_publica_{tribunal}/_search"
    headers = {"Authorization": f"APIKey {api_key}", "Content-Type": "application/json"}
    resp = requests.post(url, json=_query_dsl(termos, tamanho), headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("hits", {}).get("hits", [])


def collect(termos: list[str] | None = None, tribunais: list[str] | None = None, api_key: str | None = None) -> list[dict]:
    """Coleta processos nos tribunais indicados e converte em registros para o banco."""
    termos = termos or TERMOS_PADRAO
    tribunais = tribunais or TRIBUNAIS
    api_key = api_key or _api_key()
    if not api_key:
        raise ValueError(
            "Nenhuma DATAJUD_API_KEY configurada. Veja instruções em "
            "https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
        )

    registros: dict[str, dict] = {}
    for tribunal in tribunais:
        try:
            hits = buscar_tribunal(tribunal, termos, api_key)
        except requests.RequestException as e:
            print(f"[datajud] erro em {tribunal}: {e}")
            time.sleep(REQUEST_DELAY)
            continue

        for hit in hits:
            reg = parse_hit(tribunal, hit)
            if reg:
                registros[reg["id"]] = reg
        time.sleep(REQUEST_DELAY)

    return list(registros.values())


def parse_hit(tribunal: str, hit: dict) -> dict | None:
    fonte = hit.get("_source", {})
    assuntos_txt = " ".join(a.get("nome", "") for a in fonte.get("assuntos", []) if isinstance(a, dict))
    classe_nome = (fonte.get("classe") or {}).get("nome", "")
    texto_busca = f"{classe_nome} {assuntos_txt}"

    tipo = classify_tipo(texto_busca)
    if not tipo:
        return None

    numero = fonte.get("numeroProcesso", "")
    orgao = (fonte.get("orgaoJulgador") or {}).get("nome", "")
    data_ajuizamento = fonte.get("dataAjuizamento", "")

    reg = {
        "id": _make_id(tribunal, hit),
        "numero_processo": numero,
        "tribunal": tribunal.upper(),
        "orgao": orgao,
        "uf": uf_from_tribunal(tribunal.upper()),
        "tipo": tipo,
        "empresa": None,  # DataJud normalmente não expõe nome de partes na API pública
        "cnpj": extract_cnpj(str(fonte)),
        "setor": classify_setor(texto_busca),
        "data_publicacao": str(data_ajuizamento)[:10] if data_ajuizamento else "",
        "data_coleta": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte": "DataJud",
        "link": "",
        "texto": f"Classe: {classe_nome} | Assuntos: {assuntos_txt}"[:1500],
        "raw_json": fonte,
    }
    return reg
