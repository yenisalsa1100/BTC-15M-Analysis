"""
STREAMLIT APP - KALSHI BTC 15M (DISEÑO PROFESIONAL AVANZADO)
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

historial = cargar_historial_github()

# Botón superior de eliminar historial (simulado visualmente o funcional)
if st.button("🗑️ ELIMINAR HISTORIAL", use_container_width=True):
    st.warning("Función de limpieza de historial conectada al motor.")

# Banner principal de última predicción
if historial:
    ultimo = historial[-1]
    decision = ultimo.get("decision", "N/A")
    prob = float(ultimo.get("probabilidad", 0))
    score = float(ultimo.get("score", 0))
    
    # Color del banner según decisión
    color_banner = "#1e293b"
    if decision == "ARRIBA":
        color_banner = "#064e3b"
    elif decision == "ABAJO":
        color_banner = "#7f1d1d"

    st.markdown(
        f"""
        <div style="background-color: {color_banner}; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
            <p style="margin: 0; font-size: 12px; color: #94a3b8; letter-spacing: 1px;">ÚLTIMA PREDICCIÓN</p>
            <h1 style="margin: 5px 0; color: #ffffff;">{'▲ ARRIBA' if decision == 'ARRIBA' else ('▼ ABAJO' if decision == 'ABAJO' else '● NO APOSTAR')}</h1>
            <p style="margin: 0; font-size: 14px; color: #cbd5e1;">Probabilidad: {prob:.1f}% | Score: {score:.1f}</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Métricas Operación
    st.markdown("### 🎯 Operación")
    c1, c2, c3 = st.columns(3)
    c1.metric("Ticker", ultimo.get("ticker", "N/D"))
    c2.metric("Entrada", f"Objetivo: {ultimo.get('minuto_entrada', 'N/D')}")
    c3.metric("Hora", str(ultimo.get("timestamp", "N/D")))
    
    # Métricas Profit Máximo
    st.markdown("### 💰 Profit máximo")
    p1, p2, p3 = st.columns(3)
    p1.metric("Entrada", "N/D")
    p2.metric("Máximo Alcanzado", "N/D")
    p3.metric("Profit Máximo", "⏳ PENDIENTE")

    # Métricas Resultado
    st.markdown("### 🏁 Resultado")
    r1, r2 = st.columns(2)
    r1.metric("Resultado Final", "⏳ PENDIENTE")
    r2.metric("Llegó a +15%", "⏳ PENDIENTE")

# Resumen Global Cálculos
total_reg = len(historial)
operadas = [h for h in historial if h.get("decision") in ("ARRIBA", "ABAJO")]
ganadas = sum(1 for h in operadas if h.get("resultado") == "GANADA")
perdidas = sum(1 for h in operadas if h.get("resultado") == "PERDIDA")
precision = (ganadas / len(operadas) * 100) if operadas else 0.0

st.markdown("---")
st.markdown("### 📊 Resumen")
s1, s2, s3, s4 = st.columns(4)
s1.metric("Operaciones", total_reg)
s2.metric("Ganadas", ganadas)
s3.metric("Perdidas", perdidas)
s4.metric("Precisión", f"{precision:.1f}%")

# Métricas Profit +15%
con_profit = sum(1 for h in operadas if h.get("profit_15_alcanzado", False))
sin_profit = len(operadas) - con_profit
efectividad_profit = (con_profit / len(operadas) * 100) if operadas else 0.0

st.markdown("### 🚀 Profit +15%")
f1, f2, f3, f4 = st.columns(4)
f1.metric("Con Profit +15%", con_profit)
f2.metric("Sin Profit +15%", sin_profit)
f3.metric("Pendientes", len(historial) - len(operadas))
f4.metric("Efectividad Profit", f"{efectividad_profit:.1f}%")

# Historial Tabla Inferior
st.markdown("---")
st.markdown("### 📜 Historial")
if historial:
    datos_tabla = []
    for item in reversed(historial[-30:]):
        datos_tabla.append({
            "Hora": item.get("timestamp", "N/D"),
            "Ticker": item.get("ticker", "N/D"),
            "Predicción": item.get("decision", "N/D"),
            "Prob %": f"{float(item.get('probabilidad', 0)):.1f}",
            "Score": f"{float(item.get('score', 0)):.1f}",
            "Entrada": item.get("minuto_entrada", "N/D"),
            "Objetivo": item.get("target", "N/D"),
            "Máximo": "N/D",
            "Profit": "PENDIENTE"
        })
    st.dataframe(datos_tabla, use_container_width=True)
else:
    st.info("Cargando historial de datos...")
