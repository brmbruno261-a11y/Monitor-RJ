"""
sources/rfb_cnpj.py — enriquece os casos coletados com dados cadastrais REAIS
da Receita Federal (RFB Dados Abertos do CNPJ): razão social oficial, CNAE
(setor real, não heurística de texto), situação cadastral, porte, UF/
município do endereço, capital social, data de abertura.

Por que não baixamos o dump completo da RFB (~20GB compactado)?
  A base completa de CNPJ é distribuída pela Receita apenas como arquivos
  grandes em lote (não tem endpoint de consulta por CNPJ individual). Como
  aqui só precisamos enriquecer os CNPJs que já apareceram em casos de
  RJ/extrajudicial/falência (algumas centenas/milhares, não os ~60 milhões
  de CNPJs do Brasil), é muito mais eficiente consultar um a um via uma API
  pública que já espelha os dados da RFB por CNPJ: a BrasilAPI
  (https://brasilapi.com.br/api/cnpj/v1/{cnpj}), projeto open-source que lê
  diretamente da base oficial da Receita.

  Se no futuro você precisar da base completa (ex: para comparar "% do
  universo de empresas de um setor que entrou em RJ"), baixe os arquivos em
  https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/ (ou
  o espelho oficial vigente) e carregue localmente — não é uma operação
  adequada para rodar dentro do próprio app do Streamlit Cloud.

Limites e cuidados:
  * BrasilAPI é gratuita mas tem limite de requisições (nada documentado como
    contrato fixo) — por isso este módulo faz UMA requisição por CNPJ, com
    delay entre chamadas, e sempre grava o resultado em cache
    (tabela empresas_cnpj) para nunca reconsultar o mesmo CNPJ duas vezes.
  * Não foi testado ao vivo neste ambiente de geração (sem rede para
    brasilapi.com.br aqui). Valide localmente antes de confiar em produção.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from cnae import setor_por_cnae

BASE_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
REQUEST_DELAY = 1.0
TIMEOUT = 20


def _limpar_cnpj(cnpj: str) -> str:
    return "".join(c for c in (cnpj or "") if c.isdigit())


def consultar_cnpj(cnpj: str) -> dict:
    """Consulta um único CNPJ. Sempre devolve um registro (com campo `erro`
    preenchido em caso de falha), pronto para gravar em empresas_cnpj."""
    cnpj_digitos = _limpar_cnpj(cnpj)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    base_vazia = {
        "cnpj": cnpj_digitos,
        "razao_social": None, "nome_fantasia": None, "cnae_codigo": None,
        "cnae_descricao": None, "setor": "Não classificado",
        "situacao_cadastral": None, "uf": None, "municipio": None,
        "porte": None, "capital_social": None, "data_abertura": None,
        "atualizado_em": agora, "raw_json": None, "erro": None,
    }

    if len(cnpj_digitos) != 14:
        base_vazia["erro"] = "CNPJ inválido (não tem 14 dígitos)"
        return base_vazia

    try:
        resp = requests.get(BASE_URL.format(cnpj=cnpj_digitos), timeout=TIMEOUT)
        if resp.status_code == 404:
            base_vazia["erro"] = "CNPJ não encontrado na base da Receita"
            return base_vazia
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        base_vazia["erro"] = f"Falha na consulta: {e}"
        return base_vazia

    cnae_codigo = data.get("cnae_fiscal")
    return {
        "cnpj": cnpj_digitos,
        "razao_social": data.get("razao_social"),
        "nome_fantasia": data.get("nome_fantasia"),
        "cnae_codigo": str(cnae_codigo) if cnae_codigo else None,
        "cnae_descricao": data.get("cnae_fiscal_descricao"),
        "setor": setor_por_cnae(str(cnae_codigo) if cnae_codigo else None),
        "situacao_cadastral": data.get("descricao_situacao_cadastral"),
        "uf": data.get("uf"),
        "municipio": data.get("municipio"),
        "porte": data.get("porte"),
        "capital_social": data.get("capital_social"),
        "data_abertura": data.get("data_inicio_atividade"),
        "atualizado_em": agora,
        "raw_json": data,
        "erro": None,
    }


def enriquecer_lote(cnpjs: list[str]) -> list[dict]:
    """Consulta uma lista de CNPJs, respeitando um intervalo entre chamadas."""
    resultados = []
    for i, cnpj in enumerate(cnpjs):
        resultados.append(consultar_cnpj(cnpj))
        if i < len(cnpjs) - 1:
            time.sleep(REQUEST_DELAY)
    return resultados
