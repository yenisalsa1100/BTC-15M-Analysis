"""
STREAMLIT APP - KALSHI BTC 15M (TRACKING DE PROFIT 15% EN CONTRATOS)
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

st.title("📈 Kalshi BTC 15M - Control de Profit (Meta 15%)")
st.markdown("Seguimiento de contratos que lograron el objetivo de 15% de ganancia en su valor.")

historial = cargar_historial_github()

if historial:
    total_registros = len(historial)
    operaciones_validas = [h for h in historial if h.get("decision") in ("ARRIBA", "ABAJO")]
    total_operados = len(operaciones_validas)
    
    # Contabilizamos los que marcaron éxito en el profit del contrato
    profit_logrado = sum(1 for h in operaciones_validas if h.get("profit_15_alcanzado", False) == True)
    efectividad_profit = (profit_logrado / total_operados * 100) if total_operados > 0 else 0.0

    st.subheader("🎯 Rendimiento de Captura de Profit")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Señales Operadas", total_operados)
    c2.metric("Tocaron 15% Profit", profit_logrado)
    c3.metric("Efectividad de Profit", f"{efectividad_profit:.1f}%")
    c4.metric("Meta por Contrato", "15.0%")

    ultimo = historial[-1]  
    st.subheader("🔍 Última Operación en Curso / Registrada")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Decisión", ultimo.get("decision", "N/A"), ultimo.get("fuerza", ""))
    m2.metric("Probabilidad", f"{float(ultimo.get('probabilidad', 0)):.1f}%")
    m3.metric("Strike / Target", f"${float(ultimo.get('target', 0)):,.2f}")
    m4.metric("BTC Consenso", f"${float(ultimo.get('precio_consenso', 0)):,.2f}")
else:
    st.info("Esperando datos en el repositorio...")

st.markdown("---")
st.subheader("📜 Historial y Estado del 15% Profit")

if historial:
    for item in reversed(historial[-25:]):
        decision = item.get("decision", "N/A")
        fuerza = item.get("fuerza", "N/A")
        ticker = item.get("ticker", "N/A")
        prob = float(item.get("probabilidad", 0))
        target = float(item.get("target", 0))
        precio = float(item.get("precio_consenso", 0))
        
        # Validación del objetivo de profit en el contrato
        alcanzo_15 = item.get("profit_15_alcanzado", False)
        etiqueta_estado = "🚀 +15% Profit Logrado" if alcanzo_15 else "⏳ Monitoreando / Sin 15%"
        
        if decision == "ARRIBA":
            st.success(f"🟢 **{ticker}** | **{decision}** ({fuerza}) | Prob: {prob:.1f}% | Estado: **{etiqueta_estado}**")
        elif decision == "ABAJO":
            st.error(f"🔴 **{ticker}** | **{decision}** ({fuerza}) | Prob: {prob:.1f}% | Estado: **{etiqueta_estado}**")
        else:
            st.info(f"⚪ **{ticker}** | **{decision}** ({fuerza}) | Prob: {prob:.1f}%")
else:
    st.write("Aún no hay registros disponibles.")
