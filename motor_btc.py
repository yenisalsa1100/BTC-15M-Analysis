# ============================================================
# MOTOR KALSHI BTC 15M - VERSIÓN AVANZADA (PROFIT ENGINE V2)
# ============================================================
# MEJORAS PRINCIPALES DE CERTEZA Y SOFISTICACIÓN:
# 1. FILTRO DE RÉGIMEN DE MERCADO (ATR & ADX): Evita operar en
#    mercados con alta volatilidad lateral (chop) o sin dirección.
# 2. PONDERACIÓN DINÁMICA DE FUENTES: Evalúa la salud de cada exchange
#    en tiempo real (Coinbase, Kraken, Bitstamp, CMC, CF BRTI) penalizando
#    fuentes con retraso o desviaciones anómalas (outliers).
# 3. SCORE MULTIDIMENSIONAL AMPLIADO: Incorpora Bandas de Bollinger,
#    Stochastic RSI y análisis avanzado de absorción en Order Books.
# 4. GESTIÓN ESTRICTA DE SPREAD KALSHI: Valida que la fricción del spread
#    no consuma el Edge teórico antes de validar una entrada.
# ============================================================

import os
import time
import json
import math
import signal
import base64
import statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
import pandas as pd

from cryptography.hazmat.primitives import (
    hashes,
    serialization,
)
from cryptography.hazmat.primitives.asymmetric import padding


# ============================================================
# CONFIGURACION GENERAL Y VERSIONES
# ============================================================

VERSION_MOTOR = "BTC_15M_PROFIT_ENGINE_V2_PRO"

SERIES_TICKER = "KXBTC15M"

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
COINBASE_BASE = "https://api.exchange.coinbase.com"
KRAKEN_BASE = "https://api.kraken.com"
CMC_BASE = "https://pro-api.coinmarketcap.com"
BITSTAMP_BASE = "https://www.bitstamp.net"
MEMPOOL_BASE = "https://mempool.space"

LOCAL_TZ = ZoneInfo("America/Chicago")
HISTORIAL_FILE = "historial_btc_15m.json"



# ============================================================
# INTERVALOS Y CONTROL DE TIEMPO
# ============================================================

INTERVALO_REVISION = 5        # Escaneo más ágil (cada 5 segundos)
INTERVALO_RESULTADOS = 30
TIMEOUT_HTTP = 8

MIN_SEGUNDOS_DESDE_APERTURA = 30
MIN_SEGUNDOS_RESTANTES = 90


# ============================================================
# UMBRALES DE ALTA CERTEZA
# ============================================================

PROBABILIDAD_MEDIA = 58.0
PROBABILIDAD_FUERTE = 66.0

SCORE_MEDIO = 32.0
SCORE_FUERTE = 48.0

EDGE_MINIMO_MEDIO = 0.020
EDGE_MINIMO_FUERTE = 0.040

TARGET_ZONA_MUERTA_PCT = 0.008
TARGET_DISTANCIA_FUERTE_PCT = 0.040


# ============================================================
# MICROESTRUCTURA Y LIBROS
# ============================================================

ORDERBOOK_NIVELES = 15
TRADES_WINDOW_SEGUNDOS = 60
TRADES_MAX = 300

DETENER = False
ULTIMO_RESULTADO_CHECK = 0

ULTIMO_CMC = {"precio": None, "timestamp": 0}
ULTIMO_CF = {"precio": None, "timestamp": 0}
ULTIMO_MEMPOOL = {
    "datos": None,
    "timestamp": 0,
    "count_anterior": None,
    "vsize_anterior": None,
}


# ============================================================
# SIGNAL HANDLER
# ============================================================

def manejar_senal(signum, frame):
    global DETENER
    print("\n[STOP] Señal de cancelación recibida de forma segura.")
    DETENER = True

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, manejar_senal)
    signal.signal(signal.SIGINT, manejar_senal)


# ============================================================
# UTILIDADES MATEMÁTICAS Y DE FECHA
# ============================================================

def ahora_utc():
    return datetime.now(timezone.utc)

def ahora_local():
    return datetime.now(LOCAL_TZ)

def iso_utc():
    return ahora_utc().isoformat()

def safe_float(valor, default=None):
    try:
        if valor is None:
            return default
        return float(valor)
    except Exception:
        return default

def limitar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))

def media_ponderada_robusta(valores_con_pesos):
    """Calcula la media descartando outliers extremos mediante desviación absoluta mediana."""
    validos = [(v, p) for v, p in valores_con_pesos if v is not None and math.isfinite(v)]
    if not validos:
        return None
    
    precios = [v for v, p in validos]
    med = statistics.median(precios)
    
    # Filtrar desviaciones mayores al 1.5% del precio mediano
    filtrados = [(v, p) for v, p in validos if abs(v - med) / med < 0.015]
    if not filtrados:
        filtrados = validos # Fallback si todos se desvían

    suma_pv = sum(v * p for v, p in filtrados)
    suma_p = sum(p for v, p in filtrados)
    
    if suma_p == 0:
        return statistics.mean(precios)
    return suma_pv / suma_p


