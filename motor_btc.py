"""
MOTOR KALSHI BTC 15M - PROFIT ENGINE V2 CORREGIDO

Este archivo genera senales; no coloca ordenes reales.

Correcciones principales:
- Ventana unica de entrada 0:00 a 5:00 del contrato real de 15 minutos.
- Regimen ATR + ADX realmente aplicado como filtro.
- Stochastic RSI suavizado y usado como confirmacion, no como orden automatica.
- Bandas de Bollinger y proxy conservador de absorcion realmente aplicados.
- Ponderacion dinamica de fuentes por desviacion, latencia y antiguedad.
- Flujo agresivo de Coinbase corregido (el campo side es el lado maker).
- Kraken incorporado al flujo agresivo.
- Promedios de senales separados del consenso de precios para evitar division por cero.
- Spread de Kalshi comparado con el edge antes de aceptar una senal.
- Indicadores calculados con velas de un minuto ya cerradas.
"""

import base64
import json
import math
import os
import signal
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


# ============================================================
# CONFIGURACION GENERAL
# ============================================================

VERSION_MOTOR = "BTC_15M_PROFIT_ENGINE_V2_REAL_FIXED"

SERIES_TICKER = "KXBTC15M"
KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
COINBASE_BASE = "https://api.exchange.coinbase.com"
KRAKEN_BASE = "https://api.kraken.com"
CMC_BASE = "https://pro-api.coinmarketcap.com"
BITSTAMP_BASE = "https://www.bitstamp.net"
MEMPOOL_BASE = "https://mempool.space"

LOCAL_TZ = ZoneInfo("America/Chicago")
HISTORIAL_FILE = os.getenv("HISTORIAL_FILE", "historial_btc_15m_v2.json")


# ============================================================
# TIEMPO: VENTANA SOLICITADA 0:00 A 5:00
# ============================================================

DURACION_CONTRATO_SEGUNDOS = 15 * 60
VENTANA_ENTRADA_INICIO_SEGUNDOS = 0
VENTANA_ENTRADA_FIN_SEGUNDOS = 5 * 60

INTERVALO_REVISION = 5
INTERVALO_RESULTADOS = 30
TIMEOUT_HTTP = 8
MAX_WORKERS = 12


# ============================================================
# UMBRALES DEL MOTOR
# ============================================================

PROBABILIDAD_MEDIA = 70.0
PROBABILIDAD_FUERTE = 82.0

SCORE_MEDIO = 40.0
SCORE_FUERTE = 60.0

EDGE_MINIMO_MEDIO = 0.035
EDGE_MINIMO_FUERTE = 0.060

TARGET_ZONA_MUERTA_PCT = 0.008
TARGET_DISTANCIA_FUERTE_PCT = 0.040

# El spread no puede consumir una parte excesiva del edge bruto.
SPREAD_MAXIMO_KALSHI = 0.03
SPREAD_MAX_FRACCION_EDGE = 0.50
COSTO_OPERATIVO_ESTIMADO = 0.01


# ============================================================
# FILTRO DE REGIMEN ATR + ADX
# ============================================================

ADX_MINIMO_DIRECCION = 16.0
ADX_CONFIRMACION_FUERTE = 23.0
ATR_RELATIVO_MINIMO = 0.00005       # 0.005 % del BTC
ATR_RELATIVO_MAX_CHOP = 0.00200     # 0.200 % en vela de 1 minuto


# ============================================================
# CONSENSO Y MICROESTRUCTURA
# ============================================================

MIN_FUENTES_CONSENSO = 3
DESVIACION_PENALIZAR_PCT = 0.03
DESVIACION_EXCLUIR_PCT = 0.35
DISPERSION_MAXIMA_PCT = 0.20

ORDERBOOK_NIVELES = 15
TRADES_WINDOW_SEGUNDOS = 60
TRADES_MAX = 300
MIN_BOOKS_SALUDABLES = 2
MIN_FLUJOS_SALUDABLES = 2


# ============================================================
# ESTADO GLOBAL
# ============================================================

DETENER = False
ULTIMO_RESULTADO_CHECK = 0.0

ULTIMO_CMC = {"precio": None, "timestamp": 0.0}
ULTIMO_CF = {"precio": None, "timestamp": 0.0}
ULTIMO_MEMPOOL = {
    "datos": None,
    "timestamp": 0.0,
    "count_anterior": None,
    "vsize_anterior": None,
}

THREAD_LOCAL = threading.local()
EXECUTOR = ThreadPoolExecutor(max_workers=MAX_WORKERS)


# ============================================================
# SIGNAL HANDLER
# ============================================================

def manejar_senal(signum, frame):
    del signum, frame
    global DETENER
    print("\n[STOP] Senal de cancelacion recibida de forma segura.")
    DETENER = True


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, manejar_senal)
    signal.signal(signal.SIGINT, manejar_senal)


# ============================================================
# UTILIDADES
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
        numero = float(valor)
        if not math.isfinite(numero):
            return default
        return numero
    except (TypeError, ValueError, OverflowError):
        return default


def limitar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


def media_ponderada(valores_con_pesos, default=None):
    """Promedio generico. No aplica reglas de outliers de precios a senales."""
    validos = []
    for valor, peso in valores_con_pesos:
        valor = safe_float(valor)
        peso = safe_float(peso)
        if valor is None or peso is None or peso <= 0:
            continue
        validos.append((valor, peso))
    if not validos:
        return default
    suma_pesos = sum(peso for _, peso in validos)
    if suma_pesos <= 0:
        return default
    return sum(valor * peso for valor, peso in validos) / suma_pesos


def media_senal(valores_con_pesos):
    valor = media_ponderada(valores_con_pesos, default=0.0)
    return limitar(valor, -1.0, 1.0)


def dormir_interrumpible(segundos):
    final = time.monotonic() + max(0.0, segundos)
    while not DETENER and time.monotonic() < final:
        time.sleep(min(0.5, final - time.monotonic()))


# ============================================================
# HTTP CON SESION POR HILO
# ============================================================

def obtener_session():
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Kalshi-BTC-15M-Profit-Engine-V2-Real-Fixed/3.0",
            "Accept": "application/json",
        })
        THREAD_LOCAL.session = session
    return session


def http_get(url, params=None, headers=None, timeout=TIMEOUT_HTTP):
    try:
        respuesta = obtener_session().get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        respuesta.raise_for_status()
        return respuesta.json()
    except Exception as exc:
        print(f"[HTTP] Error GET {url}: {exc}")
        return None


