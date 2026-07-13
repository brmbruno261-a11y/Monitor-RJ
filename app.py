"""
app.py — Monitor RJ: Recuperação Judicial, Extrajudicial e Falências

Fontes:
  - Fluxo:   DJEN (comunica.pje.jus.br), DataJud (CNJ), CVM (companhias abertas)
  - Estoque: RFB Dados Abertos de CNPJ (via BrasilAPI), para enriquecer cada
             caso com setor real (CNAE), UF/município e situação cadastral
  - Malha geográfica: IBGE (mapa coroplético por UF)

Rode com:  streamlit run app.py
"""

from __future__ import annotations

import calendar
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import db
import fonte_cvm as cvm
import fonte_datajud as datajud
import fonte_djen as djen
import fonte_ibge_geo as ibge_geo
import fonte_rfb_cnpj as rfb_cnpj
import seed_sample_data

st.set_page_config(
    page_title="Monitor RJ — Recuperações e Falências",
    page_icon="📊",
    layout="wide",
)

COR_TIPO = {
    "Recuperação Judicial": "#2563eb",
    "Falência": "#dc2626",
    "Recuperação Extrajudicial": "#16a34a",
}

db.init_db()


# ------------------------------------------------------------------ dados

@st.cache_data(ttl=60)
def carregar_dados() -> pd.DataFrame:
    registros = db.fetch_all()
    df = pd.DataFrame(registros)
    if df.empty:
        return df

    # junta com o cache de enriquecimento RFB (estoque), quando disponível:
    # setor/UF reais (por CNAE e endereço) têm prioridade sobre a heurística de texto
    empresas = db.fetch_empresas()
    if empresas:

        def _enriquecido(row, campo_df, campo_empresa):
            cnpj_d = "".join(c for c in str(row.get("cnpj") or "") if c.isdigit())
            emp = empresas.get(cnpj_d)
            if emp and emp.get(campo_empresa):
                return emp[campo_empresa]
            return row.get(campo_df)

        df["setor"] = df.apply(lambda r: _enriquecido(r, "setor", "setor"), axis=1)
        df["uf"] = df.apply(lambda r: _enriquecido(r, "uf", "uf"), axis=1)
        df["razao_social_rfb"] = df.apply(lambda r: _enriquecido(r, "empresa", "razao_social"), axis=1)
        df["porte"] = df.apply(lambda r: _enriquecido(r, "porte", "porte"), axis=1)
        df["situacao_cadastral"] = df["cnpj"].apply(
            lambda c: (empresas.get("".join(ch for ch in str(c or "") if ch.isdigit())) or {}).get("situacao_cadastral")
        )
    else:
        df["porte"] = None

    df["data_publicacao"] = pd.to_datetime(df["data_publicacao"], errors="coerce")
    df = df.dropna(subset=["data_publicacao"])
    df["ano_mes"] = df["data_publicacao"].dt.to_period("M").dt.to_timestamp()
    return df


@st.cache_data(ttl=6 * 60 * 60)
def carregar_malha():
    try:
        return ibge_geo.malha_estados_brasil()
    except Exception as e:
        return {"error": str(e)}


def formatar_delta(atual: int, anterior: int) -> str:
    if anterior == 0:
        return ""
    pct = (atual - anterior) / anterior * 100
    sinal = "+" if pct >= 0 else ""
    return f"{sinal}{pct:.1f}% vs período anterior"


