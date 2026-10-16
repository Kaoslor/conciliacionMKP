"""Dashboard de conciliación Marketplaces vs SAP — Imega Ventus.

Lee desde PostgreSQL (tablas `marketplace` y `conciliacion_marketplace`).
Ejecutar desde la carpeta del proyecto:  py -m streamlit run app.py
"""
from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# =====================================================================
# Configuración
# =====================================================================
st.set_page_config(
    page_title="Conciliación Marketplaces · Imega Ventus",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

TTL = 60  # segundos de caché por consulta
LOGO = "logo-ImegaVentus-01.png"
TZ_BD, TZ_CL = "UTC", "America/Santiago"  # la base (RDS) guarda la hora de carga en UTC; se muestra en hora de Chile

INK, MUTED, BORDER = "#0B1B33", "#667085", "#E6E9F0"
ACCENT, NAVY = "#1E63C6", "#082F5E"  # azules del logo Imega Ventus
OK_C, WARN_C, ERR_C = "#12B76A", "#F79009", "#F04438"
FULL_C = "#7A5AF8"

# Estados que cuentan en las métricas
ESTADOS = {
    "OK": ("Conciliado", OK_C, "🟢"),
    "REVISAR_DIFERENCIA": ("Con diferencia", WARN_C, "🟠"),
    "SIN_DOC_SAP": ("Sin doc. SAP", ERR_C, "🔴"),
}
# Pagos de Mercado Pago sin pedido SAP (ventas Full): se muestran aparte y NO cuentan en las métricas
FULL = "POSIBLE_FULL"
ESTADOS_TODOS = {**ESTADOS, FULL: ("Posible Full", FULL_C, "🟣")}


def estado_lbl(e: str) -> str:
    return ESTADOS_TODOS.get(e, (e, MUTED, "⚪"))[0]


def estado_v(e: str) -> str:
    return f"{ESTADOS_TODOS.get(e, ('', '', '⚪'))[2]} {estado_lbl(e)}"


# =====================================================================
# Estilos
# =====================================================================
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
.stApp { font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; }
[data-testid="stAppDeployButton"], [data-testid="stDecoration"], footer { display: none !important; }
/* Barra superior de Streamlit transparente y contenido bajo ella (si no, tapa la cabecera) */
[data-testid="stHeader"] { background: transparent; }
.block-container, [data-testid="stMainBlockContainer"] {
  padding-top: 4.5rem !important; padding-bottom: 3rem; max-width: 1520px;
}

@keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(18,183,106,.6); }
  70% { box-shadow: 0 0 0 9px rgba(18,183,106,0); }
  100% { box-shadow: 0 0 0 0 rgba(18,183,106,0); }
}

