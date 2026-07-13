# Monitor RJ — Recuperação Judicial, Extrajudicial e Falências

Dashboard em Python/Streamlit para acompanhar casos de **Recuperação Judicial**,
**Recuperação Extrajudicial** e **Falência** no Brasil, combinando fontes
oficiais de **estoque** (quem são as empresas) e **fluxo** (o que está
acontecendo com elas), no estilo de painéis de indicadores como o da
BizDoc/Serasa.

## Arquitetura de dados

| Camada             | Fonte                                   | O que traz                                                        |
|---------------------|------------------------------------------|---------------------------------------------------------------------|
| Estoque             | RFB Dados Abertos de CNPJ (via BrasilAPI) | Razão social oficial, CNAE real (setor), UF/município, situação cadastral |
| Fluxo — Judiciário   | DJEN (comunica.pje.jus.br)                | Publicações judiciais (texto livre) de RJ/extrajudicial/falência   |
| Fluxo — Judiciário   | DataJud (API Pública do CNJ)               | Metadados estruturados do processo (classe, assuntos, tribunal)    |
| Fluxo — Mercado      | CVM (dados.cvm.gov.br)                    | Fatos Relevantes/comunicados de RJ/falência de companhias abertas  |
| Malha geográfica     | IBGE (servicodados.ibge.gov.br)           | GeoJSON dos estados, para o mapa coroplético por UF                |

O fluxo (DJEN/DataJud/CVM) alimenta a tabela `casos`. O estoque (RFB)
alimenta a tabela `empresas_cnpj`, usada para **enriquecer** cada caso pelo
CNPJ: quando um caso tem CNPJ enriquecido, o setor (CNAE real) e a UF
(endereço real) mostrados no dashboard passam a vir da RFB em vez da
heurística de texto — mais confiável.

## Estrutura

```
monitor_rj/
├── app.py                  # dashboard Streamlit (rode este arquivo)
├── db.py                    # camada SQLite (tabelas `casos` e `empresas_cnpj`)
├── classify.py               # heurísticas de texto: tipo, setor, UF, CNPJ, empresa
├── cnae.py                   # mapeia código CNAE -> setor macro (usado no enriquecimento RFB)
├── seed_sample_data.py        # gera dados sintéticos para demonstração
├── fonte_djen.py              # coleta no DJEN (comunica.pje.jus.br)
├── fonte_datajud.py            # coleta na API Pública do DataJud (CNJ)
├── fonte_cvm.py                # coleta nos dados abertos da CVM (companhias abertas)
├── fonte_rfb_cnpj.py            # enriquece CNPJs via BrasilAPI (espelho da RFB)
├── fonte_ibge_geo.py            # malha geográfica (GeoJSON) do IBGE
└── requirements.txt

Todos os arquivos ficam soltos na raiz (sem subpastas) de propósito — assim
dá pra atualizar qualquer um deles pelo GitHub (Add file → Upload files)
sem precisar recriar estrutura de pastas.
```

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# opcional: popular com dados de exemplo pra já ver o dashboard funcionando
python seed_sample_data.py

streamlit run app.py
```

Na barra lateral você encontra uma seção por fonte:

- **📰 DJEN** — busca por palavra-chave nas publicações de todos os tribunais.
- **⚖️ DataJud** — busca processos estruturados por tribunal. Exige uma API
  Key (veja abaixo).
- **🏦 CVM** — baixa e filtra os documentos de companhias abertas por ano.
- **🏢 RFB — enriquecer CNPJs** — consulta cada CNPJ já coletado na base da
  Receita (via BrasilAPI) e grava no cache `empresas_cnpj`.

## Fontes reais: detalhes e limitações

### DJEN (comunica.pje.jus.br)
API pública (sem login) que alimenta o portal oficial de comunicações
processuais do CNJ/PJe. **Não é uma API comercial documentada e estável** —
se os nomes dos parâmetros mudarem, ajuste as constantes no topo de
`fonte_djen.py`. Cada registro guarda o JSON bruto (`raw_json`) para
reprocessamento futuro sem precisar coletar de novo.

### DataJud (API Pública do CNJ)
Traz metadados estruturados do processo via Elasticsearch, **um índice por
tribunal** (não existe endpoint "todos os tribunais"). Exige uma API Key —
veja como obter (chave pública compartilhada ou cadastro individual
gratuito) em https://datajud-wiki.cnj.jus.br/api-publica/acesso/. Configure
via variável de ambiente `DATAJUD_API_KEY` ou cole direto no campo da
barra lateral. A busca por "recuperação judicial"/"falência" usa `match`
textual nos campos `assuntos.nome` e `classe.nome` — não há garantia de que
todo tribunal preenche esses campos da mesma forma.

### CVM (Portal de Dados Abertos)
Conjunto **"Cias Abertas: Documentos: Periódicos e Eventuais (IPE)"**,
baixado por ano (`ipe_cia_aberta_{ANO}.zip`). Cobre **apenas companhias
abertas** (capital na bolsa) — é um complemento ao Judiciário, pegando o
sinal direto do regulador do mercado de capitais, o que costuma ser mais
rápido do que aguardar a publicação judicial correspondente.

### RFB Dados Abertos de CNPJ (via BrasilAPI)
A base completa da Receita é distribuída só em arquivos enormes (~20GB
compactados, ~60 milhões de CNPJs) — inviável de baixar dentro do próprio
app. Como só precisamos enriquecer os CNPJs que já apareceram em casos
coletados (algumas centenas, não milhões), o app consulta um a um via
**BrasilAPI** (`brasilapi.com.br/api/cnpj/v1/{cnpj}`), projeto open-source
que espelha os dados oficiais da Receita — e grava tudo em cache
(`empresas_cnpj`) para nunca reconsultar o mesmo CNPJ duas vezes.

Se no futuro você precisar da base completa (ex: comparar "% do universo de
empresas de um setor que entrou em RJ"), baixe os arquivos oficiais da RFB
e carregue localmente/offline — não é uma operação adequada para rodar
dentro do Streamlit Cloud.

### IBGE — malha geográfica
`servicodados.ibge.gov.br/api/v3/malhas/brasil` traz o GeoJSON de todos os
estados de uma vez, usado no mapa coroplético da aba "🗺️ Mapa por UF". Se a
chamada falhar (rede instável, mudança de API), o dashboard cai
automaticamente para um gráfico de barras por UF.

## ⚠️ Sobre os testes deste projeto

O ambiente usado para gerar este projeto **não tem saída de rede** para
nenhum dos domínios acima (comunica.pje.jus.br, api-publica.datajud.cnj.jus.br,
dados.cvm.gov.br, brasilapi.com.br, servicodados.ibge.gov.br). Por isso:

- A **estrutura de cada fonte foi confirmada via busca/leitura de
  documentação e páginas reais** (não é suposição) — em especial, os nomes
  de coluna da CVM foram confirmados no dicionário de dados oficial.
- A **lógica de parsing, classificação e o join estoque×fluxo foram
  testados com dados sintéticos** que reproduzem a estrutura real de cada
  fonte (veja os testes que rodei durante o desenvolvimento).
- O que **não pôde ser testado ao vivo** é a chamada de rede em si (URL
  responde? formato mudou desde a última verificação?). Rode cada fonte uma
  vez localmente e me avise se algo vier vazio ou der erro — ajusto o
  parsing rapidamente porque cada registro guarda o payload bruto.

## Limitações importantes

- **Sem enriquecimento RFB**, setor e UF são heurísticos (palavras-chave e
  sigla do tribunal) — trate como indicativo, não como fonte definitiva.
- **DataJud** pode não preencher `assuntos`/`classe` de forma padronizada em
  todos os tribunais — resultado vazio pode ser "não achou" ou "esse
  tribunal não indexa esse campo".
- **CVM** cobre só companhias abertas — não é fonte para empresas de capital
  fechado.
- **BrasilAPI** é gratuita mas sem contrato de rate limit documentado — o
  enriquecimento é feito um CNPJ por vez, com intervalo, e sempre em cache.

## Próximos passos sugeridos

- Agendar a coleta (`cron` chamando as funções `collect()` de cada fonte)
  para manter o monitor sempre atualizado sem depender de clique manual.
- Deduplicar por CNPJ ao longo do tempo, pra distinguir "novo processo" de
  "nova publicação do mesmo processo".
- Trocar o SQLite por Postgres se for rodar no Streamlit Community Cloud
  com uso contínuo (lá o disco não é persistente entre reinícios).
