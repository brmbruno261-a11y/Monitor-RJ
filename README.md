# Monitor RJ — Recuperação Judicial, Extrajudicial e Falências

Dashboard em Python/Streamlit para acompanhar casos de **Recuperação Judicial**,
**Recuperação Extrajudicial** e **Falência** no Brasil, no estilo de painéis de
indicadores como o da BizDoc/Serasa: cards de KPI no topo, evolução mensal,
distribuição por UF e por setor, e uma tabela filtrável de casos.

## Estrutura

```
monitor_rj/
├── app.py               # dashboard Streamlit (rode este arquivo)
├── db.py                 # camada SQLite (armazenamento local, monitor_rj.db)
├── scraper.py             # coleta pública no DJEN (comunica.pje.jus.br)
├── classify.py            # heurísticas: tipo de caso, setor, UF, CNPJ, nome da empresa
├── seed_sample_data.py     # gera dados sintéticos para demonstração
└── requirements.txt
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

Abra o link que o Streamlit mostrar no terminal (geralmente http://localhost:8501).

Dentro do app, na barra lateral, você pode:
- **🧪 Carregar dados de exemplo** — popula o banco com 420 casos sintéticos plausíveis, para ver o dashboard funcionando de imediato.
- **🔄 Atualizar com dados reais (DJEN)** — busca publicações reais no Diário de Justiça Eletrônico Nacional pelos termos configurados.
- **🗑️ Limpar banco de dados** — zera tudo.

## Fonte de dados real: DJEN (comunica.pje.jus.br)

O scraper usa a API pública que alimenta o site
[comunica.pje.jus.br](https://comunica.pje.jus.br), o portal oficial de
comunicações processuais do CNJ/PJe. É pública e não exige login — mas **não é
uma API comercial documentada e estável**, então:

1. **Ela não foi testada ao vivo neste ambiente** (o sandbox usado para gerar
   este projeto não tem saída de rede para `comunicaapi.pje.jus.br`). Rode
   `python -c "import scraper; scraper.debug_ping()"` na sua máquina, com
   internet, antes de confiar no scraper em produção.
2. Se os nomes dos parâmetros mudarem, ajuste apenas as constantes no topo de
   `scraper.py` (`BASE_URL`, os parâmetros dentro de `fetch_page`) — o resto do
   pipeline não precisa mudar, porque cada registro guarda o JSON bruto
   original (`raw_json`) para reprocessamento futuro.
3. Seja educado com o servidor público: o scraper já inclui um intervalo
   (`REQUEST_DELAY`) entre requisições — não reduza agressivamente.

### Alternativa/complemento: API Pública do DataJud

Para dados mais estruturados por processo (classe, assunto, movimentações),
existe também a **API Pública do DataJud** do CNJ
(`https://api-publica.datajud.cnj.jus.br`), que exige uma API Key pública
(gerada e divulgada pelo próprio CNJ, veja
https://www.cnj.jus.br/sistemas/datajud/api-publica/). Ela é mais estável e
documentada, mas exige montar queries Elasticsearch por tribunal e filtrar por
códigos de assunto (tabela processual unificada do CNJ). Não foi incluída
neste projeto pronta para uso porque a chave pública muda periodicamente —
mas o desenho do banco (`db.py`, campo `raw_json`) já comporta adicionar esse
segundo scraper no futuro sem quebrar o dashboard.

## Limitações importantes

- **Classificação de tipo, setor e UF é heurística** (palavras-chave e sigla do
  tribunal), feita a partir de texto livre de publicações judiciais. Vai errar
  em casos ambíguos. Trate como indicativo, não como fonte definitiva —
  especialmente antes de qualquer decisão de crédito/negócio.
- **Extração de nome de empresa e CNPJ é por regex** sobre o texto da
  publicação; nem toda publicação traz essas informações de forma limpa.
- Cobertura do DJEN varia por tribunal e por quando cada tribunal aderiu à
  plataforma nacional de comunicações — pode haver lacunas.

## Próximos passos sugeridos

- Agendar a coleta (ex: `cron` chamando um script que roda `scraper.collect()`
  e grava no banco) para manter o monitor sempre atualizado.
- Adicionar deduplicação por CNPJ ao longo do tempo, pra distinguir "novo
  processo" de "nova publicação do mesmo processo".
- Trocar o SQLite por Postgres se o volume crescer muito ou se for rodar em
  múltiplos usuários simultâneos.