def opcoes_periodo(df: pd.DataFrame) -> list[str]:
    datas = df["data_publicacao"].dropna()
    if datas.empty:
        return ["Tudo"]
    trimestres = sorted({(d.year, (d.month - 1) // 3 + 1) for d in datas}, reverse=True)
    labels = [f"{q}ºT/{str(y)[2:]}" for y, q in trimestres]
    return ["Tudo"] + labels


def periodo_para_datas(label: str) -> tuple[date, date] | None:
    if label == "Tudo":
        return None
    q_str, y_str = label.replace("º", "").split("T/")
    q, y = int(q_str), 2000 + int(y_str)
    mes_ini = (q - 1) * 3 + 1
    mes_fim = mes_ini + 2
    ini = date(y, mes_ini, 1)
    ultimo_dia = calendar.monthrange(y, mes_fim)[1]
    fim = date(y, mes_fim, ultimo_dia)
    return ini, fim


# ------------------------------------------------------------------ sidebar

with st.sidebar:
    st.title("📊 Monitor RJ")
    st.caption("Recuperação Judicial · Extrajudicial · Falências")

    st.subheader("Dados")
    st.metric("Casos no banco", db.count_casos())
    st.caption(f"Última coleta: {db.last_data_coleta() or '—'}")

    if st.button("🧪 Carregar dados de exemplo", use_container_width=True,
                  help="Popula o banco com dados sintéticos para você ver o dashboard funcionando antes de coletar dados reais."):
        with st.spinner("Gerando dados de exemplo..."):
            db.upsert_casos(seed_sample_data.gerar())
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("🔄 Coletar dados reais")

    with st.expander("📰 DJEN — publicações judiciais"):
        st.caption("comunica.pje.jus.br — busca por palavra-chave nas publicações de todos os tribunais.")
        termos_djen = st.text_area(
            "Termos", value="recuperação judicial\nrecuperação extrajudicial\nfalência",
            height=80, key="termos_djen",
        )
        dias_djen = st.slider("Últimos N dias", 1, 180, 30, key="dias_djen")
        if st.button("Buscar no DJEN", use_container_width=True, key="btn_djen"):
            termos = [t.strip() for t in termos_djen.splitlines() if t.strip()]
            with st.spinner("Consultando o DJEN..."):
                try:
                    registros = djen.collect(termos=termos, dias_atras=dias_djen)
                    if registros:
                        db.upsert_casos(registros)
                        st.success(f"{len(registros)} publicações coletadas.")
                    else:
                        st.warning("Nenhum registro retornado.")
                except Exception as e:
                    st.error(f"Falha: {e}")
            st.cache_data.clear()
            st.rerun()

    with st.expander("⚖️ DataJud — processos estruturados (CNJ)"):
        st.caption(
            "Requer API Key do DataJud. Veja como obter em "
            "https://datajud-wiki.cnj.jus.br/api-publica/acesso/"
        )
        api_key_input = st.text_input(
            "DATAJUD_API_KEY", value=os.environ.get("DATAJUD_API_KEY", ""), type="password", key="datajud_key"
        )
        tribunais_sel = st.multiselect(
            "Tribunais", datajud.TRIBUNAIS, default=datajud.TRIBUNAIS[:5], key="datajud_tribunais"
        )
        if st.button("Buscar no DataJud", use_container_width=True, key="btn_datajud"):
            with st.spinner("Consultando o DataJud (pode demorar, um tribunal por vez)..."):
                try:
                    registros = datajud.collect(tribunais=tribunais_sel, api_key=api_key_input or None)
                    if registros:
                        db.upsert_casos(registros)
                        st.success(f"{len(registros)} processos coletados.")
                    else:
                        st.warning("Nenhum registro retornado.")
                except Exception as e:
                    st.error(f"Falha: {e}")
            st.cache_data.clear()
            st.rerun()

    with st.expander("🏦 CVM — companhias abertas"):
        st.caption("Fatos Relevantes e comunicados de RJ/falência de empresas com capital aberto.")
        anos_sel = st.multiselect(
            "Anos", list(range(2018, date.today().year + 1)),
            default=[date.today().year, date.today().year - 1], key="cvm_anos",
        )
        if st.button("Buscar na CVM", use_container_width=True, key="btn_cvm"):
            with st.spinner("Baixando e filtrando documentos da CVM..."):
                try:
                    registros = cvm.collect(anos=anos_sel)
                    if registros:
                        db.upsert_casos(registros)
                        st.success(f"{len(registros)} documentos coletados.")
                    else:
                        st.warning("Nenhum registro retornado.")
                except Exception as e:
                    st.error(f"Falha: {e}")
            st.cache_data.clear()
            st.rerun()

    with st.expander("🏢 RFB — enriquecer CNPJs (estoque)"):
        st.caption(
            "Consulta cada CNPJ encontrado nos casos na base da Receita (via BrasilAPI), "
            "trazendo setor real (CNAE), UF/município e situação cadastral."
        )
        pendentes = db.cnpjs_pendentes_enriquecimento(limite=500)
        st.caption(f"{len(pendentes)} CNPJs ainda não enriquecidos (mostrando até 500 por vez).")
        qtd = st.slider("Quantos enriquecer agora", 1, max(len(pendentes), 1), min(20, max(len(pendentes), 1)), key="qtd_enriq")
        if st.button("Enriquecer agora", use_container_width=True, key="btn_rfb", disabled=not pendentes):
            with st.spinner("Consultando a Receita Federal via BrasilAPI..."):
                try:
                    resultados = rfb_cnpj.enriquecer_lote(pendentes[:qtd])
                    db.upsert_empresas(resultados)
                    ok = sum(1 for r in resultados if not r.get("erro"))
                    st.success(f"{ok}/{len(resultados)} CNPJs enriquecidos com sucesso.")
                except Exception as e:
                    st.error(f"Falha: {e}")
            st.cache_data.clear()
            st.rerun()

    if st.button("🗑️ Limpar banco de dados", use_container_width=True):
        db.wipe_db()
        st.cache_data.clear()
        st.rerun()

df_all = carregar_dados()

if df_all.empty:
    st.title("📊 Monitor RJ — Recuperação Judicial, Extrajudicial e Falências")
    st.info(
        "Nenhum dado no banco ainda. Use **🧪 Carregar dados de exemplo** na barra lateral "
        "para ver o dashboard funcionando, ou as seções **🔄 Coletar dados reais** para "
        "buscar em DJEN, DataJud ou CVM."
    )
    st.stop()

# ------------------------------------------------------------------ barra de filtros (topo)

DEFAULTS_FILTRO = {
    "f_periodo": "Tudo", "f_uf": "Brasil", "f_porte": "Todos",
    "f_fonte": "Todas", "f_tipo": "Todos", "f_busca": "",
}
for k, v in DEFAULTS_FILTRO.items():
    st.session_state.setdefault(k, v)


def _limpar_filtros():
    for k, v in DEFAULTS_FILTRO.items():
        st.session_state[k] = v


with st.container(border=True):
    fc1, fc2, fc3, fc4, fc5, fc6 = st.columns([1.1, 1, 1, 1, 1, 0.8])

    with fc1:
        opcoes_per = opcoes_periodo(df_all)
        if st.session_state["f_periodo"] not in opcoes_per:
            st.session_state["f_periodo"] = "Tudo"
        st.selectbox("Período", opcoes_per, key="f_periodo")
    with fc2:
        opcoes_uf = ["Brasil"] + sorted(df_all["uf"].dropna().unique().tolist())
        st.selectbox("UF", opcoes_uf, key="f_uf")
    with fc3:
        opcoes_porte = ["Todos"] + sorted(df_all["porte"].dropna().unique().tolist()) if "porte" in df_all.columns else ["Todos"]
        st.selectbox("Porte", opcoes_porte, key="f_porte")
    with fc4:
        opcoes_fonte = ["Todas"] + sorted(df_all["fonte"].dropna().unique().tolist())
        st.selectbox("Fonte (casos)", opcoes_fonte, key="f_fonte")
    with fc5:
        opcoes_tipo = ["Todos"] + sorted(df_all["tipo"].dropna().unique().tolist())
        st.selectbox("Tipo (casos)", opcoes_tipo, key="f_tipo")
    with fc6:
        st.markdown("<div style='height:1.85em'></div>", unsafe_allow_html=True)
        st.button("↺ Limpar", use_container_width=True, on_click=_limpar_filtros)

    st.text_input("🔎 Buscar empresa ou texto", key="f_busca", placeholder="ex: Agropecuária Brasil Ltda")

# aplica os filtros
df = df_all.copy()
periodo_datas = periodo_para_datas(st.session_state["f_periodo"])
if periodo_datas:
    ini, fim = periodo_datas
    df = df[(df["data_publicacao"].dt.date >= ini) & (df["data_publicacao"].dt.date <= fim)]
if st.session_state["f_uf"] != "Brasil":
    df = df[df["uf"] == st.session_state["f_uf"]]
if st.session_state["f_porte"] != "Todos":
    df = df[df["porte"] == st.session_state["f_porte"]]
if st.session_state["f_fonte"] != "Todas":
    df = df[df["fonte"] == st.session_state["f_fonte"]]
if st.session_state["f_tipo"] != "Todos":
    df = df[df["tipo"] == st.session_state["f_tipo"]]
if st.session_state["f_busca"]:
    b = st.session_state["f_busca"].lower()
    df = df[
        df["empresa"].fillna("").str.lower().str.contains(b)
        | df["texto"].fillna("").str.lower().str.contains(b)
    ]

# ------------------------------------------------------------------ cabeçalho + KPIs

st.title("📊 Monitor RJ — Recuperação Judicial, Extrajudicial e Falências")
st.caption(
    f"{len(df)} casos no filtro atual · fontes: {', '.join(sorted(df['fonte'].dropna().unique())) or '—'}"
)

if periodo_datas:
    ini, fim = periodo_datas
    dias = (fim - ini).days + 1
    ini_ant, fim_ant = ini - timedelta(days=dias), ini - timedelta(days=1)
    df_ant = df_all[(df_all["data_publicacao"].dt.date >= ini_ant) & (df_all["data_publicacao"].dt.date <= fim_ant)]
else:
    df_ant = df_all.iloc[0:0]

col1, col2, col3, col4 = st.columns(4)
total = len(df)
rj = int((df["tipo"] == "Recuperação Judicial").sum())
rex = int((df["tipo"] == "Recuperação Extrajudicial").sum())
fal = int((df["tipo"] == "Falência").sum())

total_ant = len(df_ant)
rj_ant = int((df_ant["tipo"] == "Recuperação Judicial").sum())
rex_ant = int((df_ant["tipo"] == "Recuperação Extrajudicial").sum())
fal_ant = int((df_ant["tipo"] == "Falência").sum())

col1.metric("Total de casos", total, formatar_delta(total, total_ant))
col2.metric("Recuperação Judicial", rj, formatar_delta(rj, rj_ant))
col3.metric("Recuperação Extrajudicial", rex, formatar_delta(rex, rex_ant))
col4.metric("Falências", fal, formatar_delta(fal, fal_ant))

st.divider()

# ------------------------------------------------------------------ evolução no tempo

st.subheader("Evolução mensal")
serie = df.groupby(["ano_mes", "tipo"]).size().reset_index(name="casos")
if not serie.empty:
    fig = px.bar(
        serie, x="ano_mes", y="casos", color="tipo",
        color_discrete_map=COR_TIPO,
        labels={"ano_mes": "Mês", "casos": "Casos", "tipo": "Tipo"},
    )
    fig.update_layout(barmode="stack", legend_title_text="", height=380)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("Sem dados suficientes para o gráfico de evolução.")

# ------------------------------------------------------------------ mapa + setor

tab_mapa, tab_setor = st.tabs(["🗺️ Mapa por UF", "🏭 Por setor"])

with tab_mapa:
    por_uf = df.groupby("uf").size().reset_index(name="casos")
    malha = carregar_malha()
    if "error" in malha:
        st.warning(f"Não foi possível carregar a malha do IBGE agora ({malha['error']}). Mostrando barras por UF.")
        if not por_uf.empty:
            fig_uf = px.bar(por_uf.sort_values("casos", ascending=False), x="uf", y="casos")
            st.plotly_chart(fig_uf, use_container_width=True)
    elif por_uf.empty:
        st.caption("Sem dados de UF classificados no filtro atual.")
    else:
        # a malha do IBGE traz `codarea` (código IBGE da UF); mapeamos para sigla
        for feat in malha.get("features", []):
            codarea = feat.get("properties", {}).get("codarea")
            feat["properties"]["sigla"] = ibge_geo.CODIGO_UF.get(str(codarea))

        fig_mapa = px.choropleth(
            por_uf, geojson=malha, locations="uf", featureidkey="properties.sigla",
            color="casos", color_continuous_scale="Reds",
            labels={"casos": "Casos"},
        )
        fig_mapa.update_geos(fitbounds="locations", visible=False)
        fig_mapa.update_layout(height=480, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_mapa, use_container_width=True)
    st.caption(
        "⚠️ UF é a informação real de endereço da RFB quando o CNPJ foi enriquecido "
        "(veja '🏢 RFB — enriquecer CNPJs' na barra lateral); caso contrário, é estimada "
        "pela sigla do tribunal."
    )

with tab_setor:
    por_setor = df.groupby("setor").size().reset_index(name="casos").sort_values("casos", ascending=False)
    if not por_setor.empty:
        fig_setor = px.pie(por_setor, names="setor", values="casos", hole=0.45)
        fig_setor.update_layout(height=420)
        st.plotly_chart(fig_setor, use_container_width=True)
    else:
        st.caption("Sem dados de setor classificados no filtro atual.")
    st.caption(
        "⚠️ Setor é o CNAE real da RFB quando o CNPJ foi enriquecido; caso contrário, é "
        "estimado por palavras-chave no texto do caso — trate como indicativo."
    )

st.divider()

# ------------------------------------------------------------------ tabela detalhada

st.subheader("Casos")
cols_disponiveis = ["data_publicacao", "tipo", "empresa", "razao_social_rfb", "cnpj", "situacao_cadastral",
                     "tribunal", "uf", "setor", "fonte", "numero_processo"]
cols_tabela = [c for c in cols_disponiveis if c in df.columns]
df_tabela = df[cols_tabela].sort_values("data_publicacao", ascending=False).rename(columns={
    "data_publicacao": "Data", "tipo": "Tipo", "empresa": "Empresa (extraído)",
    "razao_social_rfb": "Razão Social (RFB)", "cnpj": "CNPJ", "situacao_cadastral": "Situação",
    "tribunal": "Tribunal", "uf": "UF", "setor": "Setor", "fonte": "Fonte",
    "numero_processo": "Nº Processo",
})
st.dataframe(df_tabela, use_container_width=True, hide_index=True, height=420)

csv_bytes = df_tabela.to_csv(index=False).encode("utf-8-sig")
st.download_button("⬇️ Baixar CSV do filtro atual", csv_bytes, file_name="monitor_rj_casos.csv", mime="text/csv")

with st.expander("Ver texto completo de um caso"):
    if not df.empty:
        opcoes = (df["empresa"].fillna("(sem nome extraído)") + " — " + df["data_publicacao"].dt.strftime("%d/%m/%Y")).tolist()
        idx = st.selectbox("Selecione", range(len(opcoes)), format_func=lambda i: opcoes[i])
        linha = df.iloc[idx]
        st.write(f"**Tipo:** {linha['tipo']} · **Tribunal:** {linha['tribunal']} · **Fonte:** {linha['fonte']}")
        st.write(linha["texto"])
        if linha.get("link"):
            st.markdown(f"[Abrir fonte original]({linha['link']})")