def http_post(url, data=None, headers=None, timeout=TIMEOUT_HTTP):
    try:
        return obtener_session().post(
            url,
            data=data,
            headers=headers,
            timeout=timeout,
        )
    except Exception as exc:
        print(f"[HTTP] Error POST {url}: {exc}")
        return None


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(analisis):
    decision = analisis.get("decision")
    if decision not in ("ARRIBA", "ABAJO"):
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return

    icono = "🟢" if decision == "ARRIBA" else "🔴"
    target = safe_float(analisis.get("target"), 0.0)
    precio = safe_float(analisis.get("precio_consenso"), 0.0)
    prob = safe_float(analisis.get("probabilidad"), 0.0)
    fuerza = analisis.get("fuerza", "")
    edge = analisis.get("edge")
    spread = analisis.get("spread_kalshi")
    minuto = analisis.get("minuto_entrada")

    texto = (
        f"{icono} BTC 15M PRO V2 - {decision}\n\n"
        f"Fuerza: {fuerza}\n"
        f"Probabilidad modelo: {prob:.1f}%\n"
        f"Target Kalshi: ${target:,.2f}\n"
        f"BTC Consenso: ${precio:,.2f}\n"
    )
    if edge is not None:
        texto += f"Edge despues de friccion: {edge * 100:+.2f}%\n"
    if spread is not None:
        texto += f"Spread Kalshi: {spread * 100:.1f} centavos\n"
    if minuto is not None:
        texto += f"Minuto de entrada: {minuto:.2f} (ventana 0-5)\n"

    respuesta = http_post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": texto},
    )
    if respuesta is not None and not respuesta.ok:
        print(f"[TELEGRAM] Error HTTP: {respuesta.status_code}")


# ============================================================
# KALSHI AUTH
# ============================================================

