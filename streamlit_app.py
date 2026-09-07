"""
STREAMLIT APP - KALSHI BTC 15M (PANEL DE RENDIMIENTO Y EFECTIVIDAD)
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Kalshi BTC 15M - Profit Engine V3",
    page_icon="📈",
    layout="wide",
)

GITHUB_RAW_URL = "https://raw.githubusercontent.com/yenisalsa1100/BTC-15M-Analysis/main/historial_btc_15m_v2.json"

st_autorefresh(interval=3000, key="autorefresh_historial_github")

def cargar_historial_github():
    try:
        url_con_cache_bypass = f"{GITHUB_RAW_URL}?t={datetime.now().timestamp()}"
        respuesta = requests.get(url_con_cache_bypass, timeout=5)
        if respuesta.status_code == 200:
            data = respuesta.json()
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []

st.title("📈 Kalshi BTC 15M - Rendimiento y Profit Engine")
st.markdown("Monitoreo dinámico de señales, decisiones y efectividad.")

historial = cargar_historial_github()

if historial:
    # Métricas de resumen global
    total_registros = len(historial)
    apuestas = [h for h in historial if h.get("decision") in ("ARRIBA", "ABAJO")]
    total_apostados = len(apuestas)
    
    # Calcular métricas rápidas de porcentaje de señales operables
    pct_operable = (total_apostados / total_registros * 100) if total_registros > 0 else 0

    st.subheader("📊 Resumen General del Sistema")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Registros", total_registros)
    c2.metric("Señales de Operación", total_apostados)
    c3.metric("% de Filtrado (Activas)", f"{pct_operable:.1f}%")
    c4.metric("Meta de Profit Objetivo", "15.0%")

    ultimo = historial[-1]  
    st.subheader("🔍 Última Predicción en Vivo")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Decisión", ultimo.get("decision", "N/A"), ultimo.get("fuerza", ""))
    m2.metric("Probabilidad", f"{float(ultimo.get('probabilidad', 0)):.1f}%")
    m3.metric("Strike / Target", f"${float(ultimo.get('target', 0)):,.2f}")
    m4.metric("BTC Consenso", f"${float(ultimo.get('precio_consenso', 0)):,.2f}")
    
    st.write(f"**Ticker:** `{ultimo.get('ticker', 'N/A')}` | **Minuto de Entrada:** {float(ultimo.get('minuto_entrada', 0)):.2f}")
else:
    st.info("Esperando datos en el repositorio...")

st.markdown("---")
st.subheader("📜 Historial Detallado de Decisiones")

if historial:
    for item in reversed(historial[-25:]):
        decision = item.get("decision", "N/A")
        fuerza = item.get("fuerza", "N/A")
        ticker = item.get("ticker", "N/A")
        prob = float(item.get("probabilidad", 0))
        target = float(item.get("target", 0))
        precio = float(item.get("precio_consenso", 0))
        
        # Color visual según la decisión
        if decision == "ARRIBA":
            st.success(f"🟢 **{ticker}** | Decisión: **{decision}** ({fuerza}) | Prob: {prob:.1f}% | Strike: ${target:,.2f} | BTC: ${precio:,.2f}")
        elif decision == "ABAJO":
            st.error(f"🔴 **{ticker}** | Decisión: **{decision}** ({fuerza}) | Prob: {prob:.1f}% | Strike: ${target:,.2f} | BTC: ${precio:,.2f}")
        else:
            st.info(f"⚪ **{ticker}** | Decisión: **{decision}** ({fuerza}) | Prob: {prob:.1f}% | Strike: ${target:,.2f} | BTC: ${precio:,.2f}")
else:
    st.write("Aún no hay registros disponibles.")