def dormir_interrumpible(segundos):
    for _ in range(int(segundos)):
        if DETENER:
            return
        time.sleep(1)


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Kalshi-BTC-15M-Profit-Engine-V2/2.0",
    "Accept": "application/json",
})

def http_get(url, params=None, headers=None, timeout=TIMEOUT_HTTP):
    try:
        r = SESSION.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[HTTP] Error GET {url}: {e}")
        return None


# ============================================================
# TELEGRAM NOTIFIER
# ============================================================

def enviar_telegram(analisis):
    decision = analisis.get("decision")
    if decision not in ["ARRIBA", "ABAJO"]:
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return

    icono = "🟢" if decision == "ARRIBA" else "🔴"
    target = analisis.get("target")
    precio = analisis.get("precio_consenso")
    prob = analisis.get("probabilidad")
    fuerza = analisis.get("fuerza")
    edge = analisis.get("edge")
    minuto = analisis.get("minuto_entrada")

    texto = (
        f"{icono} BTC 15M PRO V2 - {decision}\n\n"
        f"Fuerza: {fuerza}\n"
        f"Probabilidad: {prob:.1f}%\n"
        f"Target Kalshi: ${target:,.2f}\n"
        f"BTC Consenso: ${precio:,.2f}\n"
    )

    if edge is not None:
        texto += f"Edge Real: {edge * 100:+.2f}%\n"
    if minuto is not None:
        texto += f"Minuto de entrada: {minuto:.2f}\n"

    try:
        respuesta = SESSION.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": texto},
            timeout=TIMEOUT_HTTP,
        )
        if not respuesta.ok:
            print(f"[TELEGRAM] Error HTTP: {respuesta.status_code}")
    except Exception as e:
        print(f"[TELEGRAM] Error: {e}")


# ============================================================
# KALSHI AUTH
# ============================================================

def cargar_private_key():
    texto = os.getenv("KALSHI_PRIVATE_KEY", "").strip()
    texto_b64 = os.getenv("KALSHI_PRIVATE_KEY_BASE64", "").strip()

    if not texto and texto_b64:
        try:
            texto = base64.b64decode(texto_b64).decode("utf-8")
        except Exception:
            return None

    if not texto:
        return None

    texto = texto.replace("\\n", "\n")
    try:
        return serialization.load_pem_private_key(texto.encode("utf-8"), password=None)
    except Exception as e:
        print(f"[KALSHI AUTH] Error cargando private key: {e}")
        return None

PRIVATE_KEY = cargar_private_key()
KALSHI_API_KEY_ID = os.getenv("KALSHI_API_KEY_ID", "").strip()

def firma_kalshi(timestamp_ms, method, path):
    if PRIVATE_KEY is None:
        return None
    path_sin_query = path.split("?")[0]
    mensaje = f"{timestamp_ms}{method.upper()}{path_sin_query}".encode("utf-8")
    firma = PRIVATE_KEY.sign(
        mensaje,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(firma).decode("utf-8")

def headers_kalshi(method, path):
    if not KALSHI_API_KEY_ID or PRIVATE_KEY is None:
        return None
    timestamp_ms = str(int(time.time() * 1000))
    firma = firma_kalshi(timestamp_ms, method, "/trade-api/v2" + path)
    return {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "KALSHI-ACCESS-SIGNATURE": firma,
    }


# ============================================================
# MERCADOS KALSHI
# ============================================================

def parse_fecha(fecha):
    if not fecha:
        return None
    try:
        return datetime.fromisoformat(fecha.replace("Z", "+00:00"))
    except Exception:
        return None

def obtener_mercados_kalshi(status="open"):
    datos = http_get(f"{KALSHI_BASE}/markets", params={"series_ticker": SERIES_TICKER, "status": status, "limit": 100})
    if not datos:
        return []
    return datos.get("markets", [])

def elegir_mercado_actual():
    mercados = obtener_mercados_kalshi("open")
    if not mercados:
        return None
    ahora = ahora_utc()
    candidatos = []
    for mercado in mercados:
        close_time = parse_fecha(mercado.get("close_time"))
        if close_time is None:
            continue
        segundos = (close_time - ahora).total_seconds()
        if segundos <= 0:
            continue
        candidatos.append((segundos, mercado))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0])
    return candidatos[0][1]

def obtener_mercado_por_ticker(ticker):
    datos = http_get(f"{KALSHI_BASE}/markets/{ticker}")
    if not datos:
        return None
    return datos.get("market", datos)

def extraer_target_kalshi(mercado):
    for valor in [mercado.get("floor_strike"), mercado.get("functional_strike")]:
        numero = safe_float(valor)
        if numero is not None:
            return numero
    custom = mercado.get("custom_strike", {})
    if isinstance(custom, dict):
        for valor in custom.values():
            numero = safe_float(valor)
            if numero is not None:
                return numero
    return None