def cargar_private_key():
    texto = os.getenv("KALSHI_PRIVATE_KEY", "").strip()
    texto_b64 = os.getenv("KALSHI_PRIVATE_KEY_BASE64", "").strip()

    if not texto and texto_b64:
        try:
            texto = base64.b64decode(texto_b64).decode("utf-8")
        except Exception as exc:
            print(f"[KALSHI AUTH] Base64 invalido: {exc}")
            return None

    if not texto:
        return None

    texto = texto.replace("\\n", "\n")
    try:
        return serialization.load_pem_private_key(
            texto.encode("utf-8"),
            password=None,
        )
    except Exception as exc:
        print(f"[KALSHI AUTH] Error cargando private key: {exc}")
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
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
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
        return datetime.fromisoformat(str(fecha).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def obtener_mercados_kalshi(status="open"):
    datos = http_get(
        f"{KALSHI_BASE}/markets",
        params={
            "series_ticker": SERIES_TICKER,
            "status": status,
            "limit": 100,
        },
    )
    return datos.get("markets", []) if isinstance(datos, dict) else []


def elegir_mercado_actual():
    mercados = obtener_mercados_kalshi("open")
    ahora = ahora_utc()
    candidatos = []
    for mercado in mercados:
        close_time = parse_fecha(mercado.get("close_time"))
        if close_time is None:
            continue
        segundos = (close_time - ahora).total_seconds()
        if segundos > 0:
            candidatos.append((segundos, mercado))
    if not candidatos:
        return None
    candidatos.sort(key=lambda item: item[0])
    return candidatos[0][1]


def obtener_mercado_por_ticker(ticker):
    datos = http_get(f"{KALSHI_BASE}/markets/{ticker}")
    if not isinstance(datos, dict):
        return None
    return datos.get("market", datos)


def extraer_target_kalshi(mercado):
    for valor in (mercado.get("floor_strike"), mercado.get("functional_strike")):
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
    numero = safe_float(valor)
    if numero is None:
        return None
    if numero > 1:
        numero /= 100.0
    return limitar(numero, 0.0, 1.0)


def obtener_precio_lado(mercado, *claves):
    for clave in claves:
        precio = convertir_precio_kalshi(mercado.get(clave))
        if precio is not None:
            return precio
    return None


def precio_yes_ask(mercado):
    return obtener_precio_lado(mercado, "yes_ask_dollars", "yes_ask")


def precio_no_ask(mercado):
    return obtener_precio_lado(mercado, "no_ask_dollars", "no_ask")


def precio_yes_bid(mercado):
    return obtener_precio_lado(mercado, "yes_bid_dollars", "yes_bid")


def precio_no_bid(mercado):
    return obtener_precio_lado(mercado, "no_bid_dollars", "no_bid")


def tiempos_contrato(mercado, referencia=None):
    """KXBTC15M dura 15 minutos; no usamos open_time para evitar avisos adelantados."""
    referencia = referencia or ahora_utc()
    close_time = parse_fecha(mercado.get("close_time"))
    if close_time is None:
        return None
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
    if not tiempos:
        return False
    segundos = tiempos["segundos_desde_inicio"]
    return VENTANA_ENTRADA_INICIO_SEGUNDOS <= segundos <= VENTANA_ENTRADA_FIN_SEGUNDOS


# ============================================================
# ORDER BOOKS
# ============================================================

def obtener_orderbook_kalshi(ticker):
    datos = http_get(f"{KALSHI_BASE}/markets/{ticker}/orderbook")
    if not isinstance(datos, dict):
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
            total += safe_float(
                nivel.get("quantity", nivel.get("count", nivel.get("quantity_fp", 0))),
                0.0,
            )
    return total


def obi_kalshi(orderbook):
    if not isinstance(orderbook, dict):
        return None
    yes = orderbook.get("yes") or orderbook.get("yes_dollars") or []
    no = orderbook.get("no") or orderbook.get("no_dollars") or []
    qty_yes = sumar_book_kalshi(yes)
    qty_no = sumar_book_kalshi(no)
    total = qty_yes + qty_no
    if total <= 0:
        return None
    return limitar((qty_yes - qty_no) / total, -1.0, 1.0)


def metricas_book_exchange(book):
    if not isinstance(book, dict):
        return {
            "obi": None,
            "bid_depth": 0.0,
            "ask_depth": 0.0,
            "spread_bps": None,
        }

    bids = book.get("bids", [])[:ORDERBOOK_NIVELES]
    asks = book.get("asks", [])[:ORDERBOOK_NIVELES]
    if not bids or not asks:
        return {
            "obi": None,
            "bid_depth": 0.0,
            "ask_depth": 0.0,
            "spread_bps": None,
        }

    best_bid = safe_float(bids[0][0]) if len(bids[0]) >= 2 else None
    best_ask = safe_float(asks[0][0]) if len(asks[0]) >= 2 else None
    if not best_bid or not best_ask or best_ask < best_bid:
        return {
            "obi": None,
            "bid_depth": 0.0,
            "ask_depth": 0.0,
            "spread_bps": None,
        }

    mid = (best_bid + best_ask) / 2.0

    def profundidad_ponderada(niveles):
        total = 0.0
        for nivel in niveles:
            if not isinstance(nivel, list) or len(nivel) < 2:
                continue
            precio = safe_float(nivel[0])
            cantidad = safe_float(nivel[1], 0.0)
            if precio is None or cantidad <= 0:
                continue
            distancia_bps = abs(precio - mid) / mid * 10000.0
            peso_cercania = 1.0 / (1.0 + distancia_bps / 5.0)
            total += cantidad * peso_cercania
        return total

    bid_depth = profundidad_ponderada(bids)
    ask_depth = profundidad_ponderada(asks)
    total_depth = bid_depth + ask_depth
    obi = ((bid_depth - ask_depth) / total_depth) if total_depth > 0 else None
    spread_bps = (best_ask - best_bid) / mid * 10000.0
    return {
        "obi": limitar(obi, -1.0, 1.0) if obi is not None else None,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "spread_bps": spread_bps,
    }


# ============================================================
# COINBASE
# ============================================================

def obtener_coinbase_ticker():
    datos = http_get(f"{COINBASE_BASE}/products/BTC-USD/ticker")
    return safe_float(datos.get("price")) if isinstance(datos, dict) else None


def obtener_coinbase_candles():
    datos = http_get(
        f"{COINBASE_BASE}/products/BTC-USD/candles",
        params={"granularity": 60},
    )
    if not isinstance(datos, list):
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
        except (TypeError, ValueError, IndexError):
            continue
    if not filas:
        return None
    return pd.DataFrame(filas).sort_values("time").reset_index(drop=True)


def obtener_coinbase_book():
    return http_get(
        f"{COINBASE_BASE}/products/BTC-USD/book",
        params={"level": 2},
    )


def obtener_coinbase_trades():
    datos = http_get(f"{COINBASE_BASE}/products/BTC-USD/trades")
    return datos if isinstance(datos, list) else []


def obi_coinbase(book):
    return metricas_book_exchange(book)["obi"]


# ============================================================
# KRAKEN
# ============================================================

def kraken_pair_key(resultado):
    if not isinstance(resultado, dict):
        return None
    for key in resultado:
        if key != "last":
            return key
    return None


def obtener_kraken_ticker():
    datos = http_get(
        f"{KRAKEN_BASE}/0/public/Ticker",
        params={"pair": "XBTUSD"},
    )
    resultado = datos.get("result", {}) if isinstance(datos, dict) else {}
    key = kraken_pair_key(resultado)
    try:
        return float(resultado[key]["c"][0]) if key else None
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def obtener_kraken_book():
    datos = http_get(
        f"{KRAKEN_BASE}/0/public/Depth",
        params={"pair": "XBTUSD", "count": ORDERBOOK_NIVELES},
    )
    resultado = datos.get("result", {}) if isinstance(datos, dict) else {}
    key = kraken_pair_key(resultado)
    return resultado.get(key) if key else None


def obtener_kraken_trades():
    datos = http_get(
        f"{KRAKEN_BASE}/0/public/Trades",
        params={"pair": "XBTUSD", "count": TRADES_MAX},
    )
    resultado = datos.get("result", {}) if isinstance(datos, dict) else {}
    key = kraken_pair_key(resultado)
    return resultado.get(key, []) if key else []


def obi_kraken(book):
    return metricas_book_exchange(book)["obi"]


# ============================================================
# BITSTAMP
# ============================================================

def obtener_bitstamp_ticker():
    datos = http_get(f"{BITSTAMP_BASE}/api/v2/ticker/btcusd/")
    return safe_float(datos.get("last")) if isinstance(datos, dict) else None


def obtener_bitstamp_book():
    return http_get(
        f"{BITSTAMP_BASE}/api/v2/order_book/btcusd/",
        params={"group": 1},
    )


def obtener_bitstamp_trades():
    datos = http_get(
        f"{BITSTAMP_BASE}/api/v2/transactions/btcusd/",
        params={"time": "minute"},
    )
    return datos[:TRADES_MAX] if isinstance(datos, list) else []


def obi_bitstamp(book):
    return metricas_book_exchange(book)["obi"]


# ============================================================
# ORDER FLOW AGRESIVO
# ============================================================

def flujo_vacio():
    return {
        "imbalance": None,
        "buy_volume": 0.0,
        "sell_volume": 0.0,
        "trades": 0,
    }


def finalizar_flujo(buy_volume, sell_volume, usados):
    total = buy_volume + sell_volume
    imbalance = (buy_volume - sell_volume) / total if total > 0 else None
    return {
        "imbalance": limitar(imbalance, -1.0, 1.0) if imbalance is not None else None,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "trades": usados,
    }


def orderflow_coinbase(trades):
    """
    Coinbase informa el lado MAKER:
    maker sell = comprador agresivo; maker buy = vendedor agresivo.
    """
    if not trades:
        return flujo_vacio()
    ahora = ahora_utc()
    buy_volume = 0.0
    sell_volume = 0.0
    usados = 0
    for trade in trades:
        try:
            fecha = parse_fecha(trade.get("time"))
            if fecha and (ahora - fecha).total_seconds() > TRADES_WINDOW_SEGUNDOS:
                continue
            size = safe_float(trade.get("size"), 0.0)
            side_maker = str(trade.get("side", "")).lower()
            if side_maker == "sell":
                buy_volume += size
                usados += 1
            elif side_maker == "buy":
                sell_volume += size
                usados += 1
        except Exception:
            continue
    return finalizar_flujo(buy_volume, sell_volume, usados)


def orderflow_kraken(trades):
    if not trades:
        return flujo_vacio()
    ahora_ts = time.time()
    buy_volume = 0.0
    sell_volume = 0.0
    usados = 0
    for trade in trades:
        try:
            if not isinstance(trade, list) or len(trade) < 4:
                continue
            timestamp = safe_float(trade[2], 0.0)
            if timestamp and (ahora_ts - timestamp) > TRADES_WINDOW_SEGUNDOS:
                continue
            volume = safe_float(trade[1], 0.0)
            side = str(trade[3]).lower()
            if side == "b":
                buy_volume += volume
                usados += 1
            elif side == "s":
                sell_volume += volume
                usados += 1
        except Exception:
            continue
    return finalizar_flujo(buy_volume, sell_volume, usados)


def orderflow_bitstamp(trades):
    if not trades:
        return flujo_vacio()
    ahora_ts = time.time()
    buy_volume = 0.0
    sell_volume = 0.0
    usados = 0
    for trade in trades:
        try:
            timestamp = safe_float(trade.get("date"), 0.0)
            if timestamp and (ahora_ts - timestamp) > TRADES_WINDOW_SEGUNDOS:
                continue
            amount = safe_float(trade.get("amount"), 0.0)
            tipo = str(trade.get("type", "")).lower()
            if tipo in ("0", "buy"):
                buy_volume += amount
                usados += 1
            elif tipo in ("1", "sell"):
                sell_volume += amount
                usados += 1
        except Exception:
            continue
    return finalizar_flujo(buy_volume, sell_volume, usados)


# ============================================================
# MEMPOOL, CMC Y CF BRTI
# ============================================================

def obtener_mempool():
    global ULTIMO_MEMPOOL
    ahora = time.time()
    if (
        ULTIMO_MEMPOOL["datos"] is not None
        and ahora - ULTIMO_MEMPOOL["timestamp"] < 20
    ):
        return ULTIMO_MEMPOOL["datos"]

    stats = http_get(f"{MEMPOOL_BASE}/api/mempool")
    if not isinstance(stats, dict):
        return ULTIMO_MEMPOOL["datos"]

    count = safe_float(stats.get("count"), 0.0)
    vsize = safe_float(stats.get("vsize"), 0.0)
    count_anterior = ULTIMO_MEMPOOL.get("count_anterior")
    vsize_anterior = ULTIMO_MEMPOOL.get("vsize_anterior")

    cambio_count = (
        (count - count_anterior) / count_anterior * 100.0
        if count_anterior and count_anterior > 0
        else 0.0
    )
    cambio_vsize = (
        (vsize - vsize_anterior) / vsize_anterior * 100.0
        if vsize_anterior and vsize_anterior > 0
        else 0.0
    )

    datos = {
        "count": count,
        "vsize": vsize,
        "cambio_count_pct": cambio_count,
        "cambio_vsize_pct": cambio_vsize,
    }
    ULTIMO_MEMPOOL = {
        "datos": datos,
        "timestamp": ahora,
        "count_anterior": count,
        "vsize_anterior": vsize,
    }
    return datos


def obtener_coinmarketcap():
    global ULTIMO_CMC
    ahora = time.time()
    if ULTIMO_CMC["precio"] is not None and ahora - ULTIMO_CMC["timestamp"] < 45:
        return ULTIMO_CMC["precio"]

    api_key = os.getenv("COINMARKETCAP_API_KEY", "").strip()
    if not api_key:
        return ULTIMO_CMC["precio"]

    datos = http_get(
        f"{CMC_BASE}/v2/cryptocurrency/quotes/latest",
        params={"id": "1", "convert": "USD"},
        headers={"X-CMC_PRO_API_KEY": api_key},
    )
    try:
        precio = safe_float(datos["data"]["1"]["quote"]["USD"]["price"])
    except (TypeError, KeyError):
        precio = None
    if precio and precio > 0:
        ULTIMO_CMC = {"precio": precio, "timestamp": ahora}
        return precio
    return ULTIMO_CMC["precio"]


def obtener_cf_brti():
    global ULTIMO_CF
    ahora = time.time()
    if ULTIMO_CF["precio"] is not None and ahora - ULTIMO_CF["timestamp"] < 2:
        return ULTIMO_CF["precio"]

    path = "/cfbenchmarks/values"
    headers = headers_kalshi("GET", path)
    if not headers:
        return ULTIMO_CF["precio"]

    datos = http_get(
        f"{KALSHI_BASE}{path}",
        params={"id": "BRTI"},
        headers=headers,
    )
    if not datos:
        return ULTIMO_CF["precio"]

    def buscar_valor(objeto):
        if isinstance(objeto, dict):
            for clave, valor in objeto.items():
                if str(clave).upper() in ("VALUE", "PRICE", "RATE", "BRTI"):
                    numero = safe_float(valor)
                    if numero and numero > 1000:
                        return numero
                encontrado = buscar_valor(valor)
                if encontrado:
                    return encontrado
        elif isinstance(objeto, list):
            for item in objeto:
                encontrado = buscar_valor(item)
                if encontrado:
                    return encontrado
        return None

    precio = buscar_valor(datos)
    if precio:
        ULTIMO_CF = {"precio": precio, "timestamp": ahora}
        return precio
    return ULTIMO_CF["precio"]


# ============================================================
# INDICADORES: ATR, ADX, STOCHASTIC RSI Y BOLLINGER
# ============================================================

def ema(serie, periodo):
    return serie.ewm(span=periodo, adjust=False).mean()


def calcular_rsi(serie, periodo=14):
    delta = serie.diff()
    ganancias = delta.clip(lower=0)
    perdidas = -delta.clip(upper=0)
    avg_gain = ganancias.ewm(alpha=1 / periodo, adjust=False).mean()
    avg_loss = perdidas.ewm(alpha=1 / periodo, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss == 0), 50.0)
    return rsi.fillna(50.0)


