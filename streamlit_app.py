import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import motor_btc as motor


# ============================================================
# CONFIGURACION
# ============================================================

st.set_page_config(
    page_title="BTC 15M Profit Engine",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

HISTORIAL_FILE = "historial_btc_15m.json"

LOCAL_TZ = ZoneInfo("America/Chicago")


# ============================================================
# AUTO REFRESH
# ============================================================

st.markdown(
    """
    <meta http-equiv="refresh" content="10">
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>

html, body, [class*="css"] {
    font-family: Inter, Arial, sans-serif;
}

.stApp {
    background:
        radial-gradient(
            circle at 10% 5%,
            rgba(0, 212, 255, .13),
            transparent 25%
        ),
        radial-gradient(
            circle at 90% 5%,
            rgba(168, 85, 247, .14),
            transparent 28%
        ),
        linear-gradient(
            180deg,
            #02050a 0%,
            #07101d 48%,
            #02050a 100%
        );
}

.block-container {
    max-width: 1500px;
    padding-top: 1rem;
    padding-bottom: 4rem;
}

h1, h2, h3 {
    color: #f8fafc;
}

.top-title {
    font-size: 2.4rem;
    font-weight: 900;
    letter-spacing: -1.5px;
    color: white;
}

.top-subtitle {
    color: #94a3b8;
    font-size: .95rem;
    margin-bottom: 1.2rem;
}

.card {
    background:
        linear-gradient(
            145deg,
            rgba(15, 23, 42, .96),
            rgba(6, 12, 23, .96)
        );
    border: 1px solid rgba(148, 163, 184, .14);
    border-radius: 18px;
    padding: 18px;
    margin-bottom: 10px;
    box-shadow:
        0 15px 35px rgba(0,0,0,.25);
}

.card-title {
    color: #94a3b8;
    font-size: .76rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.card-value {
    color: #f8fafc;
    font-size: 1.65rem;
    font-weight: 850;
    margin-top: 4px;
}

.card-small {
    color: #64748b;
    font-size: .78rem;
}

.decision-up {
    background:
        linear-gradient(
            135deg,
            rgba(16,185,129,.25),
            rgba(5,46,22,.55)
        );
    border: 1px solid rgba(16,185,129,.45);
    border-radius: 22px;
    text-align: center;
    padding: 25px;
}

.decision-down {
    background:
        linear-gradient(
            135deg,
            rgba(239,68,68,.23),
            rgba(69,10,10,.55)
        );
    border: 1px solid rgba(239,68,68,.45);
    border-radius: 22px;
    text-align: center;
    padding: 25px;
}

.decision-no {
    background:
        linear-gradient(
            135deg,
            rgba(148,163,184,.17),
            rgba(15,23,42,.7)
        );
    border: 1px solid rgba(148,163,184,.30);
    border-radius: 22px;
    text-align: center;
    padding: 25px;
}

.decision-label {
    color: #94a3b8;
    font-size: .8rem;
    font-weight: 800;
    letter-spacing: 1.5px;
}

.decision-value {
    color: white;
    font-size: 2.6rem;
    font-weight: 950;
    margin: 3px 0;
}

.decision-info {
    color: #cbd5e1;
    font-size: .92rem;
}

.section-title {
    font-weight: 850;
    font-size: 1.15rem;
    color: #e2e8f0;
    margin-top: 18px;
    margin-bottom: 8px;
}

.scale-wrap {
    background: rgba(15,23,42,.80);
    border: 1px solid rgba(148,163,184,.13);
    border-radius: 14px;
    padding: 13px 14px 12px 14px;
    margin-bottom: 9px;
}

.scale-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 7px;
}

.scale-name {
    color: #cbd5e1;
    font-size: .85rem;
    font-weight: 700;
}

.scale-number {
    color: white;
    font-size: .95rem;
    font-weight: 850;
}

.scale-track {
    position: relative;
    height: 10px;
    border-radius: 50px;
    background:
        linear-gradient(
            90deg,
            #ef4444 0%,
            #f97316 23%,
            #64748b 50%,
            #22c55e 77%,
            #10b981 100%
        );
    overflow: hidden;
}

.scale-marker {
    position: absolute;
    width: 4px;
    height: 16px;
    background: white;
    border-radius: 3px;
    top: -3px;
    box-shadow: 0 0 8px white;
}

.scale-limits {
    display: flex;
    justify-content: space-between;
    color: #64748b;
    font-size: .66rem;
    margin-top: 5px;
}

.prob-track {
    height: 17px;
    border-radius: 50px;
    background:
        linear-gradient(
            90deg,
            #ef4444 0%,
            #64748b 50%,
            #10b981 100%
        );
    position: relative;
    overflow: hidden;
}

.prob-marker {
    position: absolute;
    width: 5px;
    height: 23px;
    background: white;
    top: -3px;
    border-radius: 4px;
    box-shadow: 0 0 10px white;
}

.metric-table {
    width: 100%;
    border-collapse: collapse;
}

.metric-table td {
    padding: 7px 4px;
    border-bottom: 1px solid rgba(148,163,184,.08);
}

.metric-name {
    color: #94a3b8;
    font-size: .82rem;
}

.metric-value {
    color: #f8fafc;
    font-size: .84rem;
    font-weight: 750;
    text-align: right;
}

.reason {
    background: rgba(15,23,42,.8);
    border-left: 3px solid #38bdf8;
    padding: 8px 10px;
    border-radius: 7px;
    margin-bottom: 5px;
    color: #cbd5e1;
    font-size: .82rem;
}

hr {
    border-color: rgba(148,163,184,.10);
}

div.stButton > button {
    width: 100%;
    border-radius: 12px;
    font-weight: 850;
    min-height: 46px;
}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# UTILIDADES
# ============================================================

def numero(
    valor,
    decimales=2,
    prefijo="",
    sufijo="",
):
    if valor is None:
        return "N/D"

    try:
        return (
            f"{prefijo}"
            f"{float(valor):,.{decimales}f}"
            f"{sufijo}"
        )

    except Exception:
        return str(valor)


def cargar_historial():
    if not os.path.exists(
        HISTORIAL_FILE
    ):
        return []

    try:
        with open(
            HISTORIAL_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            datos = json.load(f)

        if isinstance(
            datos,
            list,
        ):
            return datos

    except Exception:
        pass

    return []


def eliminar_historial():
    try:
        if os.path.exists(
            HISTORIAL_FILE
        ):
            os.remove(
                HISTORIAL_FILE
            )

        st.success(
            "Historial eliminado."
        )

    except Exception as e:
        st.error(
            f"Error eliminando historial: {e}"
        )


def tarjeta(
    titulo,
    valor,
    detalle="",
):
    st.markdown(
        f"""
        <div class="card">
            <div class="card-title">
                {titulo}
            </div>
            <div class="card-value">
                {valor}
            </div>
            <div class="card-small">
                {detalle}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def escala(
    nombre,
    valor,
    minimo,
    maximo,
    formato="{:.3f}",
):
    try:
        valor_num = float(
            valor
        )

    except Exception:
        valor_num = 0.0

    if maximo == minimo:
        porcentaje = 50

    else:
        porcentaje = (
            (
                valor_num
                - minimo
            )
            /
            (
                maximo
                - minimo
            )
        ) * 100

    porcentaje = max(
        0,
        min(
            100,
            porcentaje,
        ),
    )

    try:
        texto = formato.format(
            valor_num
        )

    except Exception:
        texto = str(
            valor_num
        )

    st.markdown(
        f"""
        <div class="scale-wrap">

            <div class="scale-header">
                <span class="scale-name">
                    {nombre}
                </span>

                <span class="scale-number">
                    {texto}
                </span>
            </div>

            <div class="scale-track">
                <div
                    class="scale-marker"
                    style="left:{porcentaje}%;">
                </div>
            </div>

            <div class="scale-limits">
                <span>{minimo}</span>
                <span>NEUTRO</span>
                <span>{maximo}</span>
            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )


def escala_probabilidad(
    prob_arriba,
):
    try:
        p = float(
            prob_arriba
        )

    except Exception:
        p = 50.0

    p = max(
        0,
        min(
            100,
            p,
        ),
    )

    st.markdown(
        f"""
        <div class="scale-wrap">

            <div class="scale-header">

                <span class="scale-name">
                    PROBABILIDAD DIRECCIONAL
                </span>

                <span class="scale-number">
                    ABAJO {100-p:.1f}%
                    &nbsp; | &nbsp;
                    ARRIBA {p:.1f}%
                </span>

            </div>

            <div class="prob-track">
                <div
                    class="prob-marker"
                    style="left:{p}%;">
                </div>
            </div>

            <div class="scale-limits">
                <span>100% ABAJO</span>
                <span>50 / 50</span>
                <span>100% ARRIBA</span>
            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )


def tabla_metricas(
    datos,
):
    filas = ""

    for nombre, valor in datos:

        filas += f"""
        <tr>
            <td class="metric-name">
                {nombre}
            </td>

            <td class="metric-value">
                {valor}
            </td>
        </tr>
        """

    st.markdown(
        f"""
        <div class="card">
            <table class="metric-table">
                {filas}
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# CABECERA
# ============================================================

st.markdown(
    """
    <div class="top-title">
        ₿ BTC 15M PROFIT ENGINE
    </div>

    <div class="top-subtitle">
        Kalshi • CF Benchmarks BRTI • Coinbase • Kraken •
        CoinMarketCap • Order Flow • Microestructura
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# BOTON HISTORIAL
# ============================================================

col_reset, col_clock = st.columns(
    [1, 3]
)

with col_reset:

    if st.button(
        "🗑️ ELIMINAR HISTORIAL",
        use_container_width=True,
    ):
        eliminar_historial()

with col_clock:

    hora = datetime.now(
        LOCAL_TZ
    )

    st.caption(
        "Actualización automática cada 10 segundos • "
        + hora.strftime(
            "%m/%d/%Y %I:%M:%S %p"
        )
    )


# ============================================================
# ANALISIS LIVE
# ============================================================

analisis = None

mercado = None

try:
    mercado = (
        motor.elegir_mercado_actual()
    )

    if mercado is not None:

        analisis = motor.analizar_mercado(
            mercado
        )

except Exception as e:

    st.error(
        "No se pudo obtener el análisis live: "
        f"{e}"
    )


if analisis is None:

    st.warning(
        "No hay análisis disponible ahora mismo. "
        "Comprueba que los Secrets estén disponibles "
        "para la app y que exista un mercado BTC 15M abierto."
    )

    st.stop()


# ============================================================
# DECISION PRINCIPAL
# ============================================================

decision = analisis.get(
    "decision",
    "NO APOSTAR",
)

fuerza = analisis.get(
    "fuerza",
    "",
)

probabilidad = analisis.get(
    "probabilidad",
    0,
)

if decision == "ARRIBA":
    clase = "decision-up"
    icono = "🟢"

elif decision == "ABAJO":
    clase = "decision-down"
    icono = "🔴"

else:
    clase = "decision-no"
    icono = "⚪"


st.markdown(
    f"""
    <div class="{clase}">

        <div class="decision-label">
            DECISION ACTUAL
        </div>

        <div class="decision-value">
            {icono} {decision}
        </div>

        <div class="decision-info">
            Fuerza:
            <b>{fuerza}</b>
            &nbsp; • &nbsp;
            Probabilidad:
            <b>{probabilidad:.1f}%</b>
        </div>

    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# TARJETAS PRINCIPALES
# ============================================================

st.markdown(
    '<div class="section-title">Contrato actual</div>',
    unsafe_allow_html=True,
)

c1, c2, c3, c4, c5 = st.columns(
    5
)

with c1:
    tarjeta(
        "TARGET KALSHI",
        numero(
            analisis.get(
                "target"
            ),
            2,
            "$",
        ),
    )

with c2:
    tarjeta(
        "BTC CONSENSO",
        numero(
            analisis.get(
                "precio_consenso"
            ),
            2,
            "$",
        ),
    )

with c3:
    tarjeta(
        "TIEMPO RESTANTE",
        numero(
            analisis.get(
                "segundos_restantes"
            ),
            0,
            "",
            " s",
        ),
    )

with c4:
    tarjeta(
        "MINUTO CONTRATO",
        numero(
            analisis.get(
                "minuto_entrada"
            ),
            2,
        ),
    )

with c5:
    tarjeta(
        "SCORE TOTAL",
        numero(
            analisis.get(
                "score"
            ),
            2,
        ),
    )


# ============================================================
# PROBABILIDAD
# ============================================================

st.markdown(
    '<div class="section-title">Probabilidad y valor</div>',
    unsafe_allow_html=True,
)

escala_probabilidad(
    analisis.get(
        "probabilidad_arriba",
        50,
    )
)

p1, p2, p3, p4 = st.columns(
    4
)

with p1:
    tarjeta(
        "PROB. ARRIBA",
        numero(
            analisis.get(
                "probabilidad_arriba"
            ),
            1,
            "",
            "%",
        ),
    )

with p2:
    tarjeta(
        "PROB. ABAJO",
        numero(
            analisis.get(
                "probabilidad_abajo"
            ),
            1,
            "",
            "%",
        ),
    )

with p3:

    edge = analisis.get(
        "edge"
    )

    tarjeta(
        "EDGE",
        (
            numero(
                edge * 100,
                2,
                "",
                "%",
            )
            if edge is not None
            else "SIN EDGE"
        ),
    )

with p4:
    tarjeta(
        "PRECIO ENTRADA",
        (
            numero(
                analisis.get(
                    "precio_entrada"
                ),
                3,
                "$",
            )
            if analisis.get(
                "precio_entrada"
            ) is not None
            else "NO ENTRA"
        ),
    )


# ============================================================
# ESCALA SCORE
# ============================================================

escala(
    "SCORE TOTAL",
    analisis.get(
        "score",
        0,
    ),
    -100,
    100,
    "{:+.2f}",
)


# ============================================================
# TARGET
# ============================================================

st.markdown(
    '<div class="section-title">Distancia al Target</div>',
    unsafe_allow_html=True,
)

escala(
    "DISTANCIA BTC ↔ TARGET",
    analisis.get(
        "distancia_target_pct",
        0,
    ),
    -0.15,
    0.15,
    "{:+.4f}%",
)


# ============================================================
# FUENTES
# ============================================================

st.markdown(
    '<div class="section-title">Precios de todas las fuentes</div>',
    unsafe_allow_html=True,
)

f1, f2 = st.columns(
    2
)

with f1:

    tabla_metricas(
        [
            (
                "CF Benchmarks / BRTI",
                numero(
                    analisis.get(
                        "precio_cf_brti"
                    ),
                    2,
                    "$",
                ),
            ),
            (
                "Coinbase BTC-USD",
                numero(
                    analisis.get(
                        "precio_coinbase"
                    ),
                    2,
                    "$",
                ),
            ),
            (
                "Kraken XBTUSD",
                numero(
                    analisis.get(
                        "precio_kraken"
                    ),
                    2,
                    "$",
                ),
            ),
            (
                "CoinMarketCap",
                numero(
                    analisis.get(
                        "precio_coinmarketcap"
                    ),
                    2,
                    "$",
                ),
            ),
            (
                "Precio consenso",
                numero(
                    analisis.get(
                        "precio_consenso"
                    ),
                    2,
                    "$",
                ),
            ),
        ]
    )

with f2:

    tabla_metricas(
        [
            (
                "Kalshi YES ask",
                numero(
                    analisis.get(
                        "yes_ask"
                    ),
                    3,
                    "$",
                ),
            ),
            (
                "Kalshi NO ask",
                numero(
                    analisis.get(
                        "no_ask"
                    ),
                    3,
                    "$",
                ),
            ),
            (
                "Fuentes disponibles",
                str(
                    analisis.get(
                        "fuentes_disponibles"
                    )
                ),
            ),
            (
                "Lado contrato",
                str(
                    analisis.get(
                        "lado_contrato"
                    )
                    or "N/D"
                ),
            ),
            (
                "Ticker",
                str(
                    analisis.get(
                        "ticker"
                    )
                    or "N/D"
                ),
            ),
        ]
    )


# ============================================================
# TENDENCIA
# ============================================================

st.markdown(
    '<div class="section-title">Tendencia técnica</div>',
    unsafe_allow_html=True,
)

t1, t2 = st.columns(
    2
)

with t1:

    tabla_metricas(
        [
            (
                "EMA 9",
                numero(
                    analisis.get(
                        "ema9"
                    ),
                    2,
                    "$",
                ),
            ),
            (
                "EMA 21",
                numero(
                    analisis.get(
                        "ema21"
                    ),
                    2,
                    "$",
                ),
            ),
            (
                "EMA 50",
                numero(
                    analisis.get(
                        "ema50"
                    ),
                    2,
                    "$",
                ),
            ),
            (
                "MACD",
                numero(
                    analisis.get(
                        "macd"
                    ),
                    4,
                ),
            ),
            (
                "MACD Signal",
                numero(
                    analisis.get(
                        "macd_signal"
                    ),
                    4,
                ),
            ),
        ]
    )

with t2:

    escala(
        "RSI 14",
        analisis.get(
            "rsi14",
            50,
        ),
        0,
        100,
        "{:.2f}",
    )

    escala(
        "CMF 20",
        analisis.get(
            "cmf20",
            0,
        ),
        -1,
        1,
        "{:+.4f}",
    )


# ============================================================
# MOMENTUM
# ============================================================

st.markdown(
    '<div class="section-title">Momentum, velocidad y aceleración</div>',
    unsafe_allow_html=True,
)

m1, m2 = st.columns(
    2
)

with m1:

    tabla_metricas(
        [
            (
                "Momentum 1 minuto",
                numero(
                    analisis.get(
                        "momentum_1m",
                        0,
                    ) * 100,
                    4,
                    "",
                    "%",
                ),
            ),
            (
                "Momentum 3 minutos",
                numero(
                    analisis.get(
                        "momentum_3m",
                        0,
                    ) * 100,
                    4,
                    "",
                    "%",
                ),
            ),
            (
                "Momentum 5 minutos",
                numero(
                    analisis.get(
                        "momentum_5m",
                        0,
                    ) * 100,
                    4,
                    "",
                    "%",
                ),
            ),
            (
                "Momentum 10 minutos",
                numero(
                    analisis.get(
                        "momentum_10m",
                        0,
                    ) * 100,
                    4,
                    "",
                    "%",
                ),
            ),
        ]
    )

with m2:

    escala(
        "VELOCIDAD",
        analisis.get(
            "velocidad",
            0,
        ) * 100,
        -0.50,
        0.50,
        "{:+.5f}%",
    )

    escala(
        "ACELERACION",
        analisis.get(
            "aceleracion",
            0,
        ) * 100,
        -0.50,
        0.50,
        "{:+.5f}%",
    )


# ============================================================
# VOLATILIDAD / VOLUMEN
# ============================================================

st.markdown(
    '<div class="section-title">Volatilidad y volumen</div>',
    unsafe_allow_html=True,
)

v1, v2 = st.columns(
    2
)

with v1:

    tabla_metricas(
        [
            (
                "Volatilidad 20",
                numero(
                    analisis.get(
                        "volatilidad20",
                        0,
                    ) * 100,
                    5,
                    "",
                    "%",
                ),
            ),
            (
                "Volumen actual",
                numero(
                    analisis.get(
                        "volumen"
                    ),
                    4,
                    "",
                    " BTC",
                ),
            ),
            (
                "Volumen promedio 20",
                numero(
                    analisis.get(
                        "volumen_promedio20"
                    ),
                    4,
                    "",
                    " BTC",
                ),
            ),
        ]
    )

with v2:

    escala(
        "VOLUMEN RELATIVO",
        analisis.get(
            "volumen_relativo",
            1,
        ),
        0,
        3,
        "{:.2f}x",
    )


# ============================================================
# ORDER BOOK IMBALANCE
# ============================================================

st.markdown(
    '<div class="section-title">Order Book Imbalance — OBI</div>',
    unsafe_allow_html=True,
)

o1, o2 = st.columns(
    2
)

with o1:

    escala(
        "OBI COINBASE",
        analisis.get(
            "obi_coinbase",
            0,
        ),
        -1,
        1,
        "{:+.4f}",
    )

    escala(
        "OBI KRAKEN",
        analisis.get(
            "obi_kraken",
            0,
        ),
        -1,
        1,
        "{:+.4f}",
    )

with o2:

    escala(
        "OBI KALSHI",
        analisis.get(
            "obi_kalshi",
            0,
        ),
        -1,
        1,
        "{:+.4f}",
    )

    escala(
        "OBI PROMEDIO",
        analisis.get(
            "obi_promedio",
            0,
        ),
        -1,
        1,
        "{:+.4f}",
    )


# ============================================================
# ORDER FLOW
# ============================================================

st.markdown(
    '<div class="section-title">Trades agresivos / Order Flow</div>',
    unsafe_allow_html=True,
)

of_cb = (
    analisis.get(
        "orderflow_coinbase"
    )
    or {}
)

of_kr = (
    analisis.get(
        "orderflow_kraken"
    )
    or {}
)

of1, of2 = st.columns(
    2
)

with of1:

    escala(
        "ORDER FLOW COINBASE",
        of_cb.get(
            "imbalance",
            0,
        ),
        -1,
        1,
        "{:+.4f}",
    )

    tabla_metricas(
        [
            (
                "Compra agresiva Coinbase",
                numero(
                    of_cb.get(
                        "buy_volume"
                    ),
                    5,
                    "",
                    " BTC",
                ),
            ),
            (
                "Venta agresiva Coinbase",
                numero(
                    of_cb.get(
                        "sell_volume"
                    ),
                    5,
                    "",
                    " BTC",
                ),
            ),
            (
                "Trades usados Coinbase",
                str(
                    of_cb.get(
                        "trades",
                        0,
                    )
                ),
            ),
        ]
    )

with of2:

    escala(
        "ORDER FLOW KRAKEN",
        of_kr.get(
            "imbalance",
            0,
        ),
        -1,
        1,
        "{:+.4f}",
    )

    tabla_metricas(
        [
            (
                "Compra agresiva Kraken",
                numero(
                    of_kr.get(
                        "buy_volume"
                    ),
                    5,
                    "",
                    " BTC",
                ),
            ),
            (
                "Venta agresiva Kraken",
                numero(
                    of_kr.get(
                        "sell_volume"
                    ),
                    5,
                    "",
                    " BTC",
                ),
            ),
            (
                "Trades usados Kraken",
                str(
                    of_kr.get(
                        "trades",
                        0,
                    )
                ),
            ),
        ]
    )

escala(
    "ORDER FLOW PROMEDIO",
    analisis.get(
        "orderflow_promedio",
        0,
    ),
    -1,
    1,
    "{:+.4f}",
)


# ============================================================
# PROFUNDIDAD
# ============================================================

st.markdown(
    '<div class="section-title">Profundidad de mercado</div>',
    unsafe_allow_html=True,
)

prof_cb = (
    analisis.get(
        "profundidad_coinbase"
    )
    or {}
)

prof_kr = (
    analisis.get(
        "profundidad_kraken"
    )
    or {}
)

prof_ka = (
    analisis.get(
        "profundidad_kalshi"
    )
    or {}
)

d1, d2, d3 = st.columns(
    3
)

with d1:

    tarjeta(
        "COINBASE BID DEPTH",
        numero(
            prof_cb.get(
                "bid"
            ),
            4,
            "",
            " BTC",
        ),
    )

    tarjeta(
        "COINBASE ASK DEPTH",
        numero(
            prof_cb.get(
                "ask"
            ),
            4,
            "",
            " BTC",
        ),
    )

with d2:

    tarjeta(
        "KRAKEN BID DEPTH",
        numero(
            prof_kr.get(
                "bid"
            ),
            4,
            "",
            " BTC",
        ),
    )

    tarjeta(
        "KRAKEN ASK DEPTH",
        numero(
            prof_kr.get(
                "ask"
            ),
            4,
            "",
            " BTC",
        ),
    )

with d3:

    tarjeta(
        "KALSHI YES DEPTH",
        numero(
            prof_ka.get(
                "yes"
            ),
            2,
        ),
    )

    tarjeta(
        "KALSHI NO DEPTH",
        numero(
            prof_ka.get(
                "no"
            ),
            2,
        ),
    )


# ============================================================
# SPREAD
# ============================================================

st.markdown(
    '<div class="section-title">Spread</div>',
    unsafe_allow_html=True,
)

spread = analisis.get(
    "spread_coinbase"
)

if spread is not None:

    tarjeta(
        "COINBASE BID / ASK SPREAD",
        numero(
            spread * 100,
            5,
            "",
            "%",
        ),
    )

else:

    tarjeta(
        "COINBASE BID / ASK SPREAD",
        "N/D",
    )


# ============================================================
# SCORE POR FAMILIAS
# ============================================================

st.markdown(
    '<div class="section-title">Score por familias</div>',
    unsafe_allow_html=True,
)

familias = (
    analisis.get(
        "score_familias"
    )
    or {}
)

sf1, sf2 = st.columns(
    2
)

with sf1:

    escala(
        "TARGET",
        familias.get(
            "target",
            0,
        ),
        -18,
        18,
        "{:+.2f}",
    )

    escala(
        "TENDENCIA",
        familias.get(
            "tendencia",
            0,
        ),
        -14,
        14,
        "{:+.2f}",
    )

    escala(
        "MOMENTUM",
        familias.get(
            "momentum",
            0,
        ),
        -13,
        13,
        "{:+.2f}",
    )

with sf2:

    escala(
        "MICROESTRUCTURA",
        familias.get(
            "microestructura",
            0,
        ),
        -16,
        16,
        "{:+.2f}",
    )

    escala(
        "FLUJO DE CAPITAL",
        familias.get(
            "flujo_capital",
            0,
        ),
        -10,
        10,
        "{:+.2f}",
    )

    escala(
        "CONSENSO",
        familias.get(
            "consenso",
            0,
        ),
        -10,
        10,
        "{:+.2f}",
    )


# ============================================================
# CONSENSO FUENTES
# ============================================================

st.markdown(
    '<div class="section-title">Consenso de fuentes</div>',
    unsafe_allow_html=True,
)

consenso = (
    analisis.get(
        "consenso_fuentes"
    )
    or {}
)

cc1, cc2, cc3, cc4 = st.columns(
    4
)

with cc1:
    tarjeta(
        "FUENTES ARRIBA",
        str(
            consenso.get(
                "arriba",
                0,
            )
        ),
    )

with cc2:
    tarjeta(
        "FUENTES ABAJO",
        str(
            consenso.get(
                "abajo",
                0,
            )
        ),
    )

with cc3:
    tarjeta(
        "TOTAL FUENTES",
        str(
            consenso.get(
                "total",
                0,
            )
        ),
    )

with cc4:
    tarjeta(
        "RATIO CONSENSO",
        numero(
            consenso.get(
                "ratio",
                0,
            ),
            3,
        ),
    )


# ============================================================
# RAZONES DEL MOTOR
# ============================================================

st.markdown(
    '<div class="section-title">Razones de la decisión</div>',
    unsafe_allow_html=True,
)

razones = analisis.get(
    "razones",
    [],
)

if razones:

    for razon in razones:

        st.markdown(
            f"""
            <div class="reason">
                {razon}
            </div>
            """,
            unsafe_allow_html=True,
        )

else:

    st.caption(
        "No hay razones registradas."
    )


# ============================================================
# HISTORIAL / ESTADISTICAS
# ============================================================

st.markdown(
    '<div class="section-title">Historial y rendimiento</div>',
    unsafe_allow_html=True,
)

historial = cargar_historial()

operaciones = [
    x
    for x in historial
    if x.get(
        "decision"
    )
    in [
        "ARRIBA",
        "ABAJO",
    ]
]

resueltas = [
    x
    for x in operaciones
    if x.get(
        "evaluacion"
    )
    in [
        "ACIERTO",
        "FALLO",
    ]
]

aciertos = sum(
    1
    for x in resueltas
    if x.get(
        "evaluacion"
    )
    == "ACIERTO"
)

fallos = sum(
    1
    for x in resueltas
    if x.get(
        "evaluacion"
    )
    == "FALLO"
)

precision = 0.0

if resueltas:

    precision = (
        aciertos
        / len(
            resueltas
        )
    ) * 100

pnl = sum(
    float(
        x.get(
            "pnl_teorico_1_contrato"
        )
        or 0
    )
    for x in resueltas
)

h1, h2, h3, h4, h5 = st.columns(
    5
)

with h1:
    tarjeta(
        "OPERACIONES",
        str(
            len(
                operaciones
            )
        ),
    )

with h2:
    tarjeta(
        "ACIERTOS",
        str(
            aciertos
        ),
    )

with h3:
    tarjeta(
        "FALLOS",
        str(
            fallos
        ),
    )

with h4:
    tarjeta(
        "PRECISION",
        f"{precision:.2f}%",
    )

with h5:
    tarjeta(
        "P&L TEORICO",
        f"${pnl:+.4f}",
    )


# ============================================================
# TABLA HISTORIAL
# ============================================================

if historial:

    columnas = [
        "hora_local",
        "ticker",
        "decision",
        "fuerza",
        "probabilidad",
        "target",
        "precio_consenso",
        "precio_entrada",
        "edge",
        "minuto_entrada",
        "score",
        "resultado",
        "evaluacion",
        "pnl_teorico_1_contrato",
        "roi_teorico_pct",
    ]

    df = pd.DataFrame(
        historial
    )

    columnas_existentes = [
        x
        for x in columnas
        if x in df.columns
    ]

    df = df[
        columnas_existentes
    ]

    df = df.iloc[
        ::-1
    ]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "Todavía no hay historial guardado."
    )