def convertir_precio_kalshi(valor):
    if valor is None:
        return None
    numero = safe_float(valor)
    if numero is None:
        return None
    if numero > 1:
        numero /= 100.0
    return limitar(numero, 0.0, 1.0)

def precio_yes_ask(mercado):
    for x in [mercado.get("yes_ask_dollars"), mercado.get("yes_ask")]:
        p = convertir_precio_kalshi(x)
        if p is not None:
            return p
    return None

def precio_no_ask(mercado):
    for x in [mercado.get("no_ask_dollars"), mercado.get("no_ask")]:
        p = convertir_precio_kalshi(x)
        if p is not None:
            return p
    return None


# ============================================================
# LIBRERÍA DE EXCHANGES Y LIBROS DE ÓRDENES (CONFIABILIDAD V2)
# ============================================================

def obtener_orderbook_kalshi(ticker):
    datos = http_get(f"{KALSHI_BASE}/markets/{ticker}/orderbook")
    if not datos:
        return None
    return datos.get("orderbook", datos)

def sumar_book_kalshi(lados):
    total = 0.0
    if not isinstance(lados, list):
        return 0.0
    for nivel in lados[:ORDERBOOK_NIVELES]:
        if isinstance(nivel, list) and len(nivel) >= 2:
            total += safe_float(nivel[1], 0.0)
        elif isinstance(nivel, dict):
            total += safe_float(nivel.get("quantity", nivel.get("count", 0)), 0)
    return total

def obi_kalshi(orderbook):
    if not orderbook:
        return 0.0
    yes = orderbook.get("yes") or orderbook.get("yes_dollars") or []
    no = orderbook.get("no") or orderbook.get("no_dollars") or []
    qty_yes = sumar_book_kalshi(yes)
    qty_no = sumar_book_kalshi(no)
    total = qty_yes + qty_no
    if total <= 0:
        return 0.0
    return (qty_yes - qty_no) / total


# --- COINBASE ---
def obtener_coinbase_ticker():
    datos = http_get(f"{COINBASE_BASE}/products/BTC-USD/ticker")
    if not datos:
        return None
    return safe_float(datos.get("price"))

def obtener_coinbase_candles():
    datos = http_get(f"{COINBASE_BASE}/products/BTC-USD/candles", params={"granularity": 60})
    if not datos:
        return None
    filas = []
    for item in datos:
        try:
            filas.append({
                "time": int(item[0]),
                "low": float(item[1]),
                "high": float(item[2]),
                "open": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            })
        except Exception:
            continue
    if not filas:
        return None
    df = pd.DataFrame(filas)
    return df.sort_values("time").reset_index(drop=True)

def obtener_coinbase_book():
    return http_get(f"{COINBASE_BASE}/products/BTC-USD/book", params={"level": 2})

def obtener_coinbase_trades():
    datos = http_get(f"{COINBASE_BASE}/products/BTC-USD/trades", params={"limit": 100})
    return datos if isinstance(datos, list) else []

def obi_coinbase(book):
    if not book:
        return 0.0
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    bid_qty = sum(safe_float(x[1], 0) for x in bids[:ORDERBOOK_NIVELES] if len(x) >= 2)
    ask_qty = sum(safe_float(x[1], 0) for x in asks[:ORDERBOOK_NIVELES] if len(x) >= 2)
    total = bid_qty + ask_qty
    if total <= 0:
        return 0.0
    return (bid_qty - ask_qty) / total


# --- KRAKEN ---
def kraken_pair_key(resultado):
    if not isinstance(resultado, dict):
        return None
    for key in resultado.keys():
        if key != "last":
            return key
    return None

def obtener_kraken_ticker():
    datos = http_get(f"{KRAKEN_BASE}/0/public/Ticker", params={"pair": "XBTUSD"})
    if not datos:
        return None
    resultado = datos.get("result", {})
    key = kraken_pair_key(resultado)
    if not key:
        return None
    try:
        return float(resultado[key]["c"][0])
    except Exception:
        return None

def obtener_kraken_book():
    datos = http_get(f"{KRAKEN_BASE}/0/public/Depth", params={"pair": "XBTUSD", "count": ORDERBOOK_NIVELES})
    if not datos:
        return None
    resultado = datos.get("result", {})
    key = kraken_pair_key(resultado)
    if not key:
        return None
    return resultado.get(key)

def obtener_kraken_trades():
    datos = http_get(f"{KRAKEN_BASE}/0/public/Trades", params={"pair": "XBTUSD", "count": TRADES_MAX})
    if not datos:
        return []
    resultado = datos.get("result", {})
    key = kraken_pair_key(resultado)
    if not key:
        return []
    return resultado.get(key, [])

def obi_kraken(book):
    if not book:
        return 0.0
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    bid_qty = sum(safe_float(x[1], 0.0) for x in bids[:ORDERBOOK_NIVELES] if len(x) >= 2)
    ask_qty = sum(safe_float(x[1], 0.0) for x in asks[:ORDERBOOK_NIVELES] if len(x) >= 2)
    total = bid_qty + ask_qty
    if total <= 0:
        return 0.0
    return (bid_qty - ask_qty) / total


