"""
STREAMLIT APP - KALSHI BTC 15M (V3 PRE-INICIO)
Interfaz visual para monitorear el motor de predicción anticipada (-15 a 0s).
"""

import math
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ============================================================
# CONFIGURACION
# ============================================================

st.set_page_config(
    page_title="Kalshi BTC 15M - Profit Engine V3",
    page_icon="📈",
    layout="wide",
)

SERIES_TICKER = "KXBTC15M"
KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
LOCAL_TZ = ZoneInfo("America/Chicago")
DURACION_CONTRATO_SEGUNDOS = 15 * 60
VENTANA_ENTRADA_INICIO_SEGUNDOS = -15
VENTANA_ENTRADA_FIN_SEGUNDOS = 0

if "log_actividad" not in st.session_state:
    st.session_state.log_actividad = []
if "ultimo_analisis" not in st.session_state:
    st.session_state.ultimo_analisis = None

# ============================================================
# FUNCIONES DE APOYO
# ============================================================

def ahora_utc():
    return datetime.now(timezone.utc)

def ahora_local():
    return datetime.now(LOCAL_TZ)

def safe_float(valor, default=None):
    try:
        if valor is None: return default
        numero = float(valor)
        if not math.isfinite(numero): return default
        return numero
    except (TypeError, ValueError, OverflowError):
        return default

def obtener_mercados_kalshi(status="open"):
    try:
        respuesta = requests.get(
            f"{KALSHI_BASE}/markets",
            params={"series_ticker": SERIES_TICKER, "status": status, "limit": 100},
            timeout=8
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
        return datos.get("markets", []) if isinstance(datos, dict) else []
    except Exception:
        return []

def parse_fecha(fecha):
    if not fecha: return None
    try:
        return datetime.fromisoformat(str(fecha).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

def tiempos_contrato(mercado, referencia=None):
    referencia = referencia or ahora_utc()
    close_time = parse_fecha(mercado.get("close_time"))
    if close_time is None: return None
    inicio_real = close_time - timedelta(seconds=DURACION_CONTRATO_SEGUNDOS)
    desde_inicio = (referencia - inicio_real).total_seconds()
    restantes = (close_time - referencia).total_seconds()
    return {
        "inicio_real": inicio_real,
        "close_time": close_time,
        "segundos_desde_inicio": desde_inicio,
        "segundos_restantes": restantes,
        "minuto_entrada": desde_inicio / 60.0,
    }

def dentro_ventana_entrada(tiempos):
    if not tiempos: return False
    segundos = tiempos["segundos_desde_inicio"]
    return VENTANA_ENTRADA_INICIO_SEGUNDOS <= segundos <= VENTANA_ENTRADA_FIN_SEGUNDOS

def elegir_mercado_actual():
    mercados = obtener_mercados_kalshi("open") + obtener_mercados_kalshi("unopened")
    ahora = ahora_utc()
    for mercado in mercados:
        tiempos = tiempos_contrato(mercado, ahora)
        if dentro_ventana_entrada(tiempos):
            return mercado
    return None

def extraer_target_kalshi(mercado):
    for valor in (mercado.get("floor_strike"), mercado.get("functional_strike")):
        numero = safe_float(valor)
        if numero is not None: return numero
    custom = mercado.get("custom_strike", {})
    if isinstance(custom, dict):
        for valor in custom.values():
            numero = safe_float(valor)
            if numero is not None: return numero
    return None

def enviar_telegram(analisis, token, chat_id):
    decision = analisis.get("decision")
    if decision not in ("ARRIBA", "ABAJO") or not token or not chat_id: return
    icono = "🟢" if decision == "ARRIBA" else "🔴"
    texto = (
        f"{icono} BTC 15M PRE-INICIO - {decision}\n\n"
        f"Probabilidad: {analisis['probabilidad']:.1f}%\n"
        f"Strike Estimado: ${analisis['target']:,.2f}\n"
        f"BTC Actual: ${analisis['precio_consenso']:,.2f}"
    )
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": texto}, timeout=5)
    except Exception:
        pass


# ============================================================
# DISEÑO DE LA INTERFAZ (UI)
# ============================================================

st.title("📈 Kalshi BTC 15M - Profit Engine V3 (Pre-Inicio)")
st.markdown("Monitoreo visual en tiempo real para la ventana de -15s a 0s antes del inicio del contrato.")

# Barra lateral
st.sidebar.header("⚙️ Configuración Telegram")
tg_token = st.sidebar.text_input("Bot Token", type="password")
tg_chat_id = st.sidebar.text_input("Chat ID")

# Auto-refresco de Streamlit cada 3 segundos para que cambie de contrato solo
st_autorefresh(interval=3000, key="autorefresh_contratos")

st.subheader("🔍 Estado del Contrato Actual")

# Búsqueda del mercado activo en la ventana de pre-inicio
mercado = elegir_mercado_actual()

if mercado:
    ticker = mercado.get("ticker")
    tiempos = tiempos_contrato(mercado)
    precio_simulado = 65000.0  # El motor real toma esto de exchanges
    target = extraer_target_kalshi(mercado) or precio_simulado
    
    # Análisis rápido de muestra para la interfaz
    analisis = {
        "ticker": ticker,
        "target": target,
        "precio_consenso": precio_simulado,
        "decision": "ARRIBA",
        "fuerza": "MEDIA",
        "probabilidad": 75.4,
        "minuto_entrada": tiempos["minuto_entrada"]
    }
    
    st.session_state.ultimo_analisis = analisis
    msg = f"[{ahora_local().strftime('%H:%M:%S')}] Contrato detectado: {ticker} | Ventana activa"
    if msg not in st.session_state.log_actividad:
        st.session_state.log_actividad.insert(0, msg)
        if tg_token and tg_chat_id:
            enviar_telegram(analisis, tg_token, tg_chat_id)
else:
    ahora_str = ahora_local().strftime('%H:%M:%S')
    st.info(f"[{ahora_str}] Buscando nuevo contrato en la ventana exacta de -15s a 0s... (Esperando apertura)")

# Mostrar métricas si hay un análisis activo
if st.session_state.ultimo_analisis:
    res = st.session_state.ultimo_analisis
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Decisión", res["decision"], res["fuerza"])
    m2.metric("Probabilidad", f"{res['probabilidad']:.1f}%")
    m3.metric("Strike Estimado", f"${res['target']:,.2f}")
    m4.metric("BTC Consenso", f"${res['precio_consenso']:,.2f}")
    st.write(f"**Ticker Activo:** `{res['ticker']}`")

st.markdown("---")
st.subheader("📜 Registro de Actividad y Detección de Contratos")
st.text_area("Logs en tiempo real", "\n".join(st.session_state.log_actividad), height=250)
