"""
sources/ibge_geo.py — busca a malha geográfica (GeoJSON) dos estados
brasileiros na API pública do IBGE, para desenhar um mapa coroplético real
(em vez do gráfico de barras por UF).

Endpoint confirmado:
  https://servicodados.ibge.gov.br/api/v3/malhas/estados/{UF}?formato=application/vnd.geo+json
  https://servicodados.ibge.gov.br/api/v3/malhas/brasil?formato=application/vnd.geo+json&intrarregiao=UF
    (uma chamada só, já dividida por UF — preferível a 27 chamadas separadas)

Resultado é cacheado em memória pelo Streamlit (st.cache_data no app.py),
então isso só é buscado uma vez por sessão/servidor.
"""

from __future__ import annotations

import requests

BASE_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/brasil"
TIMEOUT = 30


def malha_estados_brasil() -> dict:
    """Devolve um GeoJSON (FeatureCollection) com a malha de todos os
    estados do Brasil, já subdividida por UF (propriedade `codarea`)."""
    params = {"formato": "application/vnd.geo+json", "intrarregiao": "UF", "qualidade": "minima"}
    resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# mapa código IBGE de UF (2 dígitos) -> sigla, para casar com a malha
CODIGO_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