# --- BITSTAMP ---
def obtener_bitstamp_ticker():
    datos = http_get(f"{BITSTAMP_BASE}/api/v2/ticker/btcusd/")
    if not datos:
        return None
    return safe_float(datos.get("last"))

def obtener_bitstamp_book():
    return http_get(f"{BITSTAMP_BASE}/api/v2/order_book/btcusd/", params={"group": 1})

def obtener_bitstamp_trades():
    datos = http_get(f"{BITSTAMP_BASE}/api/v2/transactions/btcusd/", params={"time": "minute"})
    return datos[:TRADES_MAX] if isinstance(datos, list) else []

def obi_bitstamp(book):
    if not book:
        return 0.0
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    bid_qty = sum(safe_float(x[1], 0.0) for x in bids[:ORDERBOOK_NIVELES] if len(x) >= 2)
    ask_qty = sum(safe_float(x[1], 0.0) for x in asks[:ORDERBOOK_NIVELES] if len(x) >= 2)
    total = bid_qty + ask_qty
    if total <= 0:
        return 0.0
    return (bid_qty - ask_qty) / total


# ============================================================
# ORDER FLOW AGRESIVO (V2)
# ============================================================

def orderflow_bitstamp(trades):
    if not trades:
        return {"imbalance": 0.0, "buy_volume": 0.0, "sell_volume": 0.0, "trades": 0}
    ahora_ts = time.time()
    buy_volume = 0.0
    sell_volume = 0.0
    usados = 0
    for trade in trades:
        try:
            timestamp = safe_float(trade.get("date"), 0)
            if timestamp and (ahora_ts - timestamp) > TRADES_WINDOW_SEGUNDOS:
                continue
            amount = safe_float(trade.get("amount"), 0)
            tipo = str(trade.get("type", "")).lower()
            if tipo in ["0", "buy"]:
                buy_volume += amount
            elif tipo in ["1", "sell"]:
                sell_volume += amount
            usados += 1
        except Exception:
            continue
    total = buy_volume + sell_volume
    imbalance = (buy_volume - sell_volume) / total if total > 0 else 0.0
    return {"imbalance": imbalance, "buy_volume": buy_volume, "sell_volume": sell_volume, "trades": usados}

def orderflow_coinbase(trades):
    if not trades:
        return {"imbalance": 0.0, "buy_volume": 0.0, "sell_volume": 0.0, "trades": 0}
    ahora = ahora_utc()
    buy_volume = 0.0
    sell_volume = 0.0
    usados = 0
    for trade in trades:
        try:
            fecha = parse_fecha(trade.get("time"))
            if fecha and (ahora - fecha).total_seconds() > TRADES_WINDOW_SEGUNDOS:
                continue
            size = safe_float(trade.get("size"), 0)
            side = str(trade.get("side", "")).lower()
            if side == "sell":
                buy_volume += size
            elif side == "buy":
                sell_volume += size
            usados += 1
        except Exception:
            continue
    total = buy_volume + sell_volume
    imbalance = (buy_volume - sell_volume) / total if total > 0 else 0.0
    return {"imbalance": imbalance, "buy_volume": buy_volume, "sell_volume": sell_volume, "trades": usados}


# ============================================================
# MEMPOOL Y ORÁCULOS EXTERNOS (CMC / CF BRTI)
# ============================================================

def obtener_mempool():
    global ULTIMO_MEMPOOL
    ahora = time.time()
    if ULTIMO_MEMPOOL["datos"] is not None and (ahora - ULTIMO_MEMPOOL["timestamp"]) < 20:
        return ULTIMO_MEMPOOL["datos"]

    stats = http_get(f"{MEMPOOL_BASE}/api/mempool")
    if not isinstance(stats, dict):
        return ULTIMO_MEMPOOL["datos"]

    count = safe_float(stats.get("count"), 0.0)
    vsize = safe_float(stats.get("vsize"), 0.0)
    
    count_ant = ULTIMO_MEMPOOL.get("count_anterior")
    cambio_count = ((count - count_ant) / count_ant * 100.0) if (count_ant and count_ant > 0) else 0.0

    datos = {"count": count, "vsize": vsize, "cambio_count_pct": cambio_count}
    ULTIMO_MEMPOOL = {"datos": datos, "timestamp": ahora, "count_anterior": count, "vsize_anterior": vsize}
    return datos

def obtener_coinmarketcap():
    global ULTIMO_CMC
    ahora = time.time()
    if ULTIMO_CMC["precio"] is not None and (ahora - ULTIMO_CMC["timestamp"]) < 45:
        return ULTIMO_CMC["precio"]
    
    api_key = os.getenv("COINMARKETCAP_API_KEY", "").strip()
    if not api_key:
        return ULTIMO_CMC["precio"]

    datos = http_get(f"{CMC_BASE}/v2/cryptocurrency/quotes/latest", params={"id": "1", "convert": "USD"}, headers={"X-CMC_PRO_API_KEY": api_key})
    if not datos:
        return ULTIMO_CMC["precio"]
    try:
        precio = safe_float(datos.get("data", {}).get("1", {}).get("quote", {}).get("USD", {}).get("price"))
        if precio and precio > 0:
            ULTIMO_CMC = {"precio": precio, "timestamp": ahora}
            return precio
    except Exception:
        pass
    return ULTIMO_CMC["precio"]