/* ---------- Hero ---------- */
.hero {
  position: relative; overflow: hidden; border-radius: 20px; padding: 28px 32px; color: #fff;
  background:
    radial-gradient(900px 260px at 90% -30%, rgba(96,165,250,.45), transparent 60%),
    radial-gradient(600px 200px at 0% 120%, rgba(18,183,106,.25), transparent 60%),
    linear-gradient(135deg, #061F3F 0%, #082F5E 55%, #12407A 100%);
  box-shadow: 0 24px 48px -28px rgba(8,47,94,.7);
  animation: rise .5s ease-out;
}
.hero .eyebrow { font-size: .72rem; letter-spacing: .14em; text-transform: uppercase; color: rgba(255,255,255,.6); font-weight: 600; }
.hero h1 { color: #fff !important; font-size: 2rem; font-weight: 800; letter-spacing: -.025em; margin: 6px 0 6px; padding: 0; }
.hero .sub { color: rgba(255,255,255,.75); font-size: .95rem; max-width: 820px; }
.hero .meta { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 20px; }
.chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 13px; border-radius: 999px;
        background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.16); font-size: .8rem; color: #fff; }
.chip b { font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #12B76A; animation: pulse 1.8s infinite; }
.dot.off { background: #98A2B3; animation: none; }

/* ---------- KPI ---------- */
.kpis { display: grid; grid-template-columns: repeat(6, minmax(0,1fr)); gap: 14px; margin: 18px 0 10px; }
.kpis.k3 { grid-template-columns: repeat(3, minmax(0,1fr)); margin-top: 4px; }
@media (max-width: 1250px) { .kpis { grid-template-columns: repeat(3, minmax(0,1fr)); } }
@media (max-width: 680px)  { .kpis, .kpis.k3 { grid-template-columns: repeat(2, minmax(0,1fr)); } }
.kpi { position: relative; overflow: hidden; background: #fff; border: 1px solid #E6E9F0; border-radius: 16px;
       padding: 16px 18px 15px; animation: rise .5s ease-out both; transition: transform .2s, box-shadow .2s; }
.kpi:hover { transform: translateY(-3px); box-shadow: 0 14px 28px -16px rgba(16,24,40,.25); }
.kpi::before { content: ""; position: absolute; left: 0; top: 0; right: 0; height: 3px; background: var(--c); }
.kpi .lbl { font-size: .7rem; text-transform: uppercase; letter-spacing: .07em; color: #667085; font-weight: 600; }
.kpi .val { font-size: 1.5rem; font-weight: 800; color: #0B1B33; margin-top: 6px; letter-spacing: -.02em;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi .foot { font-size: .76rem; color: #667085; margin-top: 3px; }
.bar { height: 6px; background: #EEF0F5; border-radius: 99px; margin-top: 10px; overflow: hidden; }
.bar > span { display: block; height: 100%; border-radius: 99px; background: var(--c); }

/* ---------- Secciones / contenedores ---------- */
.sec { font-size: 1.02rem; font-weight: 700; color: #0B1B33; margin: 2px 0 0; }
.sec-sub { font-size: .8rem; color: #667085; margin-bottom: 6px; }
[data-testid="stVerticalBlockBorderWrapper"] { background: #fff; border-radius: 16px !important; border-color: #E6E9F0 !important; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #E6E9F0; }
.stTabs [data-baseweb="tab"] { height: 44px; padding: 0 18px; font-weight: 600; }
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E6E9F0; }
.carga { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; padding: 7px 0; border-bottom: 1px solid #EEF0F5; font-size: .82rem; color: #0B1B33; }
.carga:last-child { border-bottom: none; }
.cdot { width: 9px; height: 9px; border-radius: 50%; flex: none; }
.cmeta { flex-basis: 100%; padding-left: 17px; font-size: .72rem; color: #667085; }
.side-title { font-size: .72rem; letter-spacing: .1em; text-transform: uppercase; color: #667085; font-weight: 700; margin: 10px 0 6px; }

/* ---------- Tarjetas de marketplace ---------- */
.mkp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; margin: 8px 0 18px; }
.mkp { position: relative; overflow: hidden; background: #fff; border: 1px solid #E6E9F0; border-radius: 16px; padding: 18px;
       animation: rise .5s ease-out both; transition: transform .2s, box-shadow .2s; }
.mkp:hover { transform: translateY(-3px); box-shadow: 0 14px 28px -16px rgba(16,24,40,.25); }
.mkp::after { content: ""; position: absolute; right: -40px; top: -40px; width: 120px; height: 120px; border-radius: 50%;
              background: var(--c); opacity: .08; }
.mkp .head { display: flex; align-items: center; gap: 12px; }
.mkp .av { width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
           font-weight: 800; color: #fff; background: var(--c); font-size: .95rem; }
.mkp .name { font-weight: 700; color: #0B1B33; font-size: 1rem; line-height: 1.2; }
.mkp .mod { font-size: .74rem; color: #667085; }
.badge { margin-left: auto; font-size: .64rem; font-weight: 700; padding: 4px 9px; border-radius: 999px; text-transform: uppercase; letter-spacing: .05em; }
.b-on { background: #ECFDF3; color: #027A48; } .b-warn { background: #FFFAEB; color: #B54708; }
.b-off { background: #F2F4F7; color: #667085; } .b-idle { background: #EEF4FF; color: #3538CD; }
.mkp .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 16px; }
.mkp .stats span { display: block; font-size: .64rem; color: #667085; text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }
.mkp .stats b { font-size: 1.02rem; color: #0B1B33; }
.mkp .amt { margin-top: 12px; font-size: .78rem; color: #667085; display: flex; justify-content: space-between; }
.mkp .amt b { color: #0B1B33; }
.mkp.off { background: #FCFCFD; border-style: dashed; }
.mkp.off .av { background: #D0D5DD; }
.mkp .soon { margin-top: 16px; font-size: .82rem; color: #667085; }

/* ---------- Posibles Full (fuera de métricas) ---------- */
.aparte { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 4px 0 14px; padding: 10px 14px;
          border-radius: 12px; background: #F4F3FF; border: 1px solid #D9D6FE; color: #3E1C96; font-size: .84rem; }
.aparte .tag { font-size: .64rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; padding: 3px 9px;
               border-radius: 999px; background: #EBE9FE; color: #5925DC; white-space: nowrap; }
.fullnote { margin-top: 10px; font-size: .74rem; color: #5925DC; background: #F4F3FF; border-radius: 8px; padding: 5px 9px; }
.explica { background: #fff; border: 1px solid #E6E9F0; border-left: 4px solid #7A5AF8; border-radius: 12px;
           padding: 14px 16px; font-size: .86rem; color: #344054; margin-bottom: 12px; line-height: 1.55; }
.explica b { color: #0B1B33; }

.empty { text-align: center; padding: 42px 20px; background: #fff; border: 1px dashed #D0D5DD; border-radius: 16px; color: #667085; }
.empty b { display: block; color: #0B1B33; font-size: 1.05rem; margin-bottom: 4px; }
.foot-note { text-align: center; color: #98A2B3; font-size: .75rem; margin-top: 28px; }
</style>
""",
    unsafe_allow_html=True,
)


# =====================================================================
# Utilidades
# =====================================================================
def clp(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    s = f"{abs(float(x)):,.0f}".replace(",", ".")
    return f"-${s}" if float(x) < 0 else f"${s}"


def pct(x, dec: int = 1) -> str:
    return f"{x:.{dec}f}%".replace(".", ",")


def n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def initials(nombre: str) -> str:
    parts = nombre.replace("/", " ").split()
    return "".join(p[0] for p in parts[:2]).upper()


def kpi(label: str, value: str, foot: str = "", color: str = ACCENT, bar: float | None = None) -> str:
    bar_html = f'<div class="bar"><span style="width:{max(0, min(bar, 100)):.1f}%"></span></div>' if bar is not None else ""
    return (f'<div class="kpi" style="--c:{color}"><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div>{bar_html}<div class="foot">{foot}</div></div>')


def section(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="sec">{title}</div><div class="sec-sub">{sub}</div>', unsafe_allow_html=True)


def chart(fig: go.Figure, height: int = 330) -> None:
    fig.update_layout(
        height=height, margin=dict(l=6, r=6, t=8, b=6),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#344054"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None, font=dict(size=11)),
        hoverlabel=dict(bgcolor=INK, font_color="#fff", bordercolor=INK, font_family="Inter"),
        separators=",.",  # decimales con coma, miles con punto (CLP)
    )
    fig.update_xaxes(showgrid=False, linecolor=BORDER, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor="#EEF0F5", zeroline=False, tickfont=dict(color=MUTED))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def a_hora_chile(s: pd.Series) -> pd.Series:
    t = pd.to_datetime(s, errors="coerce", format="mixed")
    if t.dt.tz is None:
        t = t.dt.tz_localize(TZ_BD)
    return t.dt.tz_convert(TZ_CL).dt.tz_localize(None)


def tasa_color(t: float) -> str:
    return OK_C if t >= 95 else WARN_C if t >= 80 else ERR_C


# =====================================================================
# Datos base
# =====================================================================
conn = st.connection("postgres", type="sql")

catalogo = conn.query(
    "SELECT codigo, nombre, color, activo, orden FROM marketplace ORDER BY orden, nombre", ttl=600
)
catalogo["activo"] = catalogo["activo"].astype(bool)
NOMBRES = dict(zip(catalogo["codigo"], catalogo["nombre"]))
COLORES = dict(zip(catalogo["codigo"], catalogo["color"]))

rango = conn.query(
    """
    SELECT marketplace, MIN(fecha_transaccion) AS dmin, MAX(fecha_transaccion) AS dmax,
           MAX(fecha_ejecucion) AS ult_carga
    FROM conciliacion_marketplace GROUP BY marketplace
    """,
    ttl=TTL,
)
for c in ("dmin", "dmax"):
    rango[c] = pd.to_datetime(rango[c]).dt.date
rango["ult_carga"] = a_hora_chile(rango["ult_carga"])

con_datos = set(rango["marketplace"])
disponibles = catalogo[catalogo["activo"] | catalogo["codigo"].isin(con_datos)]
proximos = catalogo[~catalogo["activo"] & ~catalogo["codigo"].isin(con_datos)]

# =====================================================================
# Barra lateral
# =====================================================================
with st.sidebar:
    if os.path.exists(LOGO):
        st.image(LOGO, width="stretch")
    else:
        st.markdown(f"<h2 style='color:{NAVY};margin:0'>Imega Ventus</h2>", unsafe_allow_html=True)

    st.markdown('<div class="side-title">Parámetros de control</div>', unsafe_allow_html=True)

    mkp_sel = st.multiselect(
        "Marketplaces",
        disponibles["codigo"].tolist(),
        default=disponibles["codigo"].tolist(),
        format_func=lambda c: NOMBRES.get(c, c),
    )

    r = rango[rango["marketplace"].isin(mkp_sel)]
    if r.empty:
        desde = hasta = None
    else:
        dmin, dmax = r["dmin"].min(), r["dmax"].max()
        fechas = st.date_input("Período", value=(dmin, dmax), min_value=dmin, max_value=dmax, format="DD/MM/YYYY")
        if isinstance(fechas, (tuple, list)):
            desde, hasta = (fechas[0], fechas[1]) if len(fechas) == 2 else (fechas[0], fechas[0])
        else:
            desde = hasta = fechas

    st.markdown('<div class="side-title">Sincronización</div>', unsafe_allow_html=True)
    auto = st.toggle("Actualización automática", value=True, help="Refresca los datos cada 60 segundos.")
    if st.button("Sincronizar ahora", width="stretch", type="primary"):
        st.cache_data.clear()
        st.rerun()

    if not rango.empty:
        st.markdown('<div class="side-title">Última carga por canal</div>', unsafe_allow_html=True)
        filas = []
        for _, rr in rango.sort_values("ult_carga", ascending=False).iterrows():
            carga = pd.to_datetime(rr["ult_carga"], errors="coerce", format="mixed")
            carga_txt = f"{carga:%d/%m %H:%M}" if not pd.isna(carga) else "—"
            dia_txt = f"{rr['dmax']:%d/%m}" if not pd.isna(rr["dmax"]) else "—"
            color = COLORES.get(rr["marketplace"], ACCENT)
            filas.append(
                f'<div class="carga"><span class="cdot" style="background:{color}"></span>'
                f'<b>{NOMBRES.get(rr["marketplace"], rr["marketplace"])}</b>'
                f'<span class="cmeta">ventas al {dia_txt} · cargado {carga_txt}</span></div>')
        st.markdown("".join(filas), unsafe_allow_html=True)

    if not proximos.empty:
        st.markdown('<div class="side-title">Próximas integraciones</div>', unsafe_allow_html=True)
        st.caption(" · ".join(proximos["nombre"]))

# =====================================================================
# Dashboard
# =====================================================================
SQL = """
    SELECT marketplace, modalidad_logistica, fecha_transaccion, n_orden, documento_sap,
           tipo_transaccion, monto_marketplace, monto_sap, diferencia, estado,
           ref_pago, id_liquidacion, fecha_ejecucion
    FROM conciliacion_marketplace
    WHERE fecha_transaccion BETWEEN :d AND :h
    ORDER BY fecha_transaccion DESC, marketplace, n_orden
"""


def hero(df: pd.DataFrame) -> None:
    nombres = ", ".join(NOMBRES.get(c, c) for c in mkp_sel) or "—"
    periodo = f"{desde:%d/%m/%Y} — {hasta:%d/%m/%Y}" if desde else "Sin datos"
    ultima = pd.to_datetime(df["fecha_ejecucion"]).max() if not df.empty else None
    ultima_txt = f"{ultima:%d/%m/%Y %H:%M}" if ultima is not None and not pd.isna(ultima) else "—"
    vivo = ('<span class="chip"><span class="dot"></span><b>En vivo</b> · cada 60 s</span>' if auto
            else '<span class="chip"><span class="dot off"></span>Actualización manual</span>')
    st.markdown(
        f"""
<div class="hero">
  <div class="eyebrow">Finanzas · Conciliación de recaudación</div>
  <h1>Marketplaces vs SAP</h1>
  <div class="sub">Cruce por orden de los extractos de pago de cada marketplace contra los documentos de venta SAP, con montos con IVA.</div>
  <div class="meta">
    <span class="chip">Período <b>{periodo}</b></span>
    <span class="chip">Canales <b>{nombres}</b></span>
    <span class="chip">Última carga <b>{ultima_txt}</b></span>
    {vivo}
  </div>
</div>""",
        unsafe_allow_html=True,
    )


def tab_resumen(df: pd.DataFrame, tasa: float) -> None:
    c1, c2 = st.columns([2, 1], gap="medium")
    with c1, st.container(border=True):
        section("Evolución diaria por estado", "Órdenes conciliadas por fecha de transacción")
        daily = df.groupby(["fecha_transaccion", "estado"]).size().reset_index(name="ordenes")
        fig = go.Figure()
        for est, (lbl, col, _) in ESTADOS.items():
            s = daily[daily["estado"] == est]
            if not s.empty:
                fig.add_bar(x=s["fecha_transaccion"], y=s["ordenes"], name=lbl, marker_color=col,
                            hovertemplate="%{x|%d/%m}<br>" + lbl + ": %{y}<extra></extra>")
        fig.update_layout(barmode="stack", bargap=0.35)
        fig.update_xaxes(tickformat="%d/%m")
        chart(fig)
    with c2, st.container(border=True):
        section("Distribución", "Estado del total de órdenes")
        cnt = df["estado"].value_counts()
        keys = [k for k in ESTADOS if k in cnt.index]
        fig = go.Figure(go.Pie(
            labels=[ESTADOS[k][0] for k in keys], values=[int(cnt[k]) for k in keys],
            marker=dict(colors=[ESTADOS[k][1] for k in keys], line=dict(color="#fff", width=3)),
            hole=0.72, sort=False, textinfo="none",
            hovertemplate="%{label}: %{value} órdenes (%{percent})<extra></extra>",
        ))
        fig.add_annotation(text=f"<b style='font-size:30px;color:{INK}'>{pct(tasa, 0)}</b><br>"
                                f"<span style='color:{MUTED};font-size:12px'>conciliado</span>",
                           showarrow=False)
        fig.update_layout(legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center", yanchor="top"))
        chart(fig)

    c3, c4 = st.columns(2, gap="medium")
    with c3, st.container(border=True):
        section("Montos diarios", "Marketplace vs SAP, con IVA")
        m = df.groupby("fecha_transaccion")[["monto_marketplace", "monto_sap"]].sum().reset_index()
        fig = go.Figure()
        fig.add_scatter(x=m["fecha_transaccion"], y=m["monto_marketplace"], name="Marketplace",
                        mode="lines+markers", line=dict(color=ACCENT, width=3, shape="spline"),
                        fill="tozeroy", fillcolor="rgba(30,99,198,.10)", marker=dict(size=6),
                        hovertemplate="%{x|%d/%m}<br>Marketplace: $%{y:,.0f}<extra></extra>")
        fig.add_scatter(x=m["fecha_transaccion"], y=m["monto_sap"], name="SAP",
                        mode="lines", line=dict(color=NAVY, width=2, dash="dot", shape="spline"),
                        hovertemplate="%{x|%d/%m}<br>SAP: $%{y:,.0f}<extra></extra>")
        fig.update_xaxes(tickformat="%d/%m")
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        chart(fig, 300)
    with c4, st.container(border=True):
        section("Descuadre diario", "Suma de diferencias (SAP − marketplace)")
        d = df.groupby("fecha_transaccion")["diferencia"].sum().reset_index()
        cols = [OK_C if abs(v) <= 2 else (ERR_C if v < 0 else WARN_C) for v in d["diferencia"]]
        fig = go.Figure(go.Bar(x=d["fecha_transaccion"], y=d["diferencia"], marker_color=cols,
                               hovertemplate="%{x|%d/%m}<br>Diferencia: $%{y:,.0f}<extra></extra>"))
        fig.add_hline(y=0, line_color=BORDER)
        fig.update_layout(bargap=0.4, showlegend=False)
        fig.update_xaxes(tickformat="%d/%m")
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        chart(fig, 300)


def tab_marketplaces(df: pd.DataFrame, full: pd.DataFrame) -> None:
    section("Canales de venta", "Estado de la conciliación por marketplace en el período seleccionado")
    fstats = full.groupby("marketplace")["monto_marketplace"].agg(["size", "sum"])

    def nota_full(code: str) -> str:
        if code not in fstats.index:
            return ""
        return (f'<div class="fullnote">🟣 + {n(fstats.loc[code, "size"])} posibles Full fuera de métricas · '
                f'{clp(fstats.loc[code, "sum"])}</div>')

    stats = (df.groupby("marketplace")
               .agg(ordenes=("n_orden", "size"),
                    ok=("estado", lambda s: int((s == "OK").sum())),
                    monto_mkp=("monto_marketplace", "sum"),
                    monto_sap=("monto_sap", "sum"),
                    dif=("diferencia", "sum"),
                    modalidad=("modalidad_logistica", lambda s: ", ".join(sorted(s.dropna().unique())))))
    stats["exc"] = stats["ordenes"] - stats["ok"]
    stats["tasa"] = 100 * stats["ok"] / stats["ordenes"]

    cards = []
    for _, m in catalogo.iterrows():
        code, nombre, color = m["codigo"], m["nombre"], m["color"]
        if code in stats.index:
            s = stats.loc[code]
            badge = ('<span class="badge b-on">Al día</span>' if s["exc"] == 0
                     else f'<span class="badge b-warn">{int(s["exc"])} por revisar</span>')
            cards.append(f"""
<div class="mkp" style="--c:{color}">
  <div class="head"><div class="av">{initials(nombre)}</div>
    <div><div class="name">{nombre}</div><div class="mod">{s['modalidad'] or 'Activo'}</div></div>{badge}</div>
  <div class="stats">
    <div><span>Órdenes</span><b>{n(s['ordenes'])}</b></div>
    <div><span>Conciliado</span><b style="color:{tasa_color(s['tasa'])}">{pct(s['tasa'])}</b></div>
    <div><span>Descuadre</span><b>{clp(s['dif'])}</b></div>
  </div>
  <div class="bar" style="--c:{tasa_color(s['tasa'])}"><span style="width:{s['tasa']:.1f}%"></span></div>
  <div class="amt"><span>Marketplace <b>{clp(s['monto_mkp'])}</b></span><span>SAP <b>{clp(s['monto_sap'])}</b></span></div>
  {nota_full(code)}
</div>""")
        elif m["activo"]:
            soon = ("Todas las órdenes del período quedaron como posibles Full." if code in fstats.index
                    else "No hay órdenes en el período o el canal no está seleccionado.")
            cards.append(f"""
<div class="mkp" style="--c:{color}">
  <div class="head"><div class="av">{initials(nombre)}</div>
    <div><div class="name">{nombre}</div><div class="mod">Integración activa</div></div>
    <span class="badge b-idle">Sin movimientos</span></div>
  <div class="soon">{soon}</div>
  {nota_full(code)}
</div>""")
        else:
            cards.append(f"""
<div class="mkp off" style="--c:{color}">
  <div class="head"><div class="av">{initials(nombre)}</div>
    <div><div class="name">{nombre}</div><div class="mod">Integración pendiente</div></div>
    <span class="badge b-off">Próximamente</span></div>
  <div class="soon">El flujo de conciliación de este canal aún no está montado en n8n.</div>
</div>""")
    st.markdown(f'<div class="mkp-grid">{"".join(cards)}</div>', unsafe_allow_html=True)

    if stats.empty:
        return
    stats = stats.sort_values("tasa")
    labels = [NOMBRES.get(c, c) for c in stats.index]
    colors = [COLORES.get(c, ACCENT) for c in stats.index]

    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True):
        section("Tasa de conciliación", "% de órdenes en estado OK")
        fig = go.Figure(go.Bar(
            x=stats["tasa"], y=labels, orientation="h", marker_color=colors,
            text=[pct(t) for t in stats["tasa"]], textposition="outside",
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        fig.update_xaxes(range=[0, 110], ticksuffix="%")
        fig.update_layout(showlegend=False, bargap=0.45)
        chart(fig, max(220, 70 * len(stats) + 80))
    with c2, st.container(border=True):
        section("Recaudación por canal", "Montos con IVA: marketplace vs SAP")
        fig = go.Figure()
        fig.add_bar(y=labels, x=stats["monto_mkp"], name="Marketplace", orientation="h", marker_color=ACCENT,
                    hovertemplate="%{y}<br>Marketplace: $%{x:,.0f}<extra></extra>")
        fig.add_bar(y=labels, x=stats["monto_sap"], name="SAP", orientation="h", marker_color=NAVY,
                    hovertemplate="%{y}<br>SAP: $%{x:,.0f}<extra></extra>")
        fig.update_layout(barmode="group", bargap=0.35)
        fig.update_xaxes(tickprefix="$", tickformat=",.0f")
        chart(fig, max(220, 70 * len(stats) + 80))

    exc = df[df["estado"] != "OK"]
    if not exc.empty:
        with st.container(border=True):
            section("Mapa de excepciones", "Órdenes no conciliadas por día y canal")
            hm = exc.groupby(["marketplace", "fecha_transaccion"]).size().unstack(fill_value=0)
            fig = go.Figure(go.Heatmap(
                z=hm.values, x=hm.columns, y=[NOMBRES.get(c, c) for c in hm.index],
                colorscale=[[0, "#FFFFFF"], [0.001, "#FEF0C7"], [1, ERR_C]], xgap=3, ygap=3,
                hovertemplate="%{y} · %{x|%d/%m}: %{z} excepciones<extra></extra>", showscale=False))
            fig.update_xaxes(tickformat="%d/%m")
            chart(fig, max(160, 60 * len(hm) + 70))


def tab_excepciones(df: pd.DataFrame) -> None:
    exc = df[df["estado"] != "OK"].copy()
    if exc.empty:
        st.markdown('<div class="empty"><b>Todo conciliado ✔</b>No hay órdenes con diferencia ni sin documento SAP en el período.</div>',
                    unsafe_allow_html=True)
        return

    exc["exposicion"] = exc["diferencia"].abs().fillna(exc["monto_marketplace"].abs())
    exc = exc.sort_values("exposicion", ascending=False)
    maxe = exc["exposicion"].max() or 1
    exc["impacto"] = 100 * exc["exposicion"] / maxe
    exc["canal"] = exc["marketplace"].map(NOMBRES).fillna(exc["marketplace"])
    exc["estado_v"] = exc["estado"].map(estado_v)

    rev = int((exc["estado"] == "REVISAR_DIFERENCIA").sum())
    sin = int((exc["estado"] == "SIN_DOC_SAP").sum())
    st.markdown('<div class="kpis k3">'
                + kpi("Con diferencia", n(rev), f"Descuadre {clp(exc.loc[exc.estado == 'REVISAR_DIFERENCIA', 'diferencia'].sum())}", WARN_C)
                + kpi("Sin documento SAP", n(sin), f"Monto {clp(exc.loc[exc.estado == 'SIN_DOC_SAP', 'monto_marketplace'].sum())}", ERR_C)
                + kpi("Exposición total", clp(exc["exposicion"].sum()), "Suma de diferencias absolutas y montos sin SAP", NAVY)
                + "</div>", unsafe_allow_html=True)

    with st.container(border=True):
        section("Órdenes a revisar", "Ordenadas por exposición (mayor a menor)")
        st.dataframe(
            exc[["canal", "fecha_transaccion", "n_orden", "documento_sap", "monto_marketplace",
                 "monto_sap", "diferencia", "estado_v", "impacto", "tipo_transaccion"]],
            width="stretch", hide_index=True, height=min(560, 38 * len(exc) + 40),
            column_config={
                "canal": "Canal",
                "fecha_transaccion": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                "n_orden": "N° orden",
                "documento_sap": "Doc. SAP",
                "monto_marketplace": st.column_config.NumberColumn("Monto marketplace", format="localized"),
                "monto_sap": st.column_config.NumberColumn("Monto SAP", format="localized"),
                "diferencia": st.column_config.NumberColumn("Diferencia", format="localized"),
                "estado_v": "Estado",
                "impacto": st.column_config.ProgressColumn("Exposición relativa", min_value=0, max_value=100, format="%.0f%%"),
                "tipo_transaccion": st.column_config.TextColumn("Tipo de transacción", width="large"),
            },
        )
        st.download_button(
            "Descargar excepciones (CSV)",
            exc.drop(columns=["exposicion", "impacto", "canal", "estado_v"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name=f"Excepciones_{desde}_{hasta}.csv", mime="text/csv",
        )


def tab_detalle(df: pd.DataFrame) -> None:
    c1, c2 = st.columns([1, 1])
    buscar = c1.text_input("Buscar", placeholder="N° de orden, documento SAP o referencia de pago")
    est = c2.multiselect("Estado", list(ESTADOS), default=list(ESTADOS), format_func=estado_lbl)

    d = df[df["estado"].isin(est)].copy()
    if buscar:
        q = buscar.strip().lower()
        mask = (d["n_orden"].astype(str).str.lower().str.contains(q, regex=False)
                | d["documento_sap"].fillna("").astype(str).str.lower().str.contains(q, regex=False)
                | d["ref_pago"].fillna("").astype(str).str.lower().str.contains(q, regex=False))
        d = d[mask]
    d["canal"] = d["marketplace"].map(NOMBRES).fillna(d["marketplace"])
    d["estado_v"] = d["estado"].map(estado_v)

    with st.container(border=True):
        section("Registro completo", f"{n(len(d))} órdenes")
        st.dataframe(
            d[["canal", "modalidad_logistica", "fecha_transaccion", "n_orden", "documento_sap",
               "monto_marketplace", "monto_sap", "diferencia", "estado_v", "ref_pago",
               "tipo_transaccion", "fecha_ejecucion"]],
            width="stretch", hide_index=True, height=520,
            column_config={
                "canal": "Canal", "modalidad_logistica": "Modalidad",
                "fecha_transaccion": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                "n_orden": "N° orden", "documento_sap": "Doc. SAP",
                "monto_marketplace": st.column_config.NumberColumn("Monto marketplace", format="localized"),
                "monto_sap": st.column_config.NumberColumn("Monto SAP", format="localized"),
                "diferencia": st.column_config.NumberColumn("Diferencia", format="localized"),
                "estado_v": "Estado", "ref_pago": "Ref. pago",
                "tipo_transaccion": "Tipo de transacción",
                "fecha_ejecucion": st.column_config.DatetimeColumn("Cargado", format="DD/MM/YYYY HH:mm"),
            },
        )
        st.download_button(
            "Exportar informe (CSV)",
            d.drop(columns=["canal", "estado_v"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name=f"Informe_Conciliacion_{desde}_{hasta}.csv", mime="text/csv", type="primary",
        )


def tab_full(full: pd.DataFrame) -> None:
    st.markdown(
        '<div class="explica"><b>Qué son.</b> Pagos de Mercado Pago cuya orden no tiene pedido en SAP. '
        'Por su patrón corresponden a ventas <b>Full</b> (despachadas desde la bodega de Mercado Libre): no generan pedido '
        'y se facturan en la liquidación semanal de Mercado Libre. Por eso se muestran aquí y <b>no cuentan</b> '
        'en la tasa de conciliación, las excepciones ni los montos del resto del tablero.<br>'
        '<b>Pendiente.</b> Cruzarlas con la liquidación semanal para confirmarlas como Full.</div>',
        unsafe_allow_html=True,
    )
    ventas = full[full["monto_marketplace"] >= 0]
    devs = full[full["monto_marketplace"] < 0]
    cuentas = ", ".join(sorted(full["modalidad_logistica"].dropna().unique())) or "—"
    st.markdown('<div class="kpis k3">'
                + kpi("Órdenes", n(len(full)), cuentas, FULL_C)
                + kpi("Ventas", clp(ventas["monto_marketplace"].sum()), f"{n(len(ventas))} pagos", FULL_C)
                + kpi("Devoluciones", clp(devs["monto_marketplace"].sum()), f"{n(len(devs))} movimientos", MUTED)
                + "</div>", unsafe_allow_html=True)

    f = full.sort_values(["fecha_transaccion", "monto_marketplace"], ascending=[False, False])
    with st.container(border=True):
        section("Pagos sin pedido SAP", f"{n(len(f))} órdenes · {clp(f['monto_marketplace'].sum())}")
        st.dataframe(
            f[["modalidad_logistica", "fecha_transaccion", "n_orden", "monto_marketplace", "tipo_transaccion", "ref_pago"]],
            width="stretch", hide_index=True, height=min(560, 38 * len(f) + 40),
            column_config={
                "modalidad_logistica": "Cuenta",
                "fecha_transaccion": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                "n_orden": "N° orden",
                "monto_marketplace": st.column_config.NumberColumn("Monto Mercado Pago", format="localized"),
                "tipo_transaccion": st.column_config.TextColumn("Detalle", width="large"),
                "ref_pago": "Ref. pago",
            },
        )
        st.download_button(
            "Descargar posibles Full (CSV)",
            f.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name=f"Posibles_Full_{desde}_{hasta}.csv", mime="text/csv",
        )


def dashboard() -> None:
    if not mkp_sel or desde is None:
        hero(pd.DataFrame(columns=["fecha_ejecucion"]))
        st.markdown('<div class="empty"><b>Sin información para mostrar</b>'
                    'Selecciona al menos un marketplace con datos o verifica la ingesta de n8n.</div>',
                    unsafe_allow_html=True)
        return

    df = conn.query(SQL, params={"d": desde, "h": hasta}, ttl=TTL)
    df = df[df["marketplace"].isin(mkp_sel)].copy()
    for c in ("monto_marketplace", "monto_sap", "diferencia"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["fecha_transaccion"] = pd.to_datetime(df["fecha_transaccion"])
    df["fecha_ejecucion"] = a_hora_chile(df["fecha_ejecucion"])

    hero(df)
    if df.empty:
        st.markdown('<div class="empty"><b>Sin órdenes en el período</b>Ajusta el rango de fechas o los marketplaces.</div>',
                    unsafe_allow_html=True)
        return

    # Los posibles Full se separan aquí: desde esta línea, todas las métricas y pestañas usan solo `df`
    full = df[df["estado"] == FULL].copy()
    df = df[df["estado"] != FULL].copy()

    total = len(df)
    ok = int((df["estado"] == "OK").sum())
    rev = int((df["estado"] == "REVISAR_DIFERENCIA").sum())
    sin = int((df["estado"] == "SIN_DOC_SAP").sum())
    tasa = 100 * ok / total if total else 0.0
    dif_neta = df["diferencia"].sum()
    dif_abs = df["diferencia"].abs().sum()

    st.markdown(
        '<div class="kpis">'
        + kpi("Órdenes procesadas", n(total), f"{df['marketplace'].nunique()} canal(es) · {n(ok)} conciliadas", ACCENT)
        + (kpi("Tasa de conciliación", pct(tasa), "Órdenes en estado OK", tasa_color(tasa), bar=tasa) if total
           else kpi("Tasa de conciliación", "—", "Sin órdenes conciliables en el período", MUTED))
        + kpi("Excepciones", n(rev + sin), f"{rev} con diferencia · {sin} sin doc. SAP", WARN_C if rev + sin else OK_C)
        + kpi("Recaudación marketplace", clp(df["monto_marketplace"].sum()), "Con IVA", NAVY)
        + kpi("Registrado en SAP", clp(df["monto_sap"].sum()), "Con IVA (neto × 1,19)", "#0EA5E9")
        + kpi("Descuadre neto", clp(dif_neta), f"Absoluto {clp(dif_abs)}", OK_C if abs(dif_neta) <= 2 else ERR_C)
        + "</div>",
        unsafe_allow_html=True,
    )
    if not full.empty:
        st.markdown(
            f'<div class="aparte"><span class="tag">Fuera de métricas</span><span><b>{n(len(full))} pagos de '
            f'Mercado Pago</b> sin pedido en SAP ({clp(full["monto_marketplace"].sum())}), probablemente ventas '
            f'Full, se muestran aparte en la pestaña <b>Posibles Full</b>.</span></div>',
            unsafe_allow_html=True,
        )

    nombres = ["Resumen", "Por marketplace", f"Excepciones ({rev + sin})", "Detalle"]
    if not full.empty:
        nombres.append(f"Posibles Full ({len(full)})")
    tabs = st.tabs(nombres)
    with tabs[0]:
        tab_resumen(df, tasa)
    with tabs[1]:
        tab_marketplaces(df, full)
    with tabs[2]:
        tab_excepciones(df)
    with tabs[3]:
        tab_detalle(df)
    if not full.empty:
        with tabs[4]:
            tab_full(full)

    st.markdown('<div class="foot-note">Imega Ventus · Conciliación automatizada n8n → PostgreSQL · '
                'Tolerancia de redondeo ±$2 por orden</div>', unsafe_allow_html=True)


# Solo esta sección se re-ejecuta cada 60 s cuando la actualización automática está activa
st.fragment(run_every="60s" if auto else None)(dashboard)()