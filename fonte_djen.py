"""
scraper.py — coleta de publicações no DJEN (Diário de Justiça Eletrônico
Nacional) usando a API pública que alimenta o site https://comunica.pje.jus.br

IMPORTANTE — leia antes de usar em produção:
  * Essa API (comunicaapi.pje.jus.br) é pública e sem necessidade de login,
    mas NÃO é formalmente documentada/estável como uma API comercial. Os
    nomes de parâmetros usados abaixo (texto, dataDisponibilizacaoInicio,
    dataDisponibilizacaoFim, pagina, itensPorPagina) foram observados no
    front-end público. Se a CNJ/PJe alterar o contrato, ajuste PARAMS_MAP
    aqui — o resto do pipeline (db, classify, app) não precisa mudar porque
    guardamos o JSON bruto de cada registro.
  * Este ambiente de execução (sandbox usado para gerar o projeto) não tem
    saída de rede para comunicaapi.pje.jus.br, então este scraper não pôde
    ser testado ao vivo aqui. Rode localmente (`python -c "import scraper;
    scraper.debug_ping()"`) para validar antes de usar de verdade.
  * Seja educado com o servidor público: mantenha REQUEST_DELAY >= 1s e não
    dispare coletas em paralelo agressivas.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone

import requests

from classify import classify_setor, classify_tipo, extract_cnpj, extract_empresa, uf_from_tribunal

BASE_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
REQUEST_DELAY = 1.2  # segundos entre requisições, para não sobrecarregar o serviço público
TIMEOUT = 30

DEFAULT_TERMOS = [
    "recuperação judicial",
    "recuperação extrajudicial",
    "falência",
]

HEADERS = {
    "User-Agent": "MonitorRJ/1.0 (uso pessoal - monitoramento publico de RJ/falencias)",
    "Accept": "application/json",
}


def _make_id(item: dict) -> str:
    """Gera um id estável para dedup, baseado no id da comunicação (se houver)
    ou em hash do conteúdo."""
    base = str(item.get("id") or item.get("hash") or item.get("numero_processo", "") + item.get("texto", "")[:200])
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()


def fetch_page(termo: str, data_ini: date, data_fim: date, pagina: int = 1, itens_por_pagina: int = 100) -> dict:
    """Busca uma página de resultados no DJEN para um termo e intervalo de datas."""
    params = {
        "texto": termo,
        "dataDisponibilizacaoInicio": data_ini.isoformat(),
        "dataDisponibilizacaoFim": data_fim.isoformat(),
        "pagina": pagina,
        "itensPorPagina": itens_por_pagina,
    }
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def collect(termos: list[str] | None = None, dias_atras: int = 30, max_paginas_por_termo: int = 10) -> list[dict]:
    """Coleta publicações dos últimos `dias_atras` dias para cada termo em
    `termos`, converte em registros prontos para gravar no banco (ver db.py)
    e devolve a lista (ainda sem gravar)."""
    termos = termos or DEFAULT_TERMOS
    data_fim = date.today()
    data_ini = data_fim - timedelta(days=dias_atras)

    registros: dict[str, dict] = {}  # id -> registro, para dedup automático

    for termo in termos:
        pagina = 1
        while pagina <= max_paginas_por_termo:
            try:
                payload = fetch_page(termo, data_ini, data_fim, pagina=pagina)
            except requests.RequestException as e:
                print(f"[scraper] erro buscando '{termo}' pág {pagina}: {e}")
                break

            items = payload.get("items") or payload.get("result") or []
            if not items:
                break

            for item in items:
                reg = parse_item(item)
                if reg:
                    registros[reg["id"]] = reg

            # heurística de paginação: se veio menos que o pedido, é a última página
            if len(items) < 100:
                break
            pagina += 1
            time.sleep(REQUEST_DELAY)

        time.sleep(REQUEST_DELAY)

    return list(registros.values())


def parse_item(item: dict) -> dict | None:
    """Converte um item bruto da API do DJEN em um registro normalizado para o banco."""
    texto = item.get("texto") or item.get("teor") or ""
    tipo = classify_tipo(texto)
    if not tipo:
        return None  # não é um caso de RJ/Extrajudicial/Falência de fato

    tribunal = item.get("siglaTribunal") or item.get("tribunal") or item.get("nomeTribunal") or ""
    empresa = extract_empresa(texto)
    cnpj = extract_cnpj(texto)
    data_pub = item.get("data_publicacao") or item.get("dataDisponibilizacao") or ""

    reg = {
        "id": _make_id(item),
        "numero_processo": item.get("numero_processo") or item.get("numeroProcesso") or "",
        "tribunal": tribunal,
        "orgao": item.get("orgao") or item.get("nomeOrgao") or "",
        "uf": uf_from_tribunal(tribunal),
        "tipo": tipo,
        "empresa": empresa,
        "cnpj": cnpj,
        "setor": classify_setor((empresa or "") + " " + texto),
        "data_publicacao": str(data_pub)[:10] if data_pub else "",
        "data_coleta": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte": "DJEN",
        "link": item.get("link") or "",
        "texto": texto[:1500],
        "raw_json": item,
    }
    return reg


def debug_ping() -> None:
    """Teste manual rápido: roda `python -c "import scraper; scraper.debug_ping()"`
    localmente (com acesso à internet) para verificar se a API ainda responde
    no formato esperado."""
    payload = fetch_page("recuperação judicial", date.today() - timedelta(days=7), date.today(), pagina=1, itens_por_pagina=5)
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    debug_ping()
