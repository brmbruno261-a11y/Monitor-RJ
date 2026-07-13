"""
cnae.py — mapeia a "divisão" (2 primeiros dígitos) do código CNAE para um
setor macro legível. Baseado na estrutura oficial da Classificação Nacional
de Atividades Econômicas (CNAE 2.3, mantida pelo IBGE/CONCLA).

Isso é usado quando temos o CNPJ da empresa e conseguimos o CNAE real via
RFB (ver sources/rfb_cnpj.py) — muito mais confiável do que adivinhar o
setor a partir de palavras-chave no texto da publicação (ver classify.py).
"""

from __future__ import annotations

# divisão (2 dígitos) -> setor macro
DIVISAO_SETOR = {}


def _faixa(inicio: int, fim: int, setor: str) -> None:
    for i in range(inicio, fim + 1):
        DIVISAO_SETOR[f"{i:02d}"] = setor


_faixa(1, 3, "Agropecuária")
_faixa(5, 9, "Extrativa/Mineração")
_faixa(10, 33, "Indústria")
_faixa(35, 35, "Energia")
_faixa(36, 39, "Água/Saneamento/Resíduos")
_faixa(41, 43, "Construção")
_faixa(45, 47, "Comércio/Varejo")
_faixa(49, 53, "Transporte/Logística")
_faixa(55, 56, "Alimentação/Hospedagem")
_faixa(58, 63, "Tecnologia/Informação")
_faixa(64, 66, "Financeiro")
_faixa(68, 68, "Imobiliário")
_faixa(69, 75, "Serviços Profissionais")
_faixa(77, 82, "Serviços Administrativos")
_faixa(84, 84, "Administração Pública")
_faixa(85, 85, "Educação")
_faixa(86, 88, "Saúde")
_faixa(90, 93, "Cultura/Esporte/Lazer")
_faixa(94, 96, "Outros Serviços")
_faixa(97, 97, "Serviços Domésticos")
_faixa(99, 99, "Organismos Internacionais")


def setor_por_cnae(codigo_cnae: str | None) -> str:
    """Recebe um código CNAE (com ou sem formatação, ex: '0111-3/01' ou
    '01113 01') e devolve o setor macro correspondente."""
    if not codigo_cnae:
        return "Não classificado"
    digitos = "".join(c for c in str(codigo_cnae) if c.isdigit())
    if len(digitos) < 2:
        return "Não classificado"
    divisao = digitos[:2]
    return DIVISAO_SETOR.get(divisao, "Não classificado")