def calcular_stoch_rsi(rsi, periodo=14, suavizado_k=3, suavizado_d=3):
    min_rsi = rsi.rolling(periodo).min()
    max_rsi = rsi.rolling(periodo).max()
    rango = (max_rsi - min_rsi).replace(0, float("nan"))
    raw = ((rsi - min_rsi) / rango * 100.0).fillna(50.0)
    k = raw.rolling(suavizado_k).mean().fillna(50.0)
    d = k.rolling(suavizado_d).mean().fillna(50.0)
    return k, d


def calcular_adx(x, periodo=14):
    high = x["high"]
    low = x["low"]
    close = x["close"]

    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    atr = tr.ewm(alpha=1 / periodo, adjust=False, min_periods=periodo).mean()
    plus_di = 100.0 * plus_dm.ewm(
        alpha=1 / periodo,
        adjust=False,
        min_periods=periodo,
    ).mean() / atr.replace(0, float("nan"))
    minus_di = 100.0 * minus_dm.ewm(
        alpha=1 / periodo,
        adjust=False,
        min_periods=periodo,
    ).mean() / atr.replace(0, float("nan"))
    dx = 100.0 * (plus_di - minus_di).abs() / (
        plus_di + minus_di
    ).replace(0, float("nan"))
    adx = dx.ewm(alpha=1 / periodo, adjust=False, min_periods=periodo).mean()
    return tr, atr, plus_di, minus_di, adx


def quitar_vela_abierta(df):
    if df is None or df.empty:
        return None
    limite = int(time.time())
    cerradas = df[(df["time"] + 60) <= limite].copy()
    return cerradas.reset_index(drop=True)


def construir_indicadores(df):
    x = quitar_vela_abierta(df)
    if x is None or len(x) < 60:
        return None

    x["ema9"] = ema(x["close"], 9)
    x["ema21"] = ema(x["close"], 21)
    x["ema50"] = ema(x["close"], 50)
    x["rsi14"] = calcular_rsi(x["close"], 14)
    x["stoch_k"], x["stoch_d"] = calcular_stoch_rsi(x["rsi14"], 14)

    x["tr"], x["atr14"], x["plus_di"], x["minus_di"], x["adx14"] = calcular_adx(x, 14)

    x["bb_mid"] = x["close"].rolling(20).mean()
    desviacion = x["close"].rolling(20).std(ddof=0)
    x["bb_upper"] = x["bb_mid"] + 2.0 * desviacion
    x["bb_lower"] = x["bb_mid"] - 2.0 * desviacion

    ultimo = x.iloc[-1]
    anterior = x.iloc[-2]
    campos_requeridos = (
        "ema9",
        "ema21",
        "ema50",
        "rsi14",
        "stoch_k",
        "stoch_d",
        "atr14",
        "adx14",
        "plus_di",
        "minus_di",
        "bb_mid",
        "bb_upper",
        "bb_lower",
    )
    if any(safe_float(ultimo[campo]) is None for campo in campos_requeridos):
        return None

    close = float(ultimo["close"])
    bb_rango = float(ultimo["bb_upper"] - ultimo["bb_lower"])
    bb_posicion = (
        (close - float(ultimo["bb_lower"])) / bb_rango
        if bb_rango > 0
        else 0.5
    )

    atr_serie = x["atr14"].dropna().tail(50)
    atr_actual = float(ultimo["atr14"])
    atr_percentil = (
        float((atr_serie <= atr_actual).mean() * 100.0)
        if not atr_serie.empty
        else 50.0
    )

    return {
        "close": close,
        "vela_timestamp": int(ultimo["time"]),
        "ema9": float(ultimo["ema9"]),
        "ema21": float(ultimo["ema21"]),
        "ema50": float(ultimo["ema50"]),
        "rsi14": float(ultimo["rsi14"]),
        "stoch_k": float(ultimo["stoch_k"]),
        "stoch_d": float(ultimo["stoch_d"]),
        "stoch_k_anterior": float(anterior["stoch_k"]),
        "stoch_d_anterior": float(anterior["stoch_d"]),
        "atr14": atr_actual,
        "atr_relativo": atr_actual / close if close > 0 else 0.0,
        "atr_percentil": atr_percentil,
        "adx14": float(ultimo["adx14"]),
        "plus_di": float(ultimo["plus_di"]),
        "minus_di": float(ultimo["minus_di"]),
        "bb_mid": float(ultimo["bb_mid"]),
        "bb_upper": float(ultimo["bb_upper"]),
        "bb_lower": float(ultimo["bb_lower"]),
        "bb_posicion": bb_posicion,
        "mom1": close / float(x.iloc[-2]["close"]) - 1.0,
        "mom3": close / float(x.iloc[-4]["close"]) - 1.0,
        "mom5": close / float(x.iloc[-6]["close"]) - 1.0,
    }


