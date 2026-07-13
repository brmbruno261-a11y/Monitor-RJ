"""
db.py — camada de persistência do Monitor RJ.

Guarda os casos coletados (Recuperação Judicial, Recuperação Extrajudicial e
Falências) em um banco SQLite local. Cada registro guarda também o JSON bruto
recebido da fonte, para permitir reprocessar/reclassificar sem precisar
coletar de novo (a API do DJEN é pública mas não é oficialmente documentada,
então campos podem mudar).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

DB_PATH = Path(__file__).parent / "monitor_rj.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS casos (
    id                  TEXT PRIMARY KEY,   -- hash estável do registro (evita duplicados)
    numero_processo     TEXT,
    tribunal            TEXT,               -- sigla, ex: TJSP, TRF1
    orgao               TEXT,               -- vara/órgão julgador
    uf                  TEXT,
    tipo                TEXT,               -- Recuperação Judicial | Recuperação Extrajudicial | Falência
    empresa             TEXT,               -- nome extraído (melhor esforço)
    cnpj                TEXT,
    setor               TEXT,               -- classificação heurística de setor
    data_publicacao     TEXT,               -- ISO yyyy-mm-dd
    data_coleta         TEXT,               -- ISO datetime de quando foi coletado
    fonte               TEXT,               -- DJEN | manual | csv | exemplo
    link                TEXT,
    texto               TEXT,               -- trecho do teor da publicação
    raw_json            TEXT                -- payload bruto da fonte, se houver
);
CREATE INDEX IF NOT EXISTS idx_casos_data ON casos (data_publicacao);
CREATE INDEX IF NOT EXISTS idx_casos_tipo ON casos (tipo);
CREATE INDEX IF NOT EXISTS idx_casos_uf ON casos (uf);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_casos(registros: Iterable[dict]) -> int:
    """Insere/atualiza registros. Retorna quantos foram efetivamente gravados."""
    registros = list(registros)
    if not registros:
        return 0
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO casos (id, numero_processo, tribunal, orgao, uf, tipo, empresa,
                                cnpj, setor, data_publicacao, data_coleta, fonte, link,
                                texto, raw_json)
            VALUES (:id, :numero_processo, :tribunal, :orgao, :uf, :tipo, :empresa,
                    :cnpj, :setor, :data_publicacao, :data_coleta, :fonte, :link,
                    :texto, :raw_json)
            ON CONFLICT(id) DO UPDATE SET
                numero_processo=excluded.numero_processo,
                tribunal=excluded.tribunal,
                orgao=excluded.orgao,
                uf=excluded.uf,
                tipo=excluded.tipo,
                empresa=excluded.empresa,
                cnpj=excluded.cnpj,
                setor=excluded.setor,
                data_publicacao=excluded.data_publicacao,
                fonte=excluded.fonte,
                link=excluded.link,
                texto=excluded.texto,
                raw_json=excluded.raw_json
            """,
            [
                {**r, "raw_json": json.dumps(r.get("raw_json"), ensure_ascii=False) if not isinstance(r.get("raw_json"), str) else r.get("raw_json")}
                for r in registros
            ],
        )
        return cur.rowcount


def fetch_all() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM casos ORDER BY data_publicacao DESC").fetchall()
        return [dict(r) for r in rows]


def count_casos() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM casos").fetchone()[0]


def wipe_db() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM casos")


def last_data_coleta() -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(data_coleta) FROM casos").fetchone()
        return row[0] if row else None
