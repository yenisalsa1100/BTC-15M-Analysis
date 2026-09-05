import html
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

# Debe ser distinto al historial real. Este archivo solo recuerda desde
# que momento el usuario oculto las operaciones anteriores en la pantalla.
RESET_FILE = "reset_historial_btc_15m_v2.json"

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
        radial-gradient(circle at 10% 0%, rgba(56,189,248,.14), transparent 27%),
        radial-gradient(circle at 90% 0%, rgba(168,85,247,.14), transparent 28%),
        linear-gradient(180deg, var(--bg0) 0%, var(--bg1) 48%, var(--bg0) 100%);
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
    background: linear-gradient(145deg, rgba(15,23,42,.98), rgba(5,10,20,.98));
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
    background: linear-gradient(135deg, rgba(16,185,129,.28), rgba(4,47,31,.88));
    border: 1px solid rgba(16,185,129,.52);
}

.decision-down {
    background: linear-gradient(135deg, rgba(239,68,68,.27), rgba(69,10,10,.85));
    border: 1px solid rgba(239,68,68,.50);
}

.decision-no {
    background: linear-gradient(135deg, rgba(100,116,139,.22), rgba(15,23,42,.94));
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
    background: linear-gradient(
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
    box-shadow: 0 0 6px rgba(255,255,255,.9), 0 0 13px rgba(255,255,255,.45);
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
    background: linear-gradient(
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
    box-shadow: 0 0 7px white, 0 0 16px rgba(255,255,255,.5);
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


def como_dict(valor):
    return valor if isinstance(valor, dict) else {}


def timestamp_registro(registro):
    if not isinstance(registro, dict):
        return 0.0

    valores = [
        registro.get("timestamp"),
        registro.get("timestamp_local"),
        registro.get("hora_local"),
        registro.get("resultado_actualizado_en"),
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
        with open(RESET_FILE, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return float(datos.get("reset_timestamp", 0.0))
    except Exception:
        return 0.0


def guardar_reset(reset_timestamp):
    temporal = RESET_FILE + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(
            {"reset_timestamp": float(reset_timestamp)},
            archivo,
            ensure_ascii=False,
            indent=2,
        )
    os.replace(temporal, RESET_FILE)


def cargar_historial():
    try:
        respuesta = requests.get(
            HISTORIAL_URL,
            params={"actualizacion": time.time_ns()},
            timeout=5,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
        respuesta.raise_for_status()

        try:
            datos = respuesta.json()
        except json.JSONDecodeError:
            datos = []
            for linea in respuesta.text.splitlines():
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    datos.append(json.loads(linea))
                except Exception:
                    pass

        if not isinstance(datos, list):
            return []

        reset_timestamp = cargar_reset()
        if reset_timestamp <= 0:
            return datos

        return [
            registro
            for registro in datos
            if timestamp_registro(registro) > reset_timestamp
        ]
    except Exception as exc:
        st.warning(f"No se pudo conectar con GitHub: {exc}")
        return []


def eliminar_historial():
    try:
        ahora_reset = time.time()
        guardar_reset(ahora_reset)
        st.session_state["historial_eliminado"] = True
        st.session_state["reset_timestamp"] = ahora_reset
        st.session_state.pop("ultimo_analisis", None)
        st.toast("Historial eliminado.")
        return True
    except Exception as exc:
        st.error(f"Error eliminando historial: {exc}")
        return False


def fuentes_del_analisis(analisis):
    """Acepta el formato nuevo y conserva compatibilidad con el anterior."""
    calidad = como_dict(analisis.get("calidad_consenso"))
    salud = calidad.get("salud")
    resultado = {}
    if isinstance(salud, list):
        for fuente in salud:
            if not isinstance(fuente, dict):
                continue
            nombre = str(fuente.get("nombre", "")).upper()
            if nombre:
                resultado[nombre] = fuente.get("precio")

    compatibilidad = {
        "CF_BRTI": analisis.get("precio_cf_brti"),
        "COINBASE": analisis.get("precio_coinbase"),
        "KRAKEN": analisis.get("precio_kraken"),
        "CMC": analisis.get("precio_coinmarketcap"),
        "BITSTAMP": analisis.get("precio_bitstamp"),
    }
    for nombre, precio in compatibilidad.items():
        if resultado.get(nombre) is None and precio is not None:
            resultado[nombre] = precio
    return resultado


def seccion(texto):
    st.html(f'<div class="section">{html.escape(str(texto))}</div>')


def tarjeta(titulo, valor, detalle=""):
    titulo = html.escape(str(titulo))
    valor = html.escape(str(valor))
    detalle = html.escape(str(detalle))
    detalle_html = f'<div class="card-detail">{detalle}</div>' if detalle else ""
    st.html(
        f"""
        <div class="card">
            <div class="card-label">{titulo}</div>
            <div class="card-value">{valor}</div>
            {detalle_html}
        </div>
        """
    )


def tabla_metricas(datos):
    filas = ""
    for nombre, valor in datos:
        filas += (
            '<div class="metric-row">'
            f'<div class="metric-key">{html.escape(str(nombre))}</div>'
            f'<div class="metric-val">{html.escape(str(valor))}</div>'
            "</div>"
        )
    st.html(f'<div class="metric-box">{filas}</div>')


def escala(nombre, valor, minimo, maximo, formato="{:.3f}"):
    try:
        n = float(valor)
    except Exception:
        n = 0.0

    pos = 50.0 if maximo == minimo else (n - minimo) / (maximo - minimo) * 100.0
    pos = max(0.0, min(100.0, pos))

    try:
        texto = formato.format(n)
    except Exception:
        texto = str(n)

    st.html(
        f"""
        <div class="scale">
            <div class="scale-top">
                <div class="scale-name">{html.escape(str(nombre))}</div>
                <div class="scale-value">{html.escape(texto)}</div>
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
        """
    )


def escala_probabilidad(prob_arriba):
    try:
        prob = float(prob_arriba)
    except Exception:
        prob = 50.0

    prob = max(0.0, min(100.0, prob))
    abajo = 100.0 - prob

    st.html(
        f"""
        <div class="scale">
            <div class="scale-top">
                <div class="scale-name">PROBABILIDAD DIRECCIONAL</div>
                <div class="scale-value">ABAJO {abajo:.1f}% · ARRIBA {prob:.1f}%</div>
            </div>
            <div class="prob-bar">
                <div class="prob-pointer" style="left:{prob:.2f}%;"></div>
            </div>
            <div class="scale-foot">
                <span>ABAJO</span>
                <span>50 / 50</span>
                <span>ARRIBA</span>
            </div>
        </div>
        """
    )


def enriquecer_historial_para_tabla(historial):
    filas = []
    for registro_original in historial:
        if not isinstance(registro_original, dict):
            continue
        registro = dict(registro_original)
        indicadores = como_dict(registro.get("indicadores"))

        atr_rel = indicadores.get("atr_relativo")
        registro["atr_pct"] = float(atr_rel) * 100 if atr_rel is not None else None
        registro["adx14"] = indicadores.get("adx14")
        registro["stoch_k"] = indicadores.get("stoch_k")
        registro["stoch_d"] = indicadores.get("stoch_d")

        spread = registro.get("spread_kalshi")
        registro["spread_centavos"] = float(spread) * 100 if spread is not None else None

        pnl = registro.get("pnl_bruto_teorico_1_contrato")
        entrada = registro.get("precio_entrada")
        try:
            registro["roi_bruto_pct"] = (
                float(pnl) / float(entrada) * 100.0
                if pnl is not None and float(entrada) > 0
                else None
            )
        except Exception:
            registro["roi_bruto_pct"] = None

        filas.append(registro)
    return pd.DataFrame(filas)


# ============================================================
# CABECERA FIJA
# ============================================================

st.html(
    """
    <div class="hero">
        <div class="hero-title">₿ BTC 15M PROFIT ENGINE V2 PRO</div>
        <div class="hero-sub">
            Kalshi · CF Benchmarks BRTI · Coinbase · Kraken ·
            CoinMarketCap · Bitstamp · Mempool ·
            ATR/ADX · Stochastic RSI · Bollinger · Order Flow · Microestructura
        </div>
    </div>
    """
)

st.html(
    f"""
    <div class="live">
        <span class="live-dot"></span>
        ACTUALIZACIÓN AUTOMÁTICA CADA {AUTO_REFRESH_SEGUNDOS} SEGUNDOS
    </div>
    """
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
        borrar = st.button(
            "🗑️ ELIMINAR HISTORIAL",
            use_container_width=True,
            key="eliminar_historial_btn",
        )
        if borrar and eliminar_historial():
            historial = []
            analisis = None

    with b2:
        if analisis is not None:
            hora_motor = (
                analisis.get("timestamp_local")
                or analisis.get("hora_local")
                or analisis.get("timestamp")
                or "N/D"
            )
            st.caption("Última actualización del motor: " + str(hora_motor))
        else:
            st.caption("Esperando datos del motor.")

    if analisis is None:
        st.info("Esperando la primera predicción válida del motor en la ventana 0–5.")
        return

    decision = str(analisis.get("decision", "NO APOSTAR"))
    fuerza = str(analisis.get("fuerza", "DEBIL"))
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
        f"""
        <div class="{clase}">
            <div class="decision-small">ÚLTIMA DECISIÓN DEL MOTOR</div>
            <div class="decision-big">{icono} {html.escape(decision)}</div>
            <div class="decision-meta">
                FUERZA <b>{html.escape(fuerza)}</b>
                &nbsp;&nbsp;·&nbsp;&nbsp;
                PROBABILIDAD <b>{probabilidad:.1f}%</b>
            </div>
        </div>
        """
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
        tarjeta(
            "TIEMPO RESTANTE",
            numero(analisis.get("segundos_restantes"), 0, "", " s"),
        )
    with c4:
        tarjeta(
            "MINUTO DE ENTRADA",
            numero(analisis.get("minuto_entrada"), 2),
            "Ventana permitida 0:00–5:00",
        )

    tarjeta("SCORE TOTAL", numero(analisis.get("score"), 2))

    # Probabilidad y valor
    seccion("Probabilidad y valor")
    escala_probabilidad(analisis.get("probabilidad_arriba", 50))

    p1, p2 = st.columns(2)
    with p1:
        tarjeta(
            "PROB. ARRIBA",
            numero(analisis.get("probabilidad_arriba"), 1, "", "%"),
        )
    with p2:
        tarjeta(
            "PROB. ABAJO",
            numero(analisis.get("probabilidad_abajo"), 1, "", "%"),
        )

    edge = analisis.get("edge")
    spread = analisis.get("spread_kalshi")
    precio_entrada = analisis.get("precio_entrada")
    p3, p4, p5 = st.columns(3)
    with p3:
        tarjeta(
            "EDGE DESPUÉS DE FRICCIÓN",
            numero(float(edge) * 100, 2, "", "%") if edge is not None else "SIN EDGE",
        )
    with p4:
        tarjeta(
            "SPREAD KALSHI",
            numero(float(spread) * 100, 1, "", " ¢") if spread is not None else "N/D",
            "Máximo permitido: 3.0 ¢",
        )
    with p5:
        tarjeta(
            "PRECIO ENTRADA",
            numero(precio_entrada, 3, "$") if precio_entrada is not None else "NO ENTRA",
        )

    escala("SCORE TOTAL", analisis.get("score", 0), -100, 100, "{:+.2f}")

    # Filtros avanzados
    seccion("Filtros avanzados")
    indicadores = como_dict(analisis.get("indicadores"))
    regimen = como_dict(analisis.get("regimen"))
    micro = como_dict(analisis.get("microestructura"))
    calidad_micro = como_dict(micro.get("calidad"))
    calidad_consenso = como_dict(analisis.get("calidad_consenso"))

    regimen_texto = "BLOQUEADO" if regimen.get("bloqueado") else "VÁLIDO"
    atr_rel = indicadores.get("atr_relativo")
    atr_texto = (
        numero(float(atr_rel) * 100, 3, "", "%")
        if atr_rel is not None
        else "N/D"
    )

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        tarjeta("RÉGIMEN", regimen_texto)
    with f2:
        tarjeta("ATR RELATIVO", atr_texto)
    with f3:
        tarjeta("ADX 14", numero(indicadores.get("adx14"), 1))
    with f4:
        tarjeta(
            "STOCHASTIC RSI",
            f"K {numero(indicadores.get('stoch_k'), 1)} · D {numero(indicadores.get('stoch_d'), 1)}",
        )

    tabla_metricas([
        ("DI comprador (+DI)", numero(indicadores.get("plus_di"), 2)),
        ("DI vendedor (-DI)", numero(indicadores.get("minus_di"), 2)),
        ("Bollinger superior", numero(indicadores.get("bb_upper"), 2, "$")),
        ("Bollinger media", numero(indicadores.get("bb_mid"), 2, "$")),
        ("Bollinger inferior", numero(indicadores.get("bb_lower"), 2, "$")),
        ("OBI conjunto", numero(micro.get("obi_total"), 3)),
        ("Flujo agresivo", numero(micro.get("orderflow_total"), 3)),
        ("Absorción", numero(micro.get("absorcion"), 1)),
        ("Libros saludables", str(calidad_micro.get("books_validos", "N/D"))),
        ("Flujos saludables", str(calidad_micro.get("flujos_validos", "N/D"))),
        ("Fuentes saludables", str(calidad_consenso.get("fuentes_validas", "N/D"))),
        ("Dispersión de fuentes", numero(calidad_consenso.get("dispersion_pct"), 3, "", "%")),
    ])

    # Fuentes
    seccion("Precios de fuentes")
    fuentes = fuentes_del_analisis(analisis)
    tabla_metricas([
        ("CF Benchmarks / BRTI", numero(fuentes.get("CF_BRTI"), 2, "$")),
        ("Coinbase BTC-USD", numero(fuentes.get("COINBASE"), 2, "$")),
        ("Kraken XBTUSD", numero(fuentes.get("KRAKEN"), 2, "$")),
        ("CoinMarketCap", numero(fuentes.get("CMC"), 2, "$")),
        ("Bitstamp BTCUSD", numero(fuentes.get("BITSTAMP"), 2, "$")),
        ("Precio consenso", numero(analisis.get("precio_consenso"), 2, "$")),
    ])

    # Razones
    seccion("Razones de la decisión")
    razones = analisis.get("razones") or []
    if razones:
        for razon in razones:
            st.html(f'<div class="reason">{html.escape(str(razon))}</div>')
    else:
        st.caption("No hay razones registradas.")

    # Historial y rendimiento
    seccion("Historial y rendimiento")
    if not historial:
        st.info("Historial vacío.")
        return

    df = enriquecer_historial_para_tabla(historial)
    if df.empty or "decision" not in df.columns:
        st.info("Historial vacío.")
        return

    df_operados = df[
        df["decision"].astype(str).str.upper().isin(["ARRIBA", "ABAJO"])
    ].copy()

    total_operaciones = len(df_operados)
    ganadas = 0
    perdidas = 0
    if "evaluacion" in df_operados.columns:
        evaluaciones = df_operados["evaluacion"].fillna("").astype(str).str.upper()
        ganadas = int(evaluaciones.isin(["GANADA", "ACIERTO"]).sum())
        perdidas = int(evaluaciones.isin(["PERDIDA", "FALLO"]).sum())

    total_resueltas = ganadas + perdidas
    win_rate = ganadas / total_resueltas * 100.0 if total_resueltas else 0.0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        tarjeta("OPERACIONES", str(total_operaciones), f"{total_resueltas} resueltas")
    with m2:
        tarjeta("GANADAS", str(ganadas))
    with m3:
        tarjeta("PERDIDAS", str(perdidas))
    with m4:
        tarjeta("EFECTIVIDAD", f"{win_rate:.1f}%", "Solo operaciones resueltas")

    columnas = [
        "timestamp_local",
        "timestamp",
        "ticker",
        "decision",
        "fuerza",
        "probabilidad",
        "target",
        "precio_consenso",
        "precio_entrada",
        "edge",
        "spread_centavos",
        "minuto_entrada",
        "score",
        "atr_pct",
        "adx14",
        "stoch_k",
        "stoch_d",
        "resultado",
        "evaluacion",
        "pnl_bruto_teorico_1_contrato",
        "roi_bruto_pct",
    ]
    columnas_existentes = [columna for columna in columnas if columna in df.columns]
    st.dataframe(
        df[columnas_existentes].iloc[::-1],
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# INICIAR DASHBOARD EN VIVO
# ============================================================

dashboard_en_vivo()
