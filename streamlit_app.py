import json
import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests
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

HISTORIAL_URL = (
    "https://raw.githubusercontent.com/yenisalsa1100/BTC-15M-Analysis/main/"
    "historial_btc_15m_v2.json"
)

RESET_FILE = "historial_btc_15m_v2.json"

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
}
</style>
"""
)


# ============================================================
# UTILIDADES
# ============================================================

def numero(valor, decimales=2, prefijo="", sufijo=""):
    if valor is None:
        return "N/D"
    try:
        return f"{prefijo}{float(valor):,.{decimales}f}{sufijo}"
    except Exception:
        return str(valor)


def timestamp_registro(registro):
    if not isinstance(registro, dict):
        return 0.0

    valores = [
        registro.get("timestamp"),
        registro.get("hora_local"),
        registro.get("resultado_actualizado"),
    ]

    for valor in valores:
        if not valor:
            continue
        try:
            texto = str(valor).strip()
            fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            return fecha.timestamp()
        except Exception:
            continue

    return 0.0


def cargar_reset():
    if not os.path.exists(RESET_FILE):
        return 0.0
    try:
        with open(RESET_FILE, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return float(datos.get("reset_timestamp", 0.0))
    except Exception:
        return 0.0


def guardar_reset(reset_timestamp):
    temporal = RESET_FILE + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump({"reset_timestamp": float(reset_timestamp)}, f, ensure_ascii=False, indent=2)
    os.replace(temporal, RESET_FILE)


def cargar_historial():
    try:
        respuesta = requests.get(
            HISTORIAL_URL,
            timeout=5,
            headers={
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        respuesta.raise_for_status()
        
        try:
            datos = respuesta.json()
        except json.JSONDecodeError:
            datos = []
            for linea in respuesta.text.splitlines():
                linea = linea.strip()
                if linea:
                    try:
                        datos.append(json.loads(linea))
                    except Exception:
                        pass

        if not isinstance(datos, list):
            return []

        reset_timestamp = cargar_reset()
        if reset_timestamp <= 0:
            return datos

        nuevos = []
        for registro in datos:
            registro_timestamp = timestamp_registro(registro)
            if registro_timestamp > reset_timestamp:
                nuevos.append(registro)
        return nuevos
    except Exception as e:
        st.warning(f"No se pudo conectar con GitHub: {e}")
        return []


def eliminar_historial():
    try:
        ahora_reset = time.time()
        guardar_reset(ahora_reset)
        st.session_state["historial_eliminado"] = True
        st.session_state["reset_timestamp"] = ahora_reset
        st.toast("Historial eliminado.")
        return True
    except Exception as e:
        st.error(f"Error eliminando historial: {e}")
        return False


def seccion(texto):
    st.html(f'<div class="section">{texto}</div>')


def tarjeta(titulo, valor, detalle=""):
    detalle_html = f'<div class="card-detail">{detalle}</div>' if detalle else ""
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
    st.html(f'<div class="metric-box">{filas}</div>')


def escala(nombre, valor, minimo, maximo, formato="{:.3f}"):
    try:
        n = float(valor)
    except Exception:
        n = 0.0

    if maximo == minimo:
        pos = 50.0
    else:
        pos = ((n - minimo) / (maximo - minimo)) * 100.0

    pos = max(0.0, min(100.0, pos))

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
                <div class="scale-pointer" style="left:{pos:.2f}%;"></div>
            </div>
            <div class="scale-foot">
                <span>{minimo}</span>
                <span>NEUTRO</span>
                <span>{maximo}</span>
            </div>
        </div>
        '''
    )


def escala_probabilidad(prob_arriba):
    try:
        p = float(prob_arriba)
    except Exception:
        p = 50.0

    p = max(0.0, min(100.0, p))
    abajo = 100.0 - p

    st.html(
        f'''
        <div class="scale">
            <div class="scale-top">
                <div class="scale-name">PROBABILIDAD DIRECCIONAL</div>
                <div class="scale-value">ABAJO {abajo:.1f}% · ARRIBA {p:.1f}%</div>
            </div>
            <div class="prob-bar">
                <div class="prob-pointer" style="left:{p:.2f}%;"></div>
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
        <div class="hero-title">₿ BTC 15M PROFIT ENGINE V2 PRO</div>
        <div class="hero-sub">
            Kalshi · CF Benchmarks BRTI · Coinbase · Kraken ·
            CoinMarketCap · Bitstamp · Mempool ·
            Order Flow · Microestructura
        </div>
    </div>
    '''
)

st.html(
    f'''
    <div class="live">
        <span class="live-dot"></span>
        ACTUALIZACIÓN AUTOMÁTICA CADA {AUTO_REFRESH_SEGUNDOS} SEGUNDOS
    </div>
    '''
)


# ============================================================
# DASHBOARD EN VIVO
# ============================================================

@st.fragment(run_every=f"{AUTO_REFRESH_SEGUNDOS}s")
def dashboard_en_vivo():
    historial = cargar_historial()
    analisis = historial[-1] if historial else st.session_state.get("ultimo_analisis")

    if historial:
        st.session_state["ultimo_analisis"] = analisis

    b1, b2 = st.columns([1.15, 1.85])

    with b1:
        if st.button("🗑️ ELIMINAR HISTORIAL", use_container_width=True, key="eliminar_historial_btn"):
            if eliminar_historial():
                historial = []

    with b2:
        if analisis is not None:
            hora_motor = analisis.get("hora_local") or analisis.get("timestamp") or "N/D"
            st.caption("Última actualización del motor: " + str(hora_motor))
        else:
            st.caption("Esperando datos del motor.")

    if analisis is None:
        st.info("Esperando el primer análisis del motor.")
        return

    # Decision
    decision = analisis.get("decision", "NO APOSTAR")
    fuerza = analisis.get("fuerza", "DEBIL")
    try:
        probabilidad = float(analisis.get("probabilidad", 0) or 0)
    except Exception:
        probabilidad = 0.0

    if decision == "ARRIBA":
        clase = "decision decision-up"
        icono = "▲"
    elif decision == "ABAJO":
        clase = "decision decision-down"
        icono = "▼"
    else:
        clase = "decision decision-no"
        icono = "●"

    st.html(
        f'''
        <div class="{clase}">
            <div class="decision-small">ULTIMA DECISION DEL MOTOR</div>
            <div class="decision-big">{icono} {decision}</div>
            <div class="decision-meta">
                FUERZA <b>{fuerza}</b> &nbsp;&nbsp;·&nbsp;&nbsp; PROBABILIDAD <b>{probabilidad:.1f}%</b>
            </div>
        </div>
        '''
    )

    # Contrato
    seccion("Contrato")
    c1, c2 = st.columns(2)
    with c1:
        tarjeta("TARGET KALSHI", numero(analisis.get("target"), 2, "$"))
    with c2:
        tarjeta("BTC CONSENSO", numero(analisis.get("precio_consenso"), 2, "$"))

    c3, c4 = st.columns(2)
    with c3:
        tarjeta("TIEMPO RESTANTE", numero(analisis.get("segundos_restantes"), 0, "", " s"))
    with c4:
        tarjeta("MINUTO DE ENTRADA", numero(analisis.get("minuto_entrada"), 2))

    tarjeta("SCORE TOTAL", numero(analisis.get("score"), 2))

    # Probabilidad y valor
    seccion("Probabilidad y valor")
    escala_probabilidad(analisis.get("probabilidad_arriba", 50))

    p1, p2 = st.columns(2)
    with p1:
        tarjeta("PROB. ARRIBA", numero(analisis.get("probabilidad_arriba"), 1, "", "%"))
    with p2:
        tarjeta("PROB. ABAJO", numero(analisis.get("probabilidad_abajo"), 1, "", "%"))

    edge = analisis.get("edge")
    p3, p4 = st.columns(2)
    with p3:
        tarjeta("EDGE", numero(edge * 100, 2, "", "%") if edge is not None else "SIN EDGE")
    with p4:
        precio_entrada = analisis.get("precio_entrada")
        tarjeta("PRECIO ENTRADA", numero(precio_entrada, 3, "$") if precio_entrada is not None else "NO ENTRA")

    escala("SCORE TOTAL", analisis.get("score", 0), -100, 100, "{:+.2f}")

    # Fuentes
    seccion("Precios de fuentes")
    tabla_metricas([
        ("CF Benchmarks / BRTI", numero(analisis.get("precio_cf_brti"), 2, "$")),
        ("Coinbase BTC-USD", numero(analisis.get("precio_coinbase"), 2, "$")),
        ("Kraken XBTUSD", numero(analisis.get("precio_kraken"), 2, "$")),
        ("CoinMarketCap", numero(analisis.get("precio_coinmarketcap"), 2, "$")),
        ("Bitstamp BTCUSD", numero(analisis.get("precio_bitstamp"), 2, "$")),
        ("Precio consenso", numero(analisis.get("precio_consenso"), 2, "$")),
    ])

    # Razones
    seccion("Razones de la decisión")
    razones = analisis.get("razones") or []
    if razones:
        for razon in razones:
            st.html(f'<div class="reason">{razon}</div>')
    else:
        st.caption("No hay razones registradas.")

    # Historial y rendimiento
    seccion("Historial y rendimiento")
    if historial:
        df = pd.DataFrame(historial)
        
        # Filtrar operaciones reales para calcular estadísticas de efectividad (excluyendo NO APOSTAR)
        df_operados = df[df["decision"] != "NO APOSTAR"].copy()
        
        if not df_operados.empty and "evaluacion" in df_operados.columns:
            total_operados = len(df_operados)
            ganadas = len(df_operados[df_operados["evaluacion"].astype(str).str.upper() == "GANADA"])
            perdidas = len(df_operados[df_operados["evaluacion"].astype(str).str.upper() == "PERDIDA"])
            win_rate = (ganadas / total_operados * 100) if total_operados > 0 else 0
            
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                tarjeta("OPERACIONES", str(total_operados))
            with m2:
                tarjeta("GANADAS", str(ganadas))
            with m3:
                tarjeta("PERDIDAS", str(perdidas))
            with m4:
                tarjeta("EFECTIVIDAD", f"{win_rate:.1f}%")

        # Limpiar evaluaciones en filas donde no se apostó para que no muestren fallos o aciertos teóricos
        if "decision" in df.columns:
            mask_no_apostar = df["decision"].astype(str).str.upper() == "NO APOSTAR"
            for col in ["evaluacion", "resultado", "pnl_teorico_total", "roi_teorico_pct"]:
                if col in df.columns:
                    df.loc[mask_no_apostar, col] = "-"

        columnas = [
            "hora_local", "ticker", "decision", "fuerza", "probabilidad",
            "target", "precio_consenso", "precio_entrada", "edge", "minuto_entrada",
            "score", "resultado", "evaluacion", "pnl_teorico_total", "roi_teorico_pct"
        ]
        columnas_existentes = [col for col in columnas if col in df.columns]
        df = df[columnas_existentes].iloc[::-1]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Historial vacío.")


# ============================================================
# INICIAR DASHBOARD EN VIVO
# ============================================================
dashboard_en_vivo()