# ============================================================
# PONDERACION DINAMICA DE FUENTES
# ============================================================

PESOS_BASE_FUENTES = {
    "CF_BRTI": 2.5,
    "COINBASE": 2.0,
    "KRAKEN": 1.5,
    "BITSTAMP": 1.0,
    "CMC": 0.8,
}


def edad_cache_fuente(nombre):
    ahora = time.time()
    if nombre == "CMC" and ULTIMO_CMC["timestamp"]:
        return max(0.0, ahora - ULTIMO_CMC["timestamp"])
    if nombre == "CF_BRTI" and ULTIMO_CF["timestamp"]:
        return max(0.0, ahora - ULTIMO_CF["timestamp"])
    return 0.0


def medir_fuente(nombre, funcion):
    inicio = time.perf_counter()
    precio = funcion()
    latencia_ms = (time.perf_counter() - inicio) * 1000.0
    return {
        "nombre": nombre,
        "precio": safe_float(precio),
        "peso_base": PESOS_BASE_FUENTES[nombre],
        "latencia_ms": latencia_ms,
        "edad_segundos": edad_cache_fuente(nombre),
    }


def construir_precio_consenso(fuentes):
    validas = [
        fuente for fuente in fuentes
        if fuente.get("precio") is not None and fuente["precio"] > 0
    ]
    if not validas:
        return None, {
            "fuentes_validas": 0,
            "dispersion_pct": None,
            "salud": [],
            "bloqueado": True,
            "motivo": "Sin fuentes de precio",
        }

    mediana = statistics.median(fuente["precio"] for fuente in validas)
    salud = []
    ponderadas = []

    for fuente in validas:
        desvio_pct = abs(fuente["precio"] - mediana) / mediana * 100.0
        if desvio_pct >= DESVIACION_EXCLUIR_PCT:
            factor_desvio = 0.0
        elif desvio_pct <= DESVIACION_PENALIZAR_PCT:
            factor_desvio = 1.0
        else:
            recorrido = DESVIACION_EXCLUIR_PCT - DESVIACION_PENALIZAR_PCT
            factor_desvio = 1.0 - (
                (desvio_pct - DESVIACION_PENALIZAR_PCT) / recorrido
            )
            factor_desvio = limitar(factor_desvio, 0.10, 1.0)

        latencia = fuente["latencia_ms"]
        if latencia <= 1000:
            factor_latencia = 1.0
        elif latencia <= 3000:
            factor_latencia = 0.75
        else:
            factor_latencia = 0.40

        edad = fuente["edad_segundos"]
        if edad <= 5:
            factor_edad = 1.0
        elif edad <= 20:
            factor_edad = 0.70
        elif edad <= 60:
            factor_edad = 0.35
        else:
            factor_edad = 0.0

        peso_final = fuente["peso_base"] * factor_desvio * factor_latencia * factor_edad
        estado = "OK" if peso_final > 0 else "EXCLUIDA"
        salud.append({
            **fuente,
            "desviacion_pct": desvio_pct,
            "peso_final": peso_final,
            "estado": estado,
        })
        if peso_final > 0:
            ponderadas.append((fuente["precio"], peso_final))

    precio = media_ponderada(ponderadas)
    usadas = [item for item in salud if item["peso_final"] > 0]
    if usadas:
        precios_usados = [item["precio"] for item in usadas]
        dispersion_pct = (
            (max(precios_usados) - min(precios_usados)) / mediana * 100.0
        )
    else:
        dispersion_pct = None

    bloqueado = (
        precio is None
        or len(usadas) < MIN_FUENTES_CONSENSO
        or dispersion_pct is None
        or dispersion_pct > DISPERSION_MAXIMA_PCT
    )
    if len(usadas) < MIN_FUENTES_CONSENSO:
        motivo = f"Solo {len(usadas)} fuentes saludables"
    elif dispersion_pct is not None and dispersion_pct > DISPERSION_MAXIMA_PCT:
        motivo = f"Fuentes dispersas: {dispersion_pct:.3f}%"
    else:
        motivo = "Consenso saludable"

    return precio, {
        "fuentes_validas": len(usadas),
        "dispersion_pct": dispersion_pct,
        "salud": salud,
        "bloqueado": bloqueado,
        "motivo": motivo,
    }


# ============================================================
# REGIMEN, ABSORCION Y SCORE
# ============================================================

def evaluar_regimen(indicadores, calidad_consenso, calidad_micro=None):
    razones = []
    bloqueado = False
    atr_rel = indicadores["atr_relativo"]
    adx = indicadores["adx14"]

    if calidad_consenso.get("bloqueado"):
        bloqueado = True
        razones.append(calidad_consenso.get("motivo", "Consenso debil"))

    if calidad_micro:
        books_validos = calidad_micro.get("books_validos", 0)
        flujos_validos = calidad_micro.get("flujos_validos", 0)
        if books_validos < MIN_BOOKS_SALUDABLES:
            bloqueado = True
            razones.append(f"Solo {books_validos} libros saludables")
        if flujos_validos < MIN_FLUJOS_SALUDABLES:
            bloqueado = True
            razones.append(f"Solo {flujos_validos} flujos saludables")

    if atr_rel < ATR_RELATIVO_MINIMO:
        bloqueado = True
        razones.append(f"ATR demasiado bajo: {atr_rel * 100:.3f}%")

    if adx < ADX_MINIMO_DIRECCION:
        bloqueado = True
        razones.append(f"ADX sin direccion: {adx:.1f}")

    if atr_rel > ATR_RELATIVO_MAX_CHOP and adx < ADX_CONFIRMACION_FUERTE:
        bloqueado = True
        razones.append(
            f"Volatilidad alta sin tendencia: ATR {atr_rel * 100:.3f}% / ADX {adx:.1f}"
        )

    if not razones:
        razones.append(f"Regimen valido: ATR {atr_rel * 100:.3f}% / ADX {adx:.1f}")

    return {
        "bloqueado": bloqueado,
        "razones": razones,
        "atr_relativo": atr_rel,
        "adx": adx,
    }


def detectar_absorcion(obi_total, orderflow_total):
    """Proxy: flujo agresivo choca contra profundidad contraria."""
    if orderflow_total <= -0.20 and obi_total >= 0.15:
        return 1.0, "Ventas agresivas absorbidas por bids"
    if orderflow_total >= 0.20 and obi_total <= -0.15:
        return -1.0, "Compras agresivas absorbidas por asks"
    return 0.0, "Sin absorcion confirmada"


