"""
STREAMLIT APP - KALSHI BTC 15M (MUESTRA TODO EL HISTORIAL)
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

st.title("📈 Kalshi BTC 15M - Historial Real del Motor V3")
st.markdown("Monitoreo en tiempo real conectado al repositorio de GitHub.")

historial = cargar_historial_github()

if historial:
    ultimo = historial[-1]  
    st.subheader("🔍 Última Predicción Registrada por el Motor")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Decisión", ultimo.get("decision", "N/A"), ultimo.get("fuerza", ""))
    m2.metric("Probabilidad", f"{float(ultimo.get('probabilidad', 0)):.1f}%")
    m3.metric("Strike / Target", f"${float(ultimo.get('target', 0)):,.2f}")
    m4.metric("BTC Consenso", f"${float(ultimo.get('precio_consenso', 0)):,.2f}")
    
    st.write(f"**Ticker del Contrato:** `{ultimo.get('ticker', 'N/A')}`")
    minuto_val = float(ultimo.get('minuto_entrada', 0))
    st.write(f"**Minuto de Entrada:** {minuto_val:.2f}")
else:
    st.info("Esperando datos...")

st.markdown("---")
st.subheader("📜 Registro Completo de Predicciones Guardadas")

if historial:
    for item in reversed(historial[-20:]):
        decision_txt = item.get("decision", "N/A")
        fuerza_txt = item.get("fuerza", "N/A")
        ticker_txt = item.get("ticker", "N/A")
        prob_txt = float(item.get("probabilidad", 0))
        st.text(f"Ticker: {ticker_txt} | Decisión: {decision_txt} ({fuerza_txt}) | Prob: {prob_txt:.1f}%")
else:
    st.write("Aún no hay registros disponibles en línea.")
