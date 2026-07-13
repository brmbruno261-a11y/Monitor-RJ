"""
app.py — Monitor RJ: Recuperação Judicial, Extrajudicial e Falências

Rode com:  streamlit run app.py
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import db
import scraper
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
    df["data_publicacao"] = pd.to_datetime(df["data_publicacao"], errors="coerce")
    df = df.dropna(subset=["data_publicacao"])
    df["ano_mes"] = df["data_publicacao"].dt.to_period("M").dt.to_timestamp()
    return df


def formatar_delta(atual: int, anterior: int) -> str:
    if anterior == 0:
        return ""
    pct = (atual - anterior) / anterior * 100
    sinal = "+" if pct >= 0 else ""
    return f"{sinal}{pct:.1f}% vs período anterior"


# ------------------------------------------------------------------ sidebar

with st.sidebar:
    st.title("📊 Monitor RJ")
    st.caption("Recuperação Judicial · Extrajudicial · Falências")

    st.subheader("Dados")
    total_atual = db.count_casos()
    ultima_coleta = db.last_data_coleta()
    st.metric("Casos no banco", total_atual)
    st.caption(f"Última coleta: {ultima_coleta or '—'}")

    if st.button("🧪 Carregar dados de exemplo", use_container_width=True,
                  help="Popula o banco com dados sintéticos para você ver o dashboard funcionando antes de coletar dados reais."):
        with st.spinner("Gerando dados de exemplo..."):
            db.upsert_casos(seed_sample_data.gerar())
        st.cache_data.clear()
        st.rerun()

    with st.expander("🔄 Atualizar com dados reais (DJEN)"):
        st.caption(
            "Busca publicações públicas no Diário de Justiça Eletrônico Nacional "
            "(comunica.pje.jus.br) contendo os termos abaixo."
        )
        termos_txt = st.text_area(
            "Termos de busca (um por linha)",
            value="recuperação judicial\nrecuperação extrajudicial\nfalência",
            height=90,
        )
        dias_atras = st.slider("Coletar últimos N dias", 1, 180, 30)
        if st.button("Buscar agora", use_container_width=True, type="primary"):
            termos = [t.strip() for t in termos_txt.splitlines() if t.strip()]
            with st.spinner("Consultando o DJEN... isso pode levar alguns minutos"):
                try:
                    registros = scraper.collect(termos=termos, dias_atras=dias_atras)
                    if registros:
                        db.upsert_casos(registros)
                        st.success(f"{len(registros)} publicações coletadas e classificadas como RJ/Extrajudicial/Falência.")
                    else:
                        st.warning(
                            "Nenhum registro retornado. A API pública do DJEN pode ter mudado o "
                            "formato — veja as notas em scraper.py (função debug_ping) para diagnosticar."
                        )
                except Exception as e:
                    st.error(f"Falha ao coletar: {e}")
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
        "para ver o dashboard funcionando, ou **🔄 Atualizar com dados reais (DJEN)** para "
        "coletar publicações reais."
    )
    st.stop()

# ------------------------------------------------------------------ filtros

st.sidebar.subheader("Filtros")
periodo_min = df_all["data_publicacao"].min().date()
periodo_max = df_all["data_publicacao"].max().date()
periodo = st.sidebar.date_input(
    "Período (data de publicação)",
    value=(max(periodo_min, periodo_max - timedelta(days=365)), periodo_max),
    min_value=periodo_min,
    max_value=periodo_max,
)
tipos_sel = st.sidebar.multiselect("Tipo", sorted(df_all["tipo"].dropna().unique()), default=None)
ufs_sel = st.sidebar.multiselect("UF", sorted(df_all["uf"].dropna().unique()), default=None)
setores_sel = st.sidebar.multiselect("Setor", sorted(df_all["setor"].dropna().unique()), default=None)
busca = st.sidebar.text_input("Buscar empresa / texto")

df = df_all.copy()
if isinstance(periodo, tuple) and len(periodo) == 2:
    ini, fim = periodo
    df = df[(df["data_publicacao"].dt.date >= ini) & (df["data_publicacao"].dt.date <= fim)]
if tipos_sel:
    df = df[df["tipo"].isin(tipos_sel)]
if ufs_sel:
    df = df[df["uf"].isin(ufs_sel)]
if setores_sel:
    df = df[df["setor"].isin(setores_sel)]
if busca:
    b = busca.lower()
    df = df[
        df["empresa"].fillna("").str.lower().str.contains(b)
        | df["texto"].fillna("").str.lower().str.contains(b)
    ]

# ------------------------------------------------------------------ cabeçalho + KPIs

st.title("📊 Monitor RJ — Recuperação Judicial, Extrajudicial e Falências")
st.caption(
    f"{len(df)} casos no filtro atual · período {periodo[0] if isinstance(periodo, tuple) else periodo_min} "
    f"a {periodo[1] if isinstance(periodo, tuple) else periodo_max}"
)

# período anterior de mesmo tamanho, para calcular variação
if isinstance(periodo, tuple) and len(periodo) == 2:
    ini, fim = periodo
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

# ------------------------------------------------------------------ distribuições

colA, colB = st.columns(2)

with colA:
    st.subheader("Por UF")
    por_uf = df.groupby("uf").size().reset_index(name="casos").sort_values("casos", ascending=False).head(15)
    if not por_uf.empty:
        fig_uf = px.bar(por_uf, x="uf", y="casos", labels={"uf": "UF", "casos": "Casos"})
        fig_uf.update_layout(height=340)
        st.plotly_chart(fig_uf, use_container_width=True)
    else:
        st.caption("Sem dados de UF classificados no filtro atual.")

with colB:
    st.subheader("Por setor")
    por_setor = df.groupby("setor").size().reset_index(name="casos").sort_values("casos", ascending=False)
    if not por_setor.empty:
        fig_setor = px.pie(por_setor, names="setor", values="casos", hole=0.45)
        fig_setor.update_layout(height=340)
        st.plotly_chart(fig_setor, use_container_width=True)
    else:
        st.caption("Sem dados de setor classificados no filtro atual.")

st.caption(
    "⚠️ UF e setor são inferidos por heurísticas de texto (sigla do tribunal e palavras-chave) "
    "e podem conter erros — use como indicativo, não como fonte definitiva."
)

st.divider()

# ------------------------------------------------------------------ tabela detalhada

st.subheader("Casos")
cols_tabela = ["data_publicacao", "tipo", "empresa", "cnpj", "tribunal", "uf", "setor", "numero_processo"]
df_tabela = df[cols_tabela].sort_values("data_publicacao", ascending=False).rename(columns={
    "data_publicacao": "Data", "tipo": "Tipo", "empresa": "Empresa", "cnpj": "CNPJ",
    "tribunal": "Tribunal", "uf": "UF", "setor": "Setor", "numero_processo": "Nº Processo",
})
st.dataframe(df_tabela, use_container_width=True, hide_index=True, height=420)

csv = df_tabela.to_csv(index=False).encode("utf-8-sig")
st.download_button("⬇️ Baixar CSV do filtro atual", csv, file_name="monitor_rj_casos.csv", mime="text/csv")

with st.expander("Ver texto completo de um caso"):
    if not df.empty:
        opcoes = (df["empresa"].fillna("(sem nome extraído)") + " — " + df["data_publicacao"].dt.strftime("%d/%m/%Y")).tolist()
        idx = st.selectbox("Selecione", range(len(opcoes)), format_func=lambda i: opcoes[i])
        linha = df.iloc[idx]
        st.write(f"**Tipo:** {linha['tipo']} · **Tribunal:** {linha['tribunal']} · **Fonte:** {linha['fonte']}")
        st.write(linha["texto"])
        if linha.get("link"):
            st.markdown(f"[Abrir fonte original]({linha['link']})")