def calcular_score_avanzado(
    target,
    precio,
    indicadores,
    obi_total,
    orderflow_total,
    fuentes_precios,
    mempool,
    absorcion,
):
    del fuentes_precios, mempool
    razones = []
    familias = {
        "target": 0.0,
        "tendencia_adx": 0.0,
        "momentum_stoch": 0.0,
        "bollinger": 0.0,
        "microestructura": 0.0,
        "rsi": 0.0,
    }

    distancia_pct = (precio - target) / target * 100.0
    puntos_target = limitar(
        abs(distancia_pct) / TARGET_DISTANCIA_FUERTE_PCT * 22.0,
        0.0,
        22.0,
    )
    familias["target"] = puntos_target if distancia_pct > 0 else -puntos_target
    razones.append(f"BTC frente al target: {distancia_pct:+.3f}%")

    ema9 = indicadores["ema9"]
    ema21 = indicadores["ema21"]
    ema50 = indicadores["ema50"]
    adx = indicadores["adx14"]
    plus_di = indicadores["plus_di"]
    minus_di = indicadores["minus_di"]

    tendencia = 0.0
    if precio > ema9 > ema21 > ema50 and plus_di > minus_di:
        tendencia = 12.0
        razones.append("EMAs y DI alineados al alza")
    elif precio < ema9 < ema21 < ema50 and minus_di > plus_di:
        tendencia = -12.0
        razones.append("EMAs y DI alineados a la baja")
    elif ema9 > ema21 and plus_di >= minus_di:
        tendencia = 6.0
    elif ema9 < ema21 and minus_di >= plus_di:
        tendencia = -6.0

    if tendencia > 0 and adx >= ADX_CONFIRMACION_FUERTE:
        tendencia += 4.0
    elif tendencia < 0 and adx >= ADX_CONFIRMACION_FUERTE:
        tendencia -= 4.0
    familias["tendencia_adx"] = limitar(tendencia, -16.0, 16.0)

    mom1 = indicadores["mom1"]
    mom3 = indicadores["mom3"]
    mom5 = indicadores["mom5"]
    k = indicadores["stoch_k"]
    d = indicadores["stoch_d"]
    k_ant = indicadores["stoch_k_anterior"]
    d_ant = indicadores["stoch_d_anterior"]

    momentum = 0.0
    if mom1 > 0 and mom3 > 0 and mom5 > 0:
        momentum += 8.0
        razones.append("Momentum 1/3/5 positivo")
    elif mom1 < 0 and mom3 < 0 and mom5 < 0:
        momentum -= 8.0
        razones.append("Momentum 1/3/5 negativo")

    cruce_alcista = k > d and k_ant <= d_ant
    cruce_bajista = k < d and k_ant >= d_ant
    if cruce_alcista and k < 85:
        momentum += 5.0
        razones.append("Stochastic RSI cruza al alza")
    elif cruce_bajista and k > 15:
        momentum -= 5.0
        razones.append("Stochastic RSI cruza a la baja")
    elif k > d and 20 <= k <= 80:
        momentum += 2.0
    elif k < d and 20 <= k <= 80:
        momentum -= 2.0

    if k >= 90 and k < k_ant:
        momentum -= 3.0
        razones.append("Stochastic RSI alcista agotandose")
    elif k <= 10 and k > k_ant:
        momentum += 3.0
        razones.append("Stochastic RSI bajista recuperandose")
    familias["momentum_stoch"] = limitar(momentum, -16.0, 16.0)

    bb_pos = indicadores["bb_posicion"]
    bollinger = 0.0
    if bb_pos >= 1.0 and k < d:
        bollinger -= 5.0
        razones.append("Sobreextension superior con giro bajista")
    elif bb_pos <= 0.0 and k > d:
        bollinger += 5.0
        razones.append("Sobreextension inferior con giro alcista")
    elif bb_pos >= 0.58:
        bollinger += 3.0
    elif bb_pos <= 0.42:
        bollinger -= 3.0
    familias["bollinger"] = limitar(bollinger, -5.0, 5.0)

    micro = 0.0
    if obi_total >= 0.12:
        micro += 7.0
        razones.append(f"Libros compradores: OBI {obi_total:+.2f}")
    elif obi_total <= -0.12:
        micro -= 7.0
        razones.append(f"Libros vendedores: OBI {obi_total:+.2f}")

    if orderflow_total >= 0.12:
        micro += 7.0
        razones.append(f"Compras agresivas: flujo {orderflow_total:+.2f}")
    elif orderflow_total <= -0.12:
        micro -= 7.0
        razones.append(f"Ventas agresivas: flujo {orderflow_total:+.2f}")

    if absorcion > 0:
        micro += 6.0
    elif absorcion < 0:
        micro -= 6.0
    familias["microestructura"] = limitar(micro, -20.0, 20.0)

    rsi = indicadores["rsi14"]
    rsi_score = 0.0
    if 52 <= rsi <= 70:
        rsi_score += 5.0
    elif 30 <= rsi <= 48:
        rsi_score -= 5.0
    elif rsi > 75 and mom1 < 0:
        rsi_score -= 3.0
    elif rsi < 25 and mom1 > 0:
        rsi_score += 3.0
    familias["rsi"] = limitar(rsi_score, -5.0, 5.0)

    score_total = limitar(sum(familias.values()), -100.0, 100.0)
    return {
        "score": score_total,
        "distancia_target_pct": distancia_pct,
        "familias": familias,
        "razones": razones,
    }


def score_a_prob_arriba(score):
    """Confianza heuristica del score; no es una garantia estadistica."""
    prob = 1.0 / (1.0 + math.exp(-score / 24.0))
    return limitar(prob, 0.03, 0.97)


# ============================================================
# DECISION CON SPREAD ESTRICTO
# ============================================================

