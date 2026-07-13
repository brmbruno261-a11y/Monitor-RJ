"""
seed_sample_data.py — gera dados sintéticos plausíveis para o Monitor RJ
poder ser demonstrado/usado imediatamente, antes de rodar o scraper real
contra o DJEN.

Rode: python seed_sample_data.py
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta, timezone

import db

random.seed(42)

UFS = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "GO", "PE", "CE", "MT", "MS", "ES", "PA"]
SETORES = [
    "Agropecuária", "Comércio/Varejo", "Indústria", "Serviços", "Construção",
    "Transporte/Logística", "Energia", "Saúde", "Tecnologia", "Imobiliário",
]
TIPOS_PESOS = [("Recuperação Judicial", 0.72), ("Falência", 0.22), ("Recuperação Extrajudicial", 0.06)]

NOME_BASE = [
    "Agro", "Brasil", "Nova", "Sul", "Norte", "Vale do", "Rio", "Central", "Trans", "Log",
    "Mineração", "Comercial", "Industrial", "Alfa", "Beta", "Prime", "Master", "União",
]
NOME_SUFIXO = ["Ltda", "S.A.", "Comércio e Indústria Ltda", "Participações S.A.", "Transportes Ltda"]

TRIBUNAIS_POR_UF = {uf: f"TJ{uf}" for uf in UFS}


def _rand_cnpj() -> str:
    d = [random.randint(0, 9) for _ in range(12)]
    return f"{d[0]}{d[1]}.{d[2]}{d[3]}{d[4]}.{d[5]}{d[6]}{d[7]}/{d[8]}{d[9]}{d[10]}{d[11]}-{random.randint(10,99)}"


def _rand_empresa() -> str:
    return f"{random.choice(NOME_BASE)} {random.choice(NOME_BASE)} {random.choice(NOME_SUFIXO)}"


def _rand_tipo() -> str:
    r = random.random()
    acc = 0.0
    for tipo, peso in TIPOS_PESOS:
        acc += peso
        if r <= acc:
            return tipo
    return TIPOS_PESOS[-1][0]


def gerar(n: int = 420, dias: int = 730) -> list[dict]:
    registros = []
    hoje = date.today()
    for i in range(n):
        dt = hoje - timedelta(days=random.randint(0, dias))
        uf = random.choice(UFS)
        empresa = _rand_empresa()
        tipo = _rand_tipo()
        setor = random.choice(SETORES)
        cnpj = _rand_cnpj()
        rid = hashlib.sha1(f"exemplo-{i}-{empresa}-{dt}".encode()).hexdigest()
        registros.append(
            {
                "id": rid,
                "numero_processo": f"{random.randint(1000000,9999999):07d}-{random.randint(10,99)}.{dt.year}.8.{random.randint(10,26):02d}.{random.randint(1,9999):04d}",
                "tribunal": TRIBUNAIS_POR_UF[uf],
                "orgao": f"{random.randint(1,9)}ª Vara Cível/Empresarial",
                "uf": uf,
                "tipo": tipo,
                "empresa": empresa,
                "cnpj": cnpj,
                "setor": setor,
                "data_publicacao": dt.isoformat(),
                "data_coleta": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "fonte": "exemplo",
                "link": "",
                "texto": f"Processo de {tipo.lower()} envolvendo {empresa} (CNPJ {cnpj}), do setor de {setor.lower()}, "
                         f"tramitando no {TRIBUNAIS_POR_UF[uf]}. [Registro de demonstração]",
                "raw_json": None,
            }
        )
    return registros


if __name__ == "__main__":
    db.init_db()
    registros = gerar()
    db.upsert_casos(registros)
    print(f"{len(registros)} registros de exemplo inseridos em {db.DB_PATH}")
