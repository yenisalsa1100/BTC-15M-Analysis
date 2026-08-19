import json
import os

import pandas as pd
import streamlit as st


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

AUTO_REFRESH_SEGUNDOS = 3


# ============================================================
# CSS
# ============================================================

st.html(
    """
<style>
:root {
    --bg0: #02050a;
    --bg1: #07101d;
    --panel: rgba(11, 18, 32, .94);
    --panel2: rgba(15, 23, 42, .92);
    --border: rgba(148, 163, 184, .16);
    --text: #f8fafc;
    --muted: #94a3b8;
    --up: #10b981;
    --down: #ef4444;
    --cyan: #38bdf8;
    --purple: #a855f7;
}

html, body {
    background: var(--bg0);
}

.stApp {
    background:
        radial-gradient(
            circle at 10% 0%,
            rgba(56,189,248,.14),
            transparent 27%
        ),
        radial-gradient(
            circle at 90% 0%,
            rgba(168,85,247,.14),
            transparent 28%
        ),
        linear-gradient(
            180deg,
            var(--bg0) 0%,
            var(--bg1) 48%,
            var(--bg0) 100%
        );
    color: var(--text);
}

.block-container {
    max-width: 1450px;
    padding-top: .75rem;
    padding-bottom: 4rem;
}

[data-testid="stHeader"] {
    background: rgba(2,5,10,.82);
}

[data-testid="stToolbar"] {
    right: 1rem;
}

.hero {
    padding: 10px 2px 14px 2px;
}

.hero-title {
    color: white;
    font-size: 2.15rem;
    line-height: 1;
    font-weight: 950;
    letter-spacing: -1.4px;
}

.hero-sub {
    color: var(--muted);
    margin-top: 10px;
    font-size: .86rem;
    line-height: 1.5;
}

.section {
    margin-top: 19px;
    margin-bottom: 9px;
    font-size: 1.06rem;
    font-weight: 850;
    color: #e2e8f0;
}

.card {
    background:
        linear-gradient(
            145deg,
            rgba(15,23,42,.98),
            rgba(5,10,20,.98)
        );
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 15px 15px 14px 15px;
    margin-bottom: 8px;
    box-shadow: 0 10px 28px rgba(0,0,0,.23);
    min-height: 92px;
}

.card-label {
    color: var(--muted);
    text-transform: uppercase;
    font-size: .67rem;
    letter-spacing: .8px;
    font-weight: 800;
}

.card-value {
    color: white;
    font-size: 1.38rem;
    line-height: 1.2;
    font-weight: 900;
    margin-top: 7px;
    overflow-wrap: anywhere;
}

.card-detail {
    color: #64748b;
    font-size: .69rem;
    margin-top: 5px;
}

.decision {
    border-radius: 20px;
    text-align: center;
    padding: 23px 14px;
    margin-top: 8px;
    margin-bottom: 9px;
    box-shadow: 0 15px 35px rgba(0,0,0,.28);
}

.decision-up {
    background:
        linear-gradient(
            135deg,
            rgba(16,185,129,.28),
            rgba(4,47,31,.88)
        );
    border: 1px solid rgba(16,185,129,.52);
}

.decision-down {
    background:
        linear-gradient(
            135deg,
            rgba(239,68,68,.27),
            rgba(69,10,10,.85)
        );
    border: 1px solid rgba(239,68,68,.50);
}

.decision-no {
    background:
        linear-gradient(
            135deg,
            rgba(100,116,139,.22),
            rgba(15,23,42,.94)
        );
    border: 1px solid rgba(148,163,184,.33);
}

.decision-small {
    color: #94a3b8;
    font-size: .72rem;
    letter-spacing: 1.5px;
    font-weight: 850;
}

.decision-big {
    color: white;
    font-size: 2.35rem;
    line-height: 1.1;
    font-weight: 950;
    margin-top: 7px;
    margin-bottom: 9px;
}

.decision-meta {
    color: #cbd5e1;
    font-size: .84rem;
}

.scale {
    background: var(--panel2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 13px 14px 11px 14px;
    margin-bottom: 8px;
}

.scale-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
}

.scale-name {
    color: #cbd5e1;
    font-size: .76rem;
    font-weight: 800;
}

.scale-value {
    color: white;
    font-size: .82rem;
    font-weight: 900;
    white-space: nowrap;
}

.scale-bar {
    height: 11px;
    border-radius: 999px;
    position: relative;
    overflow: visible;
    background:
        linear-gradient(
            90deg,
            #dc2626 0%,
            #f97316 24%,
            #475569 48%,
            #475569 52%,
            #22c55e 76%,
            #10b981 100%
        );
}

.scale-pointer {
    position: absolute;
    top: -4px;
    width: 4px;
    height: 19px;
    border-radius: 3px;
    background: white;
    box-shadow:
        0 0 6px rgba(255,255,255,.9),
        0 0 13px rgba(255,255,255,.45);
    transform: translateX(-2px);
}

.scale-foot {
    display: flex;
    justify-content: space-between;
    color: #64748b;
    font-size: .60rem;
    margin-top: 6px;
}

.prob-bar {
    height: 15px;
    border-radius: 999px;
    position: relative;
    background:
        linear-gradient(
            90deg,
            #ef4444 0%,
            #f97316 30%,
            #475569 50%,
            #22c55e 70%,
            #10b981 100%
        );
}

.prob-pointer {
    position: absolute;
    top: -4px;
    width: 5px;
    height: 23px;
    background: white;
    border-radius: 4px;
    transform: translateX(-2px);
    box-shadow:
        0 0 7px white,
        0 0 16px rgba(255,255,255,.5);
}

.metric-box {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 15px;
    padding: 7px 13px;
    margin-bottom: 8px;
}

.metric-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    padding: 9px 0;
    border-bottom: 1px solid rgba(148,163,184,.08);
}

.metric-row:last-child {
    border-bottom: none;
}

.metric-key {
    color: #94a3b8;
    font-size: .76rem;
}

.metric-val {
    color: #f8fafc;
    font-size: .78rem;
    font-weight: 850;
    text-align: right;
    overflow-wrap: anywhere;
}

.reason {
    background: rgba(15,23,42,.86);
    border: 1px solid rgba(148,163,184,.11);
    border-left: 3px solid var(--cyan);
    color: #cbd5e1;
    border-radius: 8px;
    padding: 9px 10px;
    font-size: .77rem;
    margin-bottom: 5px;
}

.good {
    color: #34d399;
}

.bad {
    color: #fb7185;
}

.neutral {
    color: #cbd5e1;
}

.live {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: #34d399;
    font-size: .72rem;
    font-weight: 850;
}

.live-dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: #10b981;
    box-shadow: 0 0 10px rgba(16,185,129,.9);
}

div.stButton > button {
    border-radius: 12px;
    min-height: 45px;
    width: 100%;
    font-weight: 850;
}

[data-testid="stDataFrame"] {
    border-radius: 14px;
    overflow: hidden;
}

@media (max-width: 700px) {

    .block-container {
        padding-left: .72rem;
        padding-right: .72rem;
        padding-top: .45rem;
    }

    .hero-title {
        font-size: 1.75rem;
    }

    .hero-sub {
        font-size: .78rem;
    }

    .decision-big {
        font-size: 2rem;
    }

    .decision {
        padding: 20px 10px;
    }

    .card {
        min-height: 80px;
        padding: 13px;
    }

    .card-value {
        font-size: 1.22rem;
    }

    .scale-top {
        align-items: flex-start;
    }

    .scale-name {
        max-width: 62%;
    }

    .metric-key,
    .metric-val {
        font-size: .72rem;
    }

}
</style>
"""
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

    except json.JSONDecodeError:

        # El motor puede estar justo actualizando
        # el archivo. En el siguiente refresh
        # se vuelve a intentar.
        return []

    except Exception:
        return []

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

        st.rerun()

    except Exception as e:

        st.error(
            f"Error eliminando historial: {e}"
        )


def seccion(texto):

    st.html(
        f'<div class="section">{texto}</div>'
    )


def tarjeta(
    titulo,
    valor,
    detalle="",
):

    detalle_html = ""

    if detalle:
        detalle_html = (
            f'<div class="card-detail">'
            f'{detalle}'
            f'</div>'
        )

    st.html(
        f'''
        <div class="card">
            <div class="card-label">{titulo}</div>
            <div class="card-value">{valor}</div>
            {detalle_html}
        </div>
        '''
    )


def tabla_metricas(datos):

    filas = ""

    for nombre, valor in datos:

        filas += (
            '<div class="metric-row">'
            f'<div class="metric-key">{nombre}</div>'
            f'<div class="metric-val">{valor}</div>'
            '</div>'
        )

    st.html(
        f'<div class="metric-box">{filas}</div>'
    )


def escala(
    nombre,
    valor,
    minimo,
    maximo,
    formato="{:.3f}",
):

    try:
        n = float(valor)

    except Exception:
        n = 0.0

    if maximo == minimo:
        pos = 50.0

    else:
        pos = (
            (
                n - minimo
            )
            /
            (
                maximo - minimo
            )
        ) * 100.0

    pos = max(
        0.0,
        min(
            100.0,
            pos,
        ),
    )

    try:
        texto = formato.format(n)

    except Exception:
        texto = str(n)

    st.html(
        f'''
        <div class="scale">

            <div class="scale-top">
                <div class="scale-name">{nombre}</div>
                <div class="scale-value">{texto}</div>
            </div>

            <div class="scale-bar">
                <div
                    class="scale-pointer"
                    style="left:{pos:.2f}%;">
                </div>
            </div>

            <div class="scale-foot">
                <span>{minimo}</span>
                <span>NEUTRO</span>
                <span>{maximo}</span>
            </div>

        </div>
        '''
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
        0.0,
        min(
            100.0,
            p,
        ),
    )

    abajo = (
        100.0
        - p
    )

    st.html(
        f'''
        <div class="scale">

            <div class="scale-top">
                <div class="scale-name">
                    PROBABILIDAD DIRECCIONAL
                </div>

                <div class="scale-value">
                    ABAJO {abajo:.1f}% · ARRIBA {p:.1f}%
                </div>
            </div>

            <div class="prob-bar">
                <div
                    class="prob-pointer"
                    style="left:{p:.2f}%;">
                </div>
            </div>

            <div class="scale-foot">
                <span>ABAJO</span>
                <span>50 / 50</span>
                <span>ARRIBA</span>
            </div>

        </div>
        '''
    )


# ============================================================
# CABECERA FIJA
# ============================================================

st.html(
    '''
    <div class="hero">
        <div class="hero-title">
            ₿ BTC 15M PROFIT ENGINE
        </div>

        <div class="hero-sub">
            Kalshi · CF Benchmarks BRTI · Coinbase · Kraken ·
            CoinMarketCap · Order Flow · Microestructura
        </div>
    </div>
    '''
)


st.html(
    f'''
    <div class="live">
        <span class="live-dot"></span>
        ACTUALIZACIÓN AUTOMÁTICA CADA
        {AUTO_REFRESH_SEGUNDOS} SEGUNDOS
    </div>
    '''
)


# ============================================================
# DASHBOARD EN VIVO
#
# IMPORTANTE:
# - NO EJECUTA motor_btc.py
# - SOLO LEE historial_btc_15m.json
# - SE VUELVE A EJECUTAR CADA 3 SEGUNDOS
# ============================================================

@st.fragment(
    run_every=f"{AUTO_REFRESH_SEGUNDOS}s"
)
def dashboard_en_vivo():

    # ========================================================
    # CARGAR ULTIMO HISTORIAL DISPONIBLE
    # ========================================================

    historial = cargar_historial()

    analisis = None

    if historial:
        analisis = historial[-1]


    # ========================================================
    # BOTON + ESTADO
    # ========================================================

    b1, b2 = st.columns(
        [1.15, 1.85]
    )

    with b1:

        if st.button(
            "🗑️ ELIMINAR HISTORIAL",
            use_container_width=True,
            key="eliminar_historial_btn",
        ):
            eliminar_historial()


    with b2:

        if analisis is not None:

            hora_motor = (
                analisis.get(
                    "hora_local"
                )
                or analisis.get(
                    "timestamp"
                )
                or "N/D"
            )

            st.caption(
                "Última actualización del motor: "
                + str(
                    hora_motor
                )
            )

        else:

            st.caption(
                "Esperando datos del motor."
            )


    # ========================================================
    # VERIFICAR ANALISIS
    # ========================================================

    if analisis is None:

        st.warning(
            "El motor todavía no ha guardado "
            "ningún análisis."
        )

        return


    # ========================================================
    # DECISION
    # ========================================================

    decision = analisis.get(
        "decision",
        "NO APOSTAR",
    )

    fuerza = analisis.get(
        "fuerza",
        "DEBIL",
    )

    try:
        probabilidad = float(
            analisis.get(
                "probabilidad",
                0,
            )
            or 0
        )

    except Exception:
        probabilidad = 0.0


    if decision == "ARRIBA":

        clase = (
            "decision decision-up"
        )

        icono = "▲"

    elif decision == "ABAJO":

        clase = (
            "decision decision-down"
        )

        icono = "▼"

    else:

        clase = (
            "decision decision-no"
        )

        icono = "●"


    st.html(
        f'''
        <div class="{clase}">

            <div class="decision-small">
                ULTIMA DECISION DEL MOTOR
            </div>

            <div class="decision-big">
                {icono} {decision}
            </div>

            <div class="decision-meta">
                FUERZA <b>{fuerza}</b>
                &nbsp;&nbsp;·&nbsp;&nbsp;
                PROBABILIDAD <b>{probabilidad:.1f}%</b>
            </div>

        </div>
        '''
    )


    # ========================================================
    # CONTRATO
    # ========================================================

    seccion(
        "Contrato"
    )

    c1, c2 = st.columns(2)

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


    c3, c4 = st.columns(2)

    with c3:

        tarjeta(
            "TIEMPO RESTANTE AL ANALIZAR",
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
            "MINUTO DE ENTRADA",
            numero(
                analisis.get(
                    "minuto_entrada"
                ),
                2,
            ),
        )


    tarjeta(
        "SCORE TOTAL",
        numero(
            analisis.get(
                "score"
            ),
            2,
        ),
    )


    # ========================================================
    # PROBABILIDAD
    # ========================================================

    seccion(
        "Probabilidad y valor"
    )

    escala_probabilidad(
        analisis.get(
            "probabilidad_arriba",
            50,
        )
    )

    p1, p2 = st.columns(2)

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


    edge = analisis.get(
        "edge"
    )

    p3, p4 = st.columns(2)

    with p3:

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

        precio_entrada = analisis.get(
            "precio_entrada"
        )

        tarjeta(
            "PRECIO ENTRADA",
            (
                numero(
                    precio_entrada,
                    3,
                    "$",
                )
                if precio_entrada is not None
                else "NO ENTRA"
            ),
        )


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


    # ========================================================
    # TARGET
    # ========================================================

    seccion(
        "Distancia al Target"
    )

    try:
        dist_target = float(
            analisis.get(
                "distancia_target_pct",
                0,
            )
            or 0
        )

    except Exception:
        dist_target = 0.0

    limite_target = max(
        0.15,
        abs(
            dist_target
        ) * 1.20,
    )

    escala(
        "BTC ↔ TARGET",
        dist_target,
        -limite_target,
        limite_target,
        "{:+.4f}%",
    )


    # ========================================================
    # FUENTES
    # ========================================================

    seccion(
        "Precios de fuentes"
    )

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
                        "fuentes_disponibles",
                        "N/D",
                    )
                ),
            ),
            (
                "Ticker",
                str(
                    analisis.get(
                        "ticker",
                        "N/D",
                    )
                ),
            ),
        ]
    )


    # ========================================================
    # TENDENCIA
    # ========================================================

    seccion(
        "Tendencia técnica"
    )

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


    # ========================================================
    # MOMENTUM
    # ========================================================

    seccion(
        "Momentum"
    )

    tabla_metricas(
        [
            (
                "Momentum 1 minuto",
                numero(
                    (
                        analisis.get(
                            "momentum_1m",
                            0,
                        )
                        or 0
                    ) * 100,
                    4,
                    "",
                    "%",
                ),
            ),
            (
                "Momentum 3 minutos",
                numero(
                    (
                        analisis.get(
                            "momentum_3m",
                            0,
                        )
                        or 0
                    ) * 100,
                    4,
                    "",
                    "%",
                ),
            ),
            (
                "Momentum 5 minutos",
                numero(
                    (
                        analisis.get(
                            "momentum_5m",
                            0,
                        )
                        or 0
                    ) * 100,
                    4,
                    "",
                    "%",
                ),
            ),
            (
                "Momentum 10 minutos",
                numero(
                    (
                        analisis.get(
                            "momentum_10m",
                            0,
                        )
                        or 0
                    ) * 100,
                    4,
                    "",
                    "%",
                ),
            ),
        ]
    )


    escala(
        "VELOCIDAD",
        (
            analisis.get(
                "velocidad",
                0,
            )
            or 0
        ) * 100,
        -0.50,
        0.50,
        "{:+.5f}%",
    )


    escala(
        "ACELERACION",
        (
            analisis.get(
                "aceleracion",
                0,
            )
            or 0
        ) * 100,
        -0.50,
        0.50,
        "{:+.5f}%",
    )


    # ========================================================
    # VOLATILIDAD / VOLUMEN
    # ========================================================

    seccion(
        "Volatilidad y volumen"
    )

    tabla_metricas(
        [
            (
                "Volatilidad 20",
                numero(
                    (
                        analisis.get(
                            "volatilidad20",
                            0,
                        )
                        or 0
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


    # ========================================================
    # OBI
    # ========================================================

    seccion(
        "Order Book Imbalance"
    )

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


    # ========================================================
    # ORDER FLOW
    # ========================================================

    seccion(
        "Trades agresivos / Order Flow"
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
                "Trades Coinbase",
                str(
                    of_cb.get(
                        "trades",
                        0,
                    )
                ),
            ),
        ]
    )


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
                "Trades Kraken",
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


    # ========================================================
    # PROFUNDIDAD
    # ========================================================

    seccion(
        "Profundidad de mercado"
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


    tabla_metricas(
        [
            (
                "Coinbase BID depth",
                numero(
                    prof_cb.get(
                        "bid"
                    ),
                    4,
                    "",
                    " BTC",
                ),
            ),
            (
                "Coinbase ASK depth",
                numero(
                    prof_cb.get(
                        "ask"
                    ),
                    4,
                    "",
                    " BTC",
                ),
            ),
            (
                "Kraken BID depth",
                numero(
                    prof_kr.get(
                        "bid"
                    ),
                    4,
                    "",
                    " BTC",
                ),
            ),
            (
                "Kraken ASK depth",
                numero(
                    prof_kr.get(
                        "ask"
                    ),
                    4,
                    "",
                    " BTC",
                ),
            ),
            (
                "Kalshi YES depth",
                numero(
                    prof_ka.get(
                        "yes"
                    ),
                    2,
                ),
            ),
            (
                "Kalshi NO depth",
                numero(
                    prof_ka.get(
                        "no"
                    ),
                    2,
                ),
            ),
        ]
    )


    # ========================================================
    # SPREAD
    # ========================================================

    seccion(
        "Spread"
    )

    spread = analisis.get(
        "spread_coinbase"
    )

    tarjeta(
        "COINBASE BID / ASK SPREAD",
        (
            numero(
                spread * 100,
                5,
                "",
                "%",
            )
            if spread is not None
            else "N/D"
        ),
    )


    # ========================================================
    # SCORE FAMILIAS
    # ========================================================

    seccion(
        "Score por familias"
    )

    familias = (
        analisis.get(
            "score_familias"
        )
        or {}
    )


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
        "FLUJO CAPITAL",
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


    # ========================================================
    # CONSENSO
    # ========================================================

    seccion(
        "Consenso de fuentes"
    )

    consenso = (
        analisis.get(
            "consenso_fuentes"
        )
        or {}
    )


    cc1, cc2 = st.columns(2)

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


    cc3, cc4 = st.columns(2)

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


    # ========================================================
    # RAZONES
    # ========================================================

    seccion(
        "Razones de la decisión"
    )

    razones = (
        analisis.get(
            "razones"
        )
        or []
    )

    if razones:

        for razon in razones:

            st.html(
                f'<div class="reason">{razon}</div>'
            )

    else:

        st.caption(
            "No hay razones registradas."
        )


    # ========================================================
    # HISTORIAL / RENDIMIENTO
    # ========================================================

    seccion(
        "Historial y rendimiento"
    )

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
        ) * 100.0


    pnl = sum(
        float(
            x.get(
                "pnl_teorico_1_contrato"
            )
            or 0
        )
        for x in resueltas
    )


    r1, r2 = st.columns(2)

    with r1:

        tarjeta(
            "OPERACIONES",
            str(
                len(
                    operaciones
                )
            ),
        )

    with r2:

        tarjeta(
            "PRECISION",
            f"{precision:.2f}%",
        )


    r3, r4, r5 = st.columns(3)

    with r3:

        tarjeta(
            "ACIERTOS",
            str(
                aciertos
            ),
        )

    with r4:

        tarjeta(
            "FALLOS",
            str(
                fallos
            ),
        )

    with r5:

        tarjeta(
            "P&L",
            f"${pnl:+.4f}",
        )


    # ========================================================
    # HISTORIAL
    # ========================================================

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
            columna
            for columna in columnas
            if columna in df.columns
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


# ============================================================
# INICIAR DASHBOARD EN VIVO
# ============================================================

dashboard_en_vivo()