def decidir(
    score,
    prob_arriba,
    yes_ask,
    no_ask,
    yes_bid,
    no_bid,
    distancia_target_pct,
    regimen,
):
    prob_abajo = 1.0 - prob_arriba
    prob_lado = prob_arriba if score >= 0 else prob_abajo
    prob_pct = prob_lado * 100.0

    base_no = {
        "decision": "NO APOSTAR",
        "fuerza": "DEBIL",
        "probabilidad": prob_pct,
        "edge": None,
        "edge_bruto": None,
        "precio_entrada": None,
        "lado": None,
        "spread_kalshi": None,
        "motivo_bloqueo": None,
    }

    if regimen.get("bloqueado"):
        base_no["fuerza"] = "REGIMEN BLOQUEADO"
        base_no["motivo_bloqueo"] = "; ".join(regimen.get("razones", []))
        return base_no

    if score == 0:
        base_no["motivo_bloqueo"] = "Score neutral"
        return base_no

    if score > 0:
        decision = "ARRIBA"
        lado = "YES"
        ask = yes_ask
        bid = yes_bid
    else:
        decision = "ABAJO"
        lado = "NO"
        ask = no_ask
        bid = no_bid

    if ask is None or bid is None:
        base_no["fuerza"] = "SIN PRECIO/SPREAD"
        base_no["motivo_bloqueo"] = "Falta bid o ask de Kalshi"
        return base_no

    if not (0.0 < ask < 1.0) or not (0.0 <= bid <= ask):
        base_no["fuerza"] = "PRECIO INVALIDO"
        base_no["motivo_bloqueo"] = "Bid/ask de Kalshi sin liquidez valida"
        return base_no

    spread = max(0.0, ask - bid)
    edge_bruto = prob_lado - ask
    edge_neto = edge_bruto - spread - COSTO_OPERATIVO_ESTIMADO
    base_no.update({
        "edge": edge_neto,
        "edge_bruto": edge_bruto,
        "precio_entrada": ask,
        "lado": lado,
        "spread_kalshi": spread,
    })

    if spread > SPREAD_MAXIMO_KALSHI:
        base_no["fuerza"] = "SPREAD ALTO"
        base_no["motivo_bloqueo"] = f"Spread {spread * 100:.1f} centavos"
        return base_no

    if edge_bruto <= 0 or spread > max(0.01, edge_bruto * SPREAD_MAX_FRACCION_EDGE):
        base_no["fuerza"] = "SPREAD CONSUME EDGE"
        base_no["motivo_bloqueo"] = "La friccion consume demasiado edge"
        return base_no

    score_abs = abs(score)
    zona_muerta = abs(distancia_target_pct) < TARGET_ZONA_MUERTA_PCT

    if (
        prob_pct >= PROBABILIDAD_FUERTE
        and score_abs >= SCORE_FUERTE
        and edge_neto >= EDGE_MINIMO_FUERTE
    ):
        return {
            **base_no,
            "decision": decision,
            "fuerza": "FUERTE",
            "motivo_bloqueo": None,
        }

    if (
        prob_pct >= PROBABILIDAD_MEDIA
        and score_abs >= SCORE_MEDIO
        and edge_neto >= EDGE_MINIMO_MEDIO
        and not zona_muerta
    ):
        return {
            **base_no,
            "decision": decision,
            "fuerza": "MEDIA",
            "motivo_bloqueo": None,
        }

    base_no["motivo_bloqueo"] = "No alcanza score, probabilidad o edge"
    return base_no


# ============================================================
# HISTORIAL Y RESULTADOS
# ============================================================