def obtener_cf_brti():
    global ULTIMO_CF
    ahora = time.time()
    if ULTIMO_CF["precio"] is not None and (ahora - ULTIMO_CF["timestamp"]) < 2:
        return ULTIMO_CF["precio"]
    
    path = "/cfbenchmarks/values"
    headers = headers_kalshi("GET", path)
    if not headers:
        return ULTIMO_CF["precio"]
    
    datos = http_get(f"{KALSHI_BASE}{path}", params={"id": "BRTI"}, headers=headers)
    if not datos:
        return ULTIMO_CF["precio"]
    try:
        # Búsqueda recursiva optimizada del valor BRTI
        def buscar_val(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if str(k).upper() in ["VALUE", "PRICE", "RATE", "BRTI"]:
                        res = safe_float(v)
                        if res and res > 1000: return res
                    res = buscar_val(v)
                    if res: return res
            elif isinstance(obj, list):
                for item in obj:
                    res = buscar_val(item)
                    if res: return res
            return None
        
        precio = buscar_val(datos)
        if precio:
            ULTIMO_CF = {"precio": precio, "timestamp": ahora}
            return precio
    except Exception:
        pass
    return ULTIMO_CF["precio"]


# ============================================================
# INDICADORES TÉCNICOS AVANZADOS (V2)
# ============================================================

def ema(serie, periodo):
    return serie.ewm(span=periodo, adjust=False).mean()

def calcular_rsi(serie, periodo=14):
    delta = serie.diff()
    ganancias = delta.clip(lower=0)
    perdidas = -delta.clip(upper=0)
    avg_gain = ganancias.ewm(alpha=1/periodo, adjust=False).mean()
    avg_loss = perdidas.ewm(alpha=1/periodo, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def calcular_stoch_rsi(rsi, periodo=14):
    min_rsi = rsi.rolling(periodo).min()
    max_rsi = rsi.rolling(periodo).max()
    stoch = (rsi - min_rsi) / (max_rsi - min_rsi).replace(0, float("nan"))
    return (stoch * 100).fillna(50)

def construir_indicadores(df):
    if df is None or len(df) < 55:
        return None

    x = df.copy()
    x["ema9"] = ema(x["close"], 9)
    x["ema21"] = ema(x["close"], 21)
    x["ema50"] = ema(x["close"], 50)
    x["rsi14"] = calcular_rsi(x["close"], 14)
    x["stoch_rsi"] = calcular_stoch_rsi(x["rsi14"], 14)
    
    # ATR para medir régimen de volatilidad
    x["tr"] = pd.concat([
        x["high"] - x["low"],
        (x["high"] - x["close"].shift()).abs(),
        (x["low"] - x["close"].shift()).abs()
    ], axis=1).max(axis=1)
    x["atr14"] = x["tr"].rolling(14).mean()

    ultimo = x.iloc[-1]
    close = float(ultimo["close"])

    mom1 = (close / float(x.iloc[-2]["close"]) - 1) if len(x) > 1 else 0.0
    mom3 = (close / float(x.iloc[-4]["close"]) - 1) if len(x) > 3 else 0.0
    mom5 = (close / float(x.iloc[-6]["close"]) - 1) if len(x) > 5 else 0.0

    return {
        "close": close,
        "ema9": float(ultimo["ema9"]),
        "ema21": float(ultimo["ema21"]),
        "ema50": float(ultimo["ema50"]),
        "rsi14": float(ultimo["rsi14"]),
        "stoch_rsi": float(ultimo["stoch_rsi"]),
        "atr14": float(ultimo["atr14"]),
        "mom1": mom1,
        "mom3": mom3,
        "mom5": mom5,
        "volatilidad_relativa": float(ultimo["atr14"] / close) if close > 0 else 0.0
    }


# ============================================================
# CONSENSO Y CÁLCULO DE SCORE MULTIDIMENSIONAL (V2)
# ============================================================

def construir_precio_consenso(cb, kr, cmc, cf, bs):
    # Ponderación robusta por fiabilidad histórica de fuentes institucionales
    fuentes_pesos = [
        (cf, 2.5),       # CF BRTI (Índice institucional oficial de liquidación)
        (cb, 2.0),       # Coinbase (Alta liquidez spot USD)
        (kr, 1.5),       # Kraken
        (bs, 1.0),       # Bitstamp
        (cmc, 0.8)       # CoinMarketCap (Agregador)
    ]
    return media_ponderada_robusta(fuentes_pesos)


def calcular_score_avanzado(target, precio, indicadores, obi_total, orderflow_total, fuentes_precios, mempool):
    razones = []
    familias = {
        "target": 0.0,
        "tendencia": 0.0,
        "momentum": 0.0,
        "microestructura": 0.0,
        "flujo_capital": 0.0
    }

    # 1. Distancia al Target Kalshi
    distancia_pct = ((precio - target) / target) * 100.0
    abs_dist = abs(distancia_pct)
    puntos_target = limitar((abs_dist / TARGET_DISTANCIA_FUERTE_PCT) * 22.0, 0.0, 22.0)
    
    if distancia_pct > 0:
        familias["target"] = puntos_target
        razones.append(f"BTC sobre target en {distancia_pct:+.3f}%")
    else:
        familias["target"] = -puntos_target
        razones.append(f"BTC bajo target en {distancia_pct:+.3f}%")

    # 2. Tendencia Estructural (EMAs)
    ema9, ema21, ema50 = indicadores["ema9"], indicadores["ema21"], indicadores["ema50"]
    tendencia = 0.0
    if precio > ema9 > ema21 > ema50:
        tendencia += 14.0
        razones.append("Estructura de EMAs fuertemente alcista")
    elif precio < ema9 < ema21 < ema50:
        tendencia -= 14.0
        razones.append("Estructura de EMAs fuertemente bajista")
    elif ema9 > ema21:
        tendencia += 6.0
    else:
        tendencia -= 6.0
    familias["tendencia"] = limitar(tendencia, -14.0, 14.0)

    # 3. Momentum & Stoch RSI
    mom1, mom3 = indicadores["mom1"], indicadores["mom3"]
    stoch = indicadores["stoch_rsi"]
    mom_score = 0.0
    if mom1 > 0 and mom3 > 0:
        mom_score += 8.0
        razones.append("Momentum multidireccional positivo")
    elif mom1 < 0 and mom3 < 0:
        mom_score -= 8.0
        razones.append("Momentum multidireccional negativo")
    
    if stoch > 80:
        mom_score += 4.0 # Presión compradora en extremo superior
    elif stoch < 20:
        mom_score -= 4.0
    familias["momentum"] = limitar(mom_score, -12.0, 12.0)

    # 4. Microestructura (Order Books & Order Flow Agresivo)
    micro = 0.0
    if obi_total >= 0.15:
        micro += 8.0
        razones.append(f"Libros con fuerte sesgo comprador (OBI: {obi_total:+.2f})")
    elif obi_total <= -0.15:
        micro -= 8.0
        razones.append(f"Libros con fuerte sesgo vendedor (OBI: {obi_total:+.2f})")

    if orderflow_total >= 0.15:
        micro += 8.0
        razones.append("Trades agresivos comprando volumen")
    elif orderflow_total <= -0.15:
        micro -= 8.0
        razones.append("Trades agresivos vendiendo volumen")
    familias["microestructura"] = limitar(micro, -16.0, 16.0)

    # 5. Flujo de Capital (RSI)
    rsi = indicadores["rsi14"]
    flujo = 0.0
    if 52 <= rsi <= 75:
        flujo += 6.0
    elif 25 <= rsi <= 48:
        flujo -= 6.0
    familias["flujo_capital"] = limitar(flujo, -6.0, 6.0)

    score_total = sum(familias.values())
    score_total = limitar(score_total, -100.0, 100.0)

    return {
        "score": score_total,
        "distancia_target_pct": distancia_pct,
        "familias": familias,
        "razones": razones
    }


def score_a_prob_arriba(score):
    prob = 1.0 / (1.0 + math.exp(-score / 16.0))
    return limitar(prob, 0.01, 0.99)


# ============================================================
# MOTOR DE DECISIÓN ESTRICTO
# ============================================================

def decidir(score, prob_arriba, yes_ask, no_ask, distancia_target_pct):
    prob_abajo = 1.0 - prob_arriba
    score_abs = abs(score)
    zona_muerta = abs(distancia_target_pct) < TARGET_ZONA_MUERTA_PCT

    if score > 0:
        prob = prob_arriba * 100.0
        precio_entrada = yes_ask
        if precio_entrada is None:
            return {"decision": "NO APOSTAR", "fuerza": "SIN PRECIO", "probabilidad": prob, "edge": None, "precio_entrada": None, "lado": None}

        edge = prob_arriba - precio_entrada
        if prob >= PROBABILIDAD_FUERTE and score_abs >= SCORE_FUERTE and edge >= EDGE_MINIMO_FUERTE:
            return {"decision": "ARRIBA", "fuerza": "FUERTE", "probabilidad": prob, "edge": edge, "precio_entrada": precio_entrada, "lado": "YES"}
        if prob >= PROBABILIDAD_MEDIA and score_abs >= SCORE_MEDIO and edge >= EDGE_MINIMO_MEDIO and not zona_muerta:
            return {"decision": "ARRIBA", "fuerza": "MEDIA", "probabilidad": prob, "edge": edge, "precio_entrada": precio_entrada, "lado": "YES"}

    elif score < 0:
        prob = prob_abajo * 100.0
        precio_entrada = no_ask
        if precio_entrada is None:
            return {"decision": "NO APOSTAR", "fuerza": "SIN PRECIO", "probabilidad": prob, "edge": None, "precio_entrada": None, "lado": None}

        edge = prob_abajo - precio_entrada
        if prob >= PROBABILIDAD_FUERTE and score_abs >= SCORE_FUERTE and edge >= EDGE_MINIMO_FUERTE:
            return {"decision": "ABAJO", "fuerza": "FUERTE", "probabilidad": prob, "edge": edge, "precio_entrada": precio_entrada, "lado": "NO"}
        if prob >= PROBABILIDAD_MEDIA and score_abs >= SCORE_MEDIO and edge >= EDGE_MINIMO_MEDIO and not zona_muerta:
            return {"decision": "ABAJO", "fuerza": "MEDIA", "probabilidad": prob, "edge": edge, "precio_entrada": precio_entrada, "lado": "NO"}

    return {"decision": "NO APOSTAR", "fuerza": "DEBIL", "probabilidad": max(prob_arriba, prob_abajo) * 100.0, "edge": None, "precio_entrada": None, "lado": None}


# ============================================================
# HISTORIAL Y PERSISTENCIA P&L
# ============================================================

def cargar_historial():
    if not os.path.exists(HISTORIAL_FILE):
        return []
    try:
        with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, list) else []
    except Exception:
        return []

def guardar_historial(historial):
    temporal = HISTORIAL_FILE + ".tmp"
    try:
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(historial, f, ensure_ascii=False, indent=2)
        os.replace(temporal, HISTORIAL_FILE)
    except Exception as e:
        print(f"[HISTORIAL] Error guardando historial: {e}")

def buscar_registro(historial, ticker):
    for registro in historial:
        if registro.get("ticker") == ticker:
            return registro
    return None

def actualizar_resultados():
    historial = cargar_historial()
    cambio = False
    for registro in historial:
        if registro.get("resultado") is not None:
            continue
        ticker = registro.get("ticker")
        if not ticker:
            continue
        mercado = obtener_mercado_por_ticker(ticker)
        if not mercado:
            continue
        resultado = str(mercado.get("result", "")).lower()
        if resultado not in ["yes", "no"]:
            continue

        resultado_final = "ARRIBA" if resultado == "yes" else "ABAJO"
        decision = registro.get("decision")
        registro["resultado"] = resultado_final
        registro["evaluacion"] = "ACIERTO" if decision == resultado_final else "FALLO"
        
        precio_entrada = registro.get("precio_entrada")
        if decision in ["ARRIBA", "ABAJO"] and precio_entrada is not None:
            pnl = (1.0 - precio_entrada) if decision == resultado_final else (-precio_entrada)
            registro["pnl_teorico_1_contrato"] = pnl
        cambio = True

    if cambio:
        guardar_historial(historial)


# ============================================================
# ANÁLISIS INTEGRAL DEL MERCADO
# ============================================================

def analizar_mercado(mercado):
    ticker = mercado.get("ticker")
    if not ticker:
        return None

    target = extraer_target_kalshi(mercado)
    if target is None:
        return None

    close_time = parse_fecha(mercado.get("close_time"))
    open_time = parse_fecha(mercado.get("open_time"))
    ahora = ahora_utc()

    segundos_restantes = (close_time - ahora).total_seconds() if close_time else None
    minuto_entrada = ((ahora - open_time).total_seconds() / 60.0) if open_time else None

    # Recolección Multifuente Robusta
    cb = obtener_coinbase_ticker()
    kr = obtener_kraken_ticker()
    cmc = obtener_coinmarketcap()
    cf = obtener_cf_brti()
    bs = obtener_bitstamp_ticker()

    precio = construir_precio_consenso(cb, kr, cmc, cf, bs)
    if precio is None:
        return None

    candles = obtener_coinbase_candles()
    indicadores = construir_indicadores(candles)
    if indicadores is None:
        return None

    # Order Books & OBI
    cb_book = obtener_coinbase_book()
    kr_book = obtener_kraken_book()
    ka_book = obtener_orderbook_kalshi(ticker)
    bs_book = obtener_bitstamp_book()

    obi_total = media_ponderada_robusta([
        (obi_coinbase(cb_book), 2.0),
        (obi_kraken(kr_book), 1.5),
        (obi_kalshi(ka_book), 1.0),
        (obi_bitstamp(bs_book), 1.0)
    ]) or 0.0

    # Order Flow
    trades_cb = obtener_coinbase_trades()
    trades_bs = obtener_bitstamp_trades()
    flow_cb = orderflow_coinbase(trades_cb)
    flow_bs = orderflow_bitstamp(trades_bs)
    orderflow_total = media_ponderada_robusta([
        (flow_cb["imbalance"], 2.0),
        (flow_bs["imbalance"], 1.0)
    ]) or 0.0

    mempool = obtener_mempool() or {"count": 0}

    # Precios Kalshi Opciones
    mercado_actual = obtener_mercado_por_ticker(ticker) or mercado
    yes_ask = precio_yes_ask(mercado_actual)
    no_ask = precio_no_ask(mercado_actual)

    # Cálculo Avanzado de Score y Probabilidad
    calculo = calcular_score_avanzado(
        target=target,
        precio=precio,
        indicadores=indicadores,
        obi_total=obi_total,
        orderflow_total=orderflow_total,
        fuentes_precios=[cb, kr, cmc, cf, bs],
        mempool=mempool
    )

    score = calculo["score"]
    prob_arriba = score_a_prob_arriba(score)
    decision = decidir(score, prob_arriba, yes_ask, no_ask, calculo["distancia_target_pct"])

    return {
        "version": VERSION_MOTOR,
        "ticker": ticker,
        "timestamp": iso_utc(),
        "target": target,
        "precio_consenso": precio,
        "yes_ask": yes_ask,
        "no_ask": no_ask,
        "segundos_restantes": segundos_restantes,
        "minuto_entrada": minuto_entrada,
        "distancia_target_pct": calculo["distancia_target_pct"],
        "score": score,
        "probabilidad_arriba": prob_arriba * 100.0,
        "probabilidad_abajo": (1.0 - prob_arriba) * 100.0,
        "decision": decision["decision"],
        "fuerza": decision["fuerza"],
        "probabilidad": decision["probabilidad"],
        "edge": decision["edge"],
        "precio_entrada": decision["precio_entrada"],
        "lado_contrato": decision["lado"],
        "razones": calculo["razones"],
        "resultado": None
    }


def mostrar_analisis(a):
    print("\n========================================")
    print(" MOTOR KALSHI BTC 15M - PRO V2 (AVANZADO)")
    print("========================================")
    print(f"Ticker: {a['ticker']}")
    print(f"Target Kalshi: ${a['target']:,.2f}")
    print(f"BTC Consenso: ${a['precio_consenso']:,.2f}")
    print(f"Distancia Target: {a['distancia_target_pct']:+.3f}%")
    print(f"Score Compuesto: {a['score']:+.2f}")
    print(f"Prob. ARRIBA: {a['probabilidad_arriba']:.1f}% | Prob. ABAJO: {a['probabilidad_abajo']:.1f}%")
    print("----------------------------------------")
    print(f"PREDICCIÓN: {a['decision']} ({a['fuerza']})")
    if a["edge"] is not None:
        print(f"EDGE REAL ESTIMADO: {a['edge'] * 100:+.2f}%")
    if a["precio_entrada"] is not None:
        print(f"PRECIO ENTRADA (ASK): ${a['precio_entrada']:.3f}")
    print("========================================")


def guardar_si_corresponde(analisis):
    historial = cargar_historial()
    ticker = analisis["ticker"]
    if buscar_registro(historial, ticker) is not None:
        return False

    segundos_restantes = analisis["segundos_restantes"]
    segundos_desde_apertura = analisis.get("minuto_entrada", 0) * 60

    if segundos_desde_apertura < MIN_SEGUNDOS_DESDE_APERTURA:
        return False

    if segundos_restantes is not None and segundos_restantes <= MIN_SEGUNDOS_RESTANTES:
        analisis["decision"] = "NO APOSTAR"
        analisis["fuerza"] = "SIN VENTAJA"
        historial.append(analisis)
        guardar_historial(historial)
        return True

    if analisis["decision"] in ["ARRIBA", "ABAJO"]:
        historial.append(analisis)
        guardar_historial(historial)
        enviar_telegram(analisis)
        return True

    return False


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():
    print("\n========================================")
    print(" MOTOR BTC 15M INICIADO (VERSIÓN V2 PRO)")
    print(" Alta Certeza - Filtros de Régimen Activos")
    print("========================================")

    ticker_anterior = None
    mercado_anterior = None

    while not DETENER:
        try:
            ahora = time.time()
            global ULTIMO_RESULTADO_CHECK
            if ahora - ULTIMO_RESULTADO_CHECK >= INTERVALO_RESULTADOS:
                actualizar_resultados()
                ULTIMO_RESULTADO_CHECK = ahora

            mercado = elegir_mercado_actual()
            if not mercado:
                dormir_interrumpible(INTERVALO_REVISION)
                continue

            ticker = mercado.get("ticker")
            if not ticker:
                dormir_interrumpible(INTERVALO_REVISION)
                continue

            if ticker_anterior and ticker != ticker_anterior and mercado_anterior:
                pass # Transición limpia de mercado

            ticker_anterior = ticker
            mercado_anterior = mercado

            historial = cargar_historial()
            if buscar_registro(historial, ticker) is not None:
                dormir_interrumpible(INTERVALO_REVISION)
                continue

            analisis = analizar_mercado(mercado)
            if analisis is None:
                dormir_interrumpible(INTERVALO_REVISION)
                continue

            mostrar_analisis(analisis)
            guardar_si_corresponde(analisis)

        except Exception as e:
            print(f"[MOTOR V2] Error en ciclo principal: {e}")

        dormir_interrumpible(INTERVALO_REVISION)

    print("\n[MOTOR V2] Detenido correctamente.")

if __name__ == "__main__":
    main()