def cargar_historial():
    if not os.path.exists(HISTORIAL_FILE):
        return []
    try:
        with open(HISTORIAL_FILE, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return datos if isinstance(datos, list) else []
    except Exception as exc:
        print(f"[HISTORIAL] Error leyendo: {exc}")
        return []


def guardar_historial(historial):
    temporal = HISTORIAL_FILE + ".tmp"
    try:
        with open(temporal, "w", encoding="utf-8") as archivo:
            json.dump(historial, archivo, ensure_ascii=False, indent=2)
        os.replace(temporal, HISTORIAL_FILE)
    except Exception as exc:
        print(f"[HISTORIAL] Error guardando: {exc}")


def buscar_registro(historial, ticker):
    return next(
        (registro for registro in historial if registro.get("ticker") == ticker),
        None,
    )


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
        if resultado not in ("yes", "no"):
            continue

        resultado_final = "ARRIBA" if resultado == "yes" else "ABAJO"
        decision = registro.get("decision")
        registro["resultado"] = resultado_final
        registro["evaluacion"] = (
            "ACIERTO" if decision == resultado_final else "FALLO"
        )
        registro["resultado_actualizado_en"] = iso_utc()

        precio_entrada = safe_float(registro.get("precio_entrada"))
        if decision in ("ARRIBA", "ABAJO") and precio_entrada is not None:
            pnl = (
                1.0 - precio_entrada
                if decision == resultado_final
                else -precio_entrada
            )
            registro["pnl_bruto_teorico_1_contrato"] = pnl
        cambio = True

    if cambio:
        guardar_historial(historial)


# ============================================================
# CAPTURA PARALELA Y ANALISIS INTEGRAL
# ============================================================

def ejecutar_paralelo(tareas):
    futuros = {EXECUTOR.submit(funcion): nombre for nombre, funcion in tareas.items()}
    resultados = {}
    for futuro in as_completed(futuros):
        nombre = futuros[futuro]
        try:
            resultados[nombre] = futuro.result()
        except Exception as exc:
            print(f"[PARALELO] {nombre}: {exc}")
            resultados[nombre] = None
    return resultados


def analizar_mercado(mercado):
    ticker = mercado.get("ticker")
    target = extraer_target_kalshi(mercado)
    tiempos = tiempos_contrato(mercado)
    if not ticker or target is None or not dentro_ventana_entrada(tiempos):
        return None

    tareas_base = {
        "COINBASE": lambda: medir_fuente("COINBASE", obtener_coinbase_ticker),
        "KRAKEN": lambda: medir_fuente("KRAKEN", obtener_kraken_ticker),
        "CMC": lambda: medir_fuente("CMC", obtener_coinmarketcap),
        "CF_BRTI": lambda: medir_fuente("CF_BRTI", obtener_cf_brti),
        "BITSTAMP": lambda: medir_fuente("BITSTAMP", obtener_bitstamp_ticker),
        "candles": obtener_coinbase_candles,
    }
    base = ejecutar_paralelo(tareas_base)
    fuentes = [
        base.get(nombre)
        for nombre in ("COINBASE", "KRAKEN", "CMC", "CF_BRTI", "BITSTAMP")
        if isinstance(base.get(nombre), dict)
    ]
    precio, calidad_consenso = construir_precio_consenso(fuentes)
    indicadores = construir_indicadores(base.get("candles"))
    if precio is None or indicadores is None:
        return None

    tareas_micro = {
        "cb_book": obtener_coinbase_book,
        "kr_book": obtener_kraken_book,
        "ka_book": lambda: obtener_orderbook_kalshi(ticker),
        "bs_book": obtener_bitstamp_book,
        "cb_trades": obtener_coinbase_trades,
        "kr_trades": obtener_kraken_trades,
        "bs_trades": obtener_bitstamp_trades,
        "mempool": obtener_mempool,
        "mercado": lambda: obtener_mercado_por_ticker(ticker),
    }
    micro = ejecutar_paralelo(tareas_micro)

    cb_metricas = metricas_book_exchange(micro.get("cb_book"))
    kr_metricas = metricas_book_exchange(micro.get("kr_book"))
    bs_metricas = metricas_book_exchange(micro.get("bs_book"))
    ka_obi = obi_kalshi(micro.get("ka_book"))

    obi_total = media_senal([
        (cb_metricas["obi"], 2.0),
        (kr_metricas["obi"], 1.5),
        (ka_obi, 1.0),
        (bs_metricas["obi"], 1.0),
    ])

    flow_cb = orderflow_coinbase(micro.get("cb_trades") or [])
    flow_kr = orderflow_kraken(micro.get("kr_trades") or [])
    flow_bs = orderflow_bitstamp(micro.get("bs_trades") or [])
    orderflow_total = media_senal([
        (flow_cb["imbalance"], 2.0),
        (flow_kr["imbalance"], 1.5),
        (flow_bs["imbalance"], 1.0),
    ])

    absorcion, razon_absorcion = detectar_absorcion(obi_total, orderflow_total)
    mempool = micro.get("mempool") or {}
    mercado_actual = micro.get("mercado") or mercado

    yes_ask = precio_yes_ask(mercado_actual)
    no_ask = precio_no_ask(mercado_actual)
    yes_bid = precio_yes_bid(mercado_actual)
    no_bid = precio_no_bid(mercado_actual)

    calidad_micro = {
        "books_validos": sum(
            valor is not None
            for valor in (
                cb_metricas["obi"],
                kr_metricas["obi"],
                bs_metricas["obi"],
                ka_obi,
            )
        ),
        "flujos_validos": sum(
            valor is not None
            for valor in (
                flow_cb["imbalance"],
                flow_kr["imbalance"],
                flow_bs["imbalance"],
            )
        ),
    }

    regimen = evaluar_regimen(indicadores, calidad_consenso, calidad_micro)
    calculo = calcular_score_avanzado(
        target=target,
        precio=precio,
        indicadores=indicadores,
        obi_total=obi_total,
        orderflow_total=orderflow_total,
        fuentes_precios=fuentes,
        mempool=mempool,
        absorcion=absorcion,
    )

    score = calculo["score"]
    prob_arriba = score_a_prob_arriba(score)
    decision = decidir(
        score=score,
        prob_arriba=prob_arriba,
        yes_ask=yes_ask,
        no_ask=no_ask,
        yes_bid=yes_bid,
        no_bid=no_bid,
        distancia_target_pct=calculo["distancia_target_pct"],
        regimen=regimen,
    )

    tiempos_finales = tiempos_contrato(mercado_actual)
    if not dentro_ventana_entrada(tiempos_finales):
        return None

    return {
        "version": VERSION_MOTOR,
        "ticker": ticker,
        "timestamp": iso_utc(),
        "timestamp_local": ahora_local().isoformat(),
        "target": target,
        "precio_consenso": precio,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "inicio_contrato": tiempos_finales["inicio_real"].isoformat(),
        "close_time": tiempos_finales["close_time"].isoformat(),
        "segundos_restantes": tiempos_finales["segundos_restantes"],
        "segundos_desde_inicio": tiempos_finales["segundos_desde_inicio"],
        "minuto_entrada": tiempos_finales["minuto_entrada"],
        "ventana_entrada": "0:00-5:00",
        "distancia_target_pct": calculo["distancia_target_pct"],
        "score": score,
        "familias_score": calculo["familias"],
        "probabilidad_arriba": prob_arriba * 100.0,
        "probabilidad_abajo": (1.0 - prob_arriba) * 100.0,
        "decision": decision["decision"],
        "fuerza": decision["fuerza"],
        "probabilidad": decision["probabilidad"],
        "edge": decision["edge"],
        "edge_bruto": decision["edge_bruto"],
        "spread_kalshi": decision["spread_kalshi"],
        "precio_entrada": decision["precio_entrada"],
        "lado_contrato": decision["lado"],
        "motivo_bloqueo": decision["motivo_bloqueo"],
        "regimen": regimen,
        "indicadores": indicadores,
        "calidad_consenso": calidad_consenso,
        "microestructura": {
            "calidad": calidad_micro,
            "obi_total": obi_total,
            "orderflow_total": orderflow_total,
            "absorcion": absorcion,
            "razon_absorcion": razon_absorcion,
            "coinbase_book": cb_metricas,
            "kraken_book": kr_metricas,
            "bitstamp_book": bs_metricas,
            "kalshi_obi": ka_obi,
            "coinbase_flow": flow_cb,
            "kraken_flow": flow_kr,
            "bitstamp_flow": flow_bs,
        },
        "mempool": mempool,
        "razones": calculo["razones"] + [razon_absorcion],
        "resultado": None,
    }


def mostrar_analisis(analisis):
    print("\n========================================")
    print(" MOTOR KALSHI BTC 15M - PRO V2 REAL FIXED")
    print("========================================")
    print(f"Ticker: {analisis['ticker']}")
    print(f"Minuto: {analisis['minuto_entrada']:.2f} (ventana 0-5)")
    print(f"Target Kalshi: ${analisis['target']:,.2f}")
    print(f"BTC Consenso: ${analisis['precio_consenso']:,.2f}")
    print(f"Distancia Target: {analisis['distancia_target_pct']:+.3f}%")
    print(f"Score Compuesto: {analisis['score']:+.2f}")
    print(
        f"Prob. ARRIBA: {analisis['probabilidad_arriba']:.1f}% | "
        f"Prob. ABAJO: {analisis['probabilidad_abajo']:.1f}%"
    )
    print("----------------------------------------")
    print(f"PREDICCION: {analisis['decision']} ({analisis['fuerza']})")
    if analisis["edge"] is not None:
        print(f"EDGE DESPUES DE FRICCION: {analisis['edge'] * 100:+.2f}%")
    if analisis["spread_kalshi"] is not None:
        print(f"SPREAD KALSHI: {analisis['spread_kalshi'] * 100:.1f} centavos")
    if analisis["motivo_bloqueo"]:
        print(f"BLOQUEO: {analisis['motivo_bloqueo']}")
    print("========================================")


def guardar_si_corresponde(analisis):
    historial = cargar_historial()
    ticker = analisis["ticker"]
    if buscar_registro(historial, ticker) is not None:
        return False

    tiempos_actuales = tiempos_contrato({"close_time": analisis.get("close_time")})
    if not dentro_ventana_entrada(tiempos_actuales):
        return False

    analisis["segundos_restantes"] = tiempos_actuales["segundos_restantes"]
    analisis["segundos_desde_inicio"] = tiempos_actuales["segundos_desde_inicio"]
    analisis["minuto_entrada"] = tiempos_actuales["minuto_entrada"]

    if analisis["decision"] not in ("ARRIBA", "ABAJO"):
        return False

    historial.append(analisis)
    guardar_historial(historial)
    enviar_telegram(analisis)
    return True


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():
    global ULTIMO_RESULTADO_CHECK

    print("\n========================================")
    print(" MOTOR BTC 15M INICIADO - V2 REAL FIXED")
    print(" Ventana 0:00-5:00 | ATR + ADX activos")
    print("========================================")

    try:
        while not DETENER:
            try:
                ahora_ts = time.time()
                mercado = elegir_mercado_actual()
                ventana_activa_sin_senal = False

                if mercado:
                    ticker = mercado.get("ticker")
                    tiempos = tiempos_contrato(mercado)
                    historial = cargar_historial()
                    ya_guardado = bool(ticker and buscar_registro(historial, ticker))
                    ventana_activa_sin_senal = bool(
                        ticker and dentro_ventana_entrada(tiempos) and not ya_guardado
                    )

                    if ventana_activa_sin_senal:
                        analisis = analizar_mercado(mercado)
                        if analisis is not None:
                            mostrar_analisis(analisis)
                            guardar_si_corresponde(analisis)

                # Dentro de la ventana se prioriza la senal; los resultados
                # pendientes se actualizan al salir o despues de guardar.
                if (
                    not ventana_activa_sin_senal
                    and ahora_ts - ULTIMO_RESULTADO_CHECK >= INTERVALO_RESULTADOS
                ):
                    actualizar_resultados()
                    ULTIMO_RESULTADO_CHECK = ahora_ts

            except Exception as exc:
                print(f"[MOTOR V2] Error en ciclo principal: {exc}")

            dormir_interrumpible(INTERVALO_REVISION)
    finally:
        EXECUTOR.shutdown(wait=False, cancel_futures=True)

    print("\n[MOTOR V2] Detenido correctamente.")


if __name__ == "__main__":
    main()
