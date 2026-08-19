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

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


# ============================================================
# MOTOR KALSHI BTC 15M
# VERSION: BTC_15M_PROFIT_ENGINE_V2_PRECISION
#
# CAMBIOS V2:
# - MIN_SEGUNDOS_DESDE_APERTURA = 55
# - 3 confirmaciones consecutivas antes de guardar ARRIBA/ABAJO
# - ventana de entrada 8 a 3 minutos restantes
# - velas cerradas para indicadores
# - minimo 3 fuentes para operar
# - CF/BRTI obligatorio para operar
# - filtro de dispersion de fuentes
# - OBI spot separado de Kalshi
# - zona muerta bloquea MEDIA y FUERTE
# - probabilidad mas conservadora
# - historial guarda hora prediccion y hora resultado
# - estadisticas muestran hora de ACIERTO/FALLO
#
# ESTE ARCHIVO NO COLOCA ORDENES REALES.
# ============================================================


VERSION_MOTOR = "BTC_15M_PROFIT_ENGINE_V2_PRECISION"

SERIES_TICKER = "KXBTC15M"

KALSHI_BASE = "https://external-api.kalshi.com/trade-api/v2"
COINBASE_BASE = "https://api.exchange.coinbase.com"
KRAKEN_BASE = "https://api.kraken.com"
CMC_BASE = "https://pro-api.coinmarketcap.com"

LOCAL_TZ = ZoneInfo("America/Chicago")

HISTORIAL_FILE = "historial_btc_15m.json"

INTERVALO_REVISION = 10
INTERVALO_RESULTADOS = 30
TIMEOUT_HTTP = 10

# Pedido del usuario
MIN_SEGUNDOS_DESDE_APERTURA = 55

# Ventana para comprometer una apuesta
MAX_SEGUNDOS_RESTANTES_ENTRADA = 480  # 8 min
MIN_SEGUNDOS_RESTANTES_ENTRADA = 180  # 3 min
MIN_SEGUNDOS_RESTANTES = 120          # a los 2 min -> NO APOSTAR final

CONFIRMACIONES_REQUERIDAS = 3
MAX_SEGUNDOS_ENTRE_CONFIRMACIONES = 25

PROBABILIDAD_MEDIA = 58.0
PROBABILIDAD_FUERTE = 66.0
SCORE_MEDIO = 28.0
SCORE_FUERTE = 44.0

EDGE_MINIMO_MEDIO = 0.020
EDGE_MINIMO_FUERTE = 0.035

TARGET_ZONA_MUERTA_PCT = 0.012
TARGET_DISTANCIA_FUERTE_PCT = 0.050

ORDERBOOK_NIVELES = 10

TRADES_WINDOW_SEGUNDOS = 120
TRADES_MAX = 200

MIN_FUENTES_OPERAR = 3
REQUIERE_CF_PARA_OPERAR = True

# Máxima diferencia entre la fuente más alta y la más baja
# expresada en % del precio medio.
MAX_DISPERSION_FUENTES_PCT = 0.060

DETENER = False
ULTIMO_RESULTADO_CHECK = 0

ULTIMO_CMC = {"precio": None, "timestamp": 0}
ULTIMO_CF = {"precio": None, "timestamp": 0}

CONFIRMACIONES = {}


# ============================================================
# CONTROL
# ============================================================

def manejar_senal(signum, frame):
    global DETENER
    print("\n[STOP] Señal de cancelación recibida.")
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


def iso_local():
    return ahora_local().isoformat()


def formato_hora_local(dt=None):
    if dt is None:
        dt = ahora_local()
    return dt.strftime("%Y-%m-%d %I:%M:%S %p")


def safe_float(valor, default=None):
    try:
        if valor is None:
            return default
        return float(valor)
    except Exception:
        return default


def limitar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


def media_valida(valores):
    salida = []
    for x in valores:
        try:
            if x is None:
                continue
            valor = float(x)
            if math.isfinite(valor):
                salida.append(valor)
        except Exception:
            continue
    return statistics.mean(salida) if salida else None


def mediana_valida(valores):
    salida = []
    for x in valores:
        try:
            if x is None:
                continue
            valor = float(x)
            if math.isfinite(valor):
                salida.append(valor)
        except Exception:
            continue
    return statistics.median(salida) if salida else None


def dormir_interrumpible(segundos):
    for _ in range(int(segundos)):
        if DETENER:
            return
        time.sleep(1)


# ============================================================
# HTTP
# ============================================================

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Kalshi-BTC-15M-Profit-Engine/2.0",
    "Accept": "application/json",
})


def http_get(url, params=None, headers=None, timeout=TIMEOUT_HTTP):
    try:
        r = SESSION.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[HTTP] Error GET {url}: {e}")
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

    texto = (
        f"{icono} BTC 15M - {decision}\n\n"
        f"Fuerza: {analisis.get('fuerza')}\n"
        f"Probabilidad: {analisis.get('probabilidad', 0):.1f}%\n"
        f"Target Kalshi: ${analisis.get('target', 0):,.2f}\n"
        f"BTC: ${analisis.get('precio_consenso', 0):,.2f}\n"
        f"Hora entrada: {analisis.get('hora_prediccion_local', '-')}\n"
    )

    edge = analisis.get("edge")
    if edge is not None:
        texto += f"Edge: {edge * 100:+.2f}%\n"

    minuto = analisis.get("minuto_entrada")
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
        return serialization.load_pem_private_key(
            texto.encode("utf-8"),
            password=None,
        )
    except Exception as e:
        print(f"[KALSHI AUTH] No se pudo cargar private key: {e}")
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
    firma = firma_kalshi(
        timestamp_ms,
        method,
        "/trade-api/v2" + path,
    )

    return {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "KALSHI-ACCESS-SIGNATURE": firma,
    }


# ============================================================
# FECHAS
# ============================================================

def parse_fecha(fecha):
    if not fecha:
        return None
    try:
        return datetime.fromisoformat(fecha.replace("Z", "+00:00"))
    except Exception:
        return None


# ============================================================
# KALSHI
# ============================================================

def obtener_mercados_kalshi(status="open"):
    datos = http_get(
        f"{KALSHI_BASE}/markets",
        params={
            "series_ticker": SERIES_TICKER,
            "status": status,
            "limit": 100,
        },
    )
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
    for valor in [
        mercado.get("floor_strike"),
        mercado.get("functional_strike"),
    ]:
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
    for x in [
        mercado.get("yes_ask_dollars"),
        mercado.get("yes_ask"),
    ]:
        p = convertir_precio_kalshi(x)
        if p is not None:
            return p
    return None


def precio_no_ask(mercado):
    for x in [
        mercado.get("no_ask_dollars"),
        mercado.get("no_ask"),
    ]:
        p = convertir_precio_kalshi(x)
        if p is not None:
            return p
    return None


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
            cantidad = safe_float(
                nivel.get(
                    "quantity",
                    nivel.get(
                        "count",
                        nivel.get(
                            "quantity_fp",
                            nivel.get("count_fp", 0),
                        ),
                    ),
                ),
                0,
            )
            total += cantidad

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


def profundidad_kalshi(orderbook):
    if not orderbook:
        return {"yes": 0.0, "no": 0.0, "total": 0.0}

    yes = orderbook.get("yes") or orderbook.get("yes_dollars") or []
    no = orderbook.get("no") or orderbook.get("no_dollars") or []

    qty_yes = sumar_book_kalshi(yes)
    qty_no = sumar_book_kalshi(no)

    return {
        "yes": qty_yes,
        "no": qty_no,
        "total": qty_yes + qty_no,
    }


# ============================================================
# COINBASE
# ============================================================

def obtener_coinbase_ticker():
    datos = http_get(f"{COINBASE_BASE}/products/BTC-USD/ticker")
    if not datos:
        return None
    return safe_float(datos.get("price"))


def obtener_coinbase_candles():
    datos = http_get(
        f"{COINBASE_BASE}/products/BTC-USD/candles",
        params={"granularity": 60},
    )

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
    df = df.sort_values("time").reset_index(drop=True)

    # Usar solo velas completamente cerradas.
    ahora_ts = int(time.time())
    df = df[df["time"] + 60 <= ahora_ts].copy()

    return df.reset_index(drop=True)


def obtener_coinbase_book():
    return http_get(
        f"{COINBASE_BASE}/products/BTC-USD/book",
        params={"level": 2},
    )


def obtener_coinbase_trades():
    datos = http_get(
        f"{COINBASE_BASE}/products/BTC-USD/trades",
        params={"limit": 100},
    )

    return datos if isinstance(datos, list) else []


def obi_coinbase(book):
    if not book:
        return 0.0

    bids = book.get("bids", [])
    asks = book.get("asks", [])

    bid_qty = sum(
        safe_float(x[1], 0)
        for x in bids[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(x[1], 0)
        for x in asks[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    total = bid_qty + ask_qty
    if total <= 0:
        return 0.0

    return (bid_qty - ask_qty) / total


def profundidad_coinbase(book):
    if not book:
        return {"bid": 0.0, "ask": 0.0, "total": 0.0}

    bid_qty = sum(
        safe_float(x[1], 0)
        for x in book.get("bids", [])[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(x[1], 0)
        for x in book.get("asks", [])[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    return {
        "bid": bid_qty,
        "ask": ask_qty,
        "total": bid_qty + ask_qty,
    }


def spread_coinbase(book):
    if not book:
        return None

    try:
        best_bid = float(book["bids"][0][0])
        best_ask = float(book["asks"][0][0])
        mid = (best_bid + best_ask) / 2

        if mid <= 0:
            return None

        return (best_ask - best_bid) / mid

    except Exception:
        return None


# ============================================================
# KRAKEN
# ============================================================

def kraken_pair_key(resultado):
    if not isinstance(resultado, dict):
        return None

    for key in resultado.keys():
        if key != "last":
            return key

    return None


def obtener_kraken_ticker():
    datos = http_get(
        f"{KRAKEN_BASE}/0/public/Ticker",
        params={"pair": "XBTUSD"},
    )

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
    datos = http_get(
        f"{KRAKEN_BASE}/0/public/Depth",
        params={
            "pair": "XBTUSD",
            "count": ORDERBOOK_NIVELES,
        },
    )

    if not datos:
        return None

    resultado = datos.get("result", {})
    key = kraken_pair_key(resultado)

    if not key:
        return None

    return resultado.get(key)


def obtener_kraken_trades():
    datos = http_get(
        f"{KRAKEN_BASE}/0/public/Trades",
        params={
            "pair": "XBTUSD",
            "count": TRADES_MAX,
        },
    )

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

    bid_qty = sum(
        safe_float(x[1], 0.0)
        for x in bids[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(x[1], 0.0)
        for x in asks[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    total = bid_qty + ask_qty

    if total <= 0:
        return 0.0

    return (bid_qty - ask_qty) / total


def profundidad_kraken(book):
    if not book:
        return {"bid": 0.0, "ask": 0.0, "total": 0.0}

    bid_qty = sum(
        safe_float(x[1], 0)
        for x in book.get("bids", [])[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(x[1], 0)
        for x in book.get("asks", [])[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    return {
        "bid": bid_qty,
        "ask": ask_qty,
        "total": bid_qty + ask_qty,
    }


# ============================================================
# ORDER FLOW
# ============================================================

def orderflow_coinbase(trades):
    if not trades:
        return {
            "imbalance": 0.0,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "trades": 0,
        }

    ahora = ahora_utc()
    buy_volume = 0.0
    sell_volume = 0.0
    usados = 0

    for trade in trades:
        try:
            fecha = parse_fecha(trade.get("time"))

            if fecha:
                edad = (ahora - fecha).total_seconds()
                if edad > TRADES_WINDOW_SEGUNDOS:
                    continue

            size = safe_float(trade.get("size"), 0)
            side = str(trade.get("side", "")).lower()

            # Coinbase side representa el maker.
            if side == "sell":
                buy_volume += size
            elif side == "buy":
                sell_volume += size

            usados += 1

        except Exception:
            continue

    total = buy_volume + sell_volume
    imbalance = (
        (buy_volume - sell_volume) / total
        if total > 0
        else 0.0
    )

    return {
        "imbalance": imbalance,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "trades": usados,
    }


def orderflow_kraken(trades):
    if not trades:
        return {
            "imbalance": 0.0,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "trades": 0,
        }

    ahora_ts = time.time()
    buy_volume = 0.0
    sell_volume = 0.0
    usados = 0

    for trade in trades:
        try:
            if len(trade) < 4:
                continue

            volume = safe_float(trade[1], 0)
            timestamp = safe_float(trade[2], 0)
            side = str(trade[3]).lower()

            if timestamp and (ahora_ts - timestamp) > TRADES_WINDOW_SEGUNDOS:
                continue

            if side == "b":
                buy_volume += volume
            elif side == "s":
                sell_volume += volume

            usados += 1

        except Exception:
            continue

    total = buy_volume + sell_volume
    imbalance = (
        (buy_volume - sell_volume) / total
        if total > 0
        else 0.0
    )

    return {
        "imbalance": imbalance,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "trades": usados,
    }


# ============================================================
# COINMARKETCAP
# ============================================================

def obtener_coinmarketcap():
    global ULTIMO_CMC

    ahora = time.time()

    # CMC es fuente secundaria. Cache corto.
    if (
        ULTIMO_CMC["precio"] is not None
        and ahora - ULTIMO_CMC["timestamp"] < 30
    ):
        return ULTIMO_CMC["precio"]

    api_key = os.getenv("COINMARKETCAP_API_KEY", "").strip()

    if not api_key:
        print("[CMC] Falta COINMARKETCAP_API_KEY.")
        return ULTIMO_CMC["precio"]

    datos = http_get(
        f"{CMC_BASE}/v2/cryptocurrency/quotes/latest",
        params={"id": "1", "convert": "USD"},
        headers={
            "X-CMC_PRO_API_KEY": api_key,
            "Accept": "application/json",
        },
    )

    if not datos:
        return ULTIMO_CMC["precio"]

    try:
        data = datos.get("data")
        btc = None

        if isinstance(data, dict):
            btc = data.get("1") or data.get(1)

            if btc is None:
                for valor in data.values():
                    if (
                        isinstance(valor, dict)
                        and str(valor.get("symbol", "")).upper() == "BTC"
                    ):
                        btc = valor
                        break

        elif isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if (
                    str(item.get("id")) == "1"
                    or str(item.get("symbol", "")).upper() == "BTC"
                ):
                    btc = item
                    break

        if not isinstance(btc, dict):
            return ULTIMO_CMC["precio"]

        quote = btc.get("quote", {})
        usd = quote.get("USD") or quote.get("usd")

        if isinstance(usd, list) and usd and isinstance(usd[0], dict):
            usd = usd[0]

        if not isinstance(usd, dict):
            return ULTIMO_CMC["precio"]

        precio = safe_float(usd.get("price"))

        if precio is None or not math.isfinite(precio) or precio <= 0:
            return ULTIMO_CMC["precio"]

        ULTIMO_CMC = {
            "precio": precio,
            "timestamp": ahora,
        }

        return precio

    except Exception as e:
        print(f"[CMC] Error procesando: {e}")
        return ULTIMO_CMC["precio"]


# ============================================================
# CF BENCHMARKS / BRTI
# ============================================================

def buscar_valor_brti(objeto):
    if objeto is None:
        return None

    if isinstance(objeto, dict):
        for llave in [
            "value",
            "price",
            "rate",
            "indexValue",
            "index_value",
        ]:
            if llave in objeto:
                numero = safe_float(objeto.get(llave))
                if numero is not None and numero > 1000:
                    return numero

        for llave, valor in objeto.items():
            if str(llave).upper() == "BRTI":
                encontrado = buscar_valor_brti(valor)
                if encontrado is not None:
                    return encontrado

        for valor in objeto.values():
            encontrado = buscar_valor_brti(valor)
            if encontrado is not None:
                return encontrado

    elif isinstance(objeto, list):
        for item in objeto:
            if isinstance(item, dict):
                identificador = str(
                    item.get(
                        "id",
                        item.get(
                            "symbol",
                            item.get("ticker", ""),
                        ),
                    )
                ).upper()

                if identificador == "BRTI":
                    encontrado = buscar_valor_brti(item)
                    if encontrado is not None:
                        return encontrado

        for item in objeto:
            encontrado = buscar_valor_brti(item)
            if encontrado is not None:
                return encontrado

    return None


def obtener_cf_brti():
    global ULTIMO_CF

    ahora = time.time()

    if (
        ULTIMO_CF["precio"] is not None
        and ahora - ULTIMO_CF["timestamp"] < 2
    ):
        return ULTIMO_CF["precio"]

    path = "/cfbenchmarks/values"
    headers = headers_kalshi("GET", path)

    if headers is None:
        print("[CF BRTI] No hay autenticación Kalshi.")
        return ULTIMO_CF["precio"]

    datos = http_get(
        f"{KALSHI_BASE}{path}",
        params={"id": "BRTI"},
        headers=headers,
    )

    if not datos:
        return ULTIMO_CF["precio"]

    try:
        contenido = datos.get("data", datos)
        precio = buscar_valor_brti(contenido)

        if precio is None:
            return ULTIMO_CF["precio"]

        ULTIMO_CF = {
            "precio": precio,
            "timestamp": ahora,
        }

        return precio

    except Exception as e:
        print(f"[CF BRTI] Error procesando: {e}")
        return ULTIMO_CF["precio"]


# ============================================================
# INDICADORES
# ============================================================

def ema(serie, periodo):
    return serie.ewm(span=periodo, adjust=False).mean()


def calcular_rsi(serie, periodo=14):
    delta = serie.diff()
    ganancias = delta.clip(lower=0)
    perdidas = -delta.clip(upper=0)

    avg_gain = ganancias.ewm(
        alpha=1 / periodo,
        adjust=False,
    ).mean()

    avg_loss = perdidas.ewm(
        alpha=1 / periodo,
        adjust=False,
    ).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))

    return rsi.fillna(50)


def calcular_cmf(df, periodo=20):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    rango = (high - low).replace(0, float("nan"))

    multiplier = (
        ((close - low) - (high - close)) / rango
    ).fillna(0)

    money_flow = multiplier * volume

    cmf = (
        money_flow.rolling(periodo).sum()
        / volume.rolling(periodo).sum().replace(0, float("nan"))
    )

    return cmf.fillna(0)


def construir_indicadores(df):
    if df is None or len(df) < 55:
        return None

    x = df.copy()

    x["ema9"] = ema(x["close"], 9)
    x["ema21"] = ema(x["close"], 21)
    x["ema50"] = ema(x["close"], 50)
    x["rsi14"] = calcular_rsi(x["close"], 14)
    x["macd"] = ema(x["close"], 12) - ema(x["close"], 26)
    x["macd_signal"] = ema(x["macd"], 9)
    x["cmf20"] = calcular_cmf(x, 20)
    x["ret"] = x["close"].pct_change()
    x["vol20"] = x["ret"].rolling(20).std()
    x["volume_avg20"] = x["volume"].rolling(20).mean()

    ultimo = x.iloc[-1]
    close = float(ultimo["close"])

    def momentum(n):
        if len(x) <= n:
            return 0.0

        anterior = float(x.iloc[-1 - n]["close"])

        if anterior == 0:
            return 0.0

        return close / anterior - 1

    mom1 = momentum(1)
    mom2 = momentum(2)
    mom3 = momentum(3)
    mom5 = momentum(5)
    mom10 = momentum(10)

    velocidad = mom1

    # Mejor definición de aceleración:
    # cambio entre el retorno del último minuto y el minuto anterior.
    retorno_anterior = mom2 - mom1
    aceleracion = mom1 - retorno_anterior

    volume_actual = safe_float(ultimo["volume"], 0)
    volume_avg = safe_float(ultimo["volume_avg20"], 0)

    volumen_relativo = (
        volume_actual / volume_avg
        if volume_avg > 0
        else 1.0
    )

    return {
        "close": close,
        "ema9": float(ultimo["ema9"]),
        "ema21": float(ultimo["ema21"]),
        "ema50": float(ultimo["ema50"]),
        "rsi14": float(ultimo["rsi14"]),
        "macd": float(ultimo["macd"]),
        "macd_signal": float(ultimo["macd_signal"]),
        "cmf20": float(ultimo["cmf20"]),
        "vol20": safe_float(ultimo["vol20"], 0.0),
        "volume": volume_actual,
        "volume_avg20": volume_avg,
        "volumen_relativo": volumen_relativo,
        "mom1": mom1,
        "mom3": mom3,
        "mom5": mom5,
        "mom10": mom10,
        "velocidad": velocidad,
        "aceleracion": aceleracion,
    }


# ============================================================
# FUENTES / DISPERSION
# ============================================================

def construir_precio_consenso(coinbase, kraken, cmc, cf):
    # Mediana evita que una fuente aislada distorsione demasiado.
    return mediana_valida([coinbase, kraken, cmc, cf])


def calcular_dispersion_fuentes(fuentes):
    validas = [
        float(x)
        for x in fuentes
        if x is not None and safe_float(x) is not None
    ]

    if len(validas) < 2:
        return None

    centro = statistics.median(validas)

    if centro <= 0:
        return None

    return ((max(validas) - min(validas)) / centro) * 100.0


def calcular_consenso_fuentes(target, fuentes):
    validas = [x for x in fuentes if x is not None]

    if not validas:
        return {
            "arriba": 0,
            "abajo": 0,
            "total": 0,
            "ratio": 0.0,
        }

    arriba = sum(1 for x in validas if x > target)
    abajo = sum(1 for x in validas if x < target)
    total = len(validas)

    return {
        "arriba": arriba,
        "abajo": abajo,
        "total": total,
        "ratio": (arriba - abajo) / total,
    }


# ============================================================
# SCORE
# ============================================================

def calcular_score(
    target,
    precio,
    indicadores,
    obi_cb,
    obi_kr,
    obi_ka,
    orderflow_cb,
    orderflow_kr,
    precios_fuentes,
):
    razones = []

    familias = {
        "target": 0.0,
        "tendencia": 0.0,
        "momentum": 0.0,
        "microestructura_spot": 0.0,
        "kalshi_sentimiento": 0.0,
        "flujo_capital": 0.0,
        "consenso": 0.0,
    }

    # TARGET
    distancia_pct = ((precio - target) / target) * 100.0
    abs_distancia = abs(distancia_pct)

    puntos_target = limitar(
        (abs_distancia / TARGET_DISTANCIA_FUERTE_PCT) * 18.0,
        0.0,
        18.0,
    )

    if distancia_pct > 0:
        familias["target"] = puntos_target
        razones.append(f"BTC sobre target {distancia_pct:+.4f}%")
    elif distancia_pct < 0:
        familias["target"] = -puntos_target
        razones.append(f"BTC bajo target {distancia_pct:+.4f}%")

    # TENDENCIA
    ema9 = indicadores["ema9"]
    ema21 = indicadores["ema21"]
    ema50 = indicadores["ema50"]
    macd = indicadores["macd"]
    macd_signal = indicadores["macd_signal"]

    tendencia = 0.0

    if precio > ema9 > ema21 > ema50:
        tendencia += 10.0
        razones.append("Estructura EMA alcista")
    elif precio < ema9 < ema21 < ema50:
        tendencia -= 10.0
        razones.append("Estructura EMA bajista")
    elif ema9 > ema21:
        tendencia += 5.0
    elif ema9 < ema21:
        tendencia -= 5.0

    if macd > macd_signal:
        tendencia += 4.0
    elif macd < macd_signal:
        tendencia -= 4.0

    familias["tendencia"] = limitar(tendencia, -14.0, 14.0)

    # MOMENTUM
    moms = [
        indicadores["mom1"],
        indicadores["mom3"],
        indicadores["mom5"],
        indicadores["mom10"],
    ]

    votos_up = sum(1 for x in moms if x > 0)
    votos_down = sum(1 for x in moms if x < 0)

    velocidad = indicadores["velocidad"]
    aceleracion = indicadores["aceleracion"]

    momentum_score = 0.0

    if votos_up >= 3:
        momentum_score += 7.0
        razones.append("Momentum mayormente alcista")
    elif votos_down >= 3:
        momentum_score -= 7.0
        razones.append("Momentum mayormente bajista")

    if velocidad > 0:
        momentum_score += 3.0
    elif velocidad < 0:
        momentum_score -= 3.0

    if velocidad > 0 and aceleracion > 0:
        momentum_score += 3.0
        razones.append("Precio acelerando arriba")
    elif velocidad < 0 and aceleracion < 0:
        momentum_score -= 3.0
        razones.append("Precio acelerando abajo")

    familias["momentum"] = limitar(momentum_score, -13.0, 13.0)

    # MICROESTRUCTURA SPOT
    obi_spot = media_valida([obi_cb, obi_kr])
    if obi_spot is None:
        obi_spot = 0.0

    flujo_cb = orderflow_cb.get("imbalance", 0.0)
    flujo_kr = orderflow_kr.get("imbalance", 0.0)

    orderflow_total = media_valida([flujo_cb, flujo_kr])
    if orderflow_total is None:
        orderflow_total = 0.0

    micro = 0.0

    if obi_spot >= 0.20:
        micro += 7.0
        razones.append("Order books spot compradores")
    elif obi_spot >= 0.08:
        micro += 4.0
    elif obi_spot <= -0.20:
        micro -= 7.0
        razones.append("Order books spot vendedores")
    elif obi_spot <= -0.08:
        micro -= 4.0

    if orderflow_total >= 0.20:
        micro += 7.0
        razones.append("Trades agresivos compradores")
    elif orderflow_total >= 0.08:
        micro += 4.0
    elif orderflow_total <= -0.20:
        micro -= 7.0
        razones.append("Trades agresivos vendedores")
    elif orderflow_total <= -0.08:
        micro -= 4.0

    if obi_spot > 0.08 and orderflow_total > 0.08:
        micro += 2.0
    elif obi_spot < -0.08 and orderflow_total < -0.08:
        micro -= 2.0

    familias["microestructura_spot"] = limitar(micro, -16.0, 16.0)

    # KALSHI SENTIMIENTO - SEPARADO DEL OBI SPOT
    kalshi_sent = 0.0

    if obi_ka >= 0.25:
        kalshi_sent = 4.0
        razones.append("Book Kalshi favorece YES")
    elif obi_ka >= 0.10:
        kalshi_sent = 2.0
    elif obi_ka <= -0.25:
        kalshi_sent = -4.0
        razones.append("Book Kalshi favorece NO")
    elif obi_ka <= -0.10:
        kalshi_sent = -2.0

    familias["kalshi_sentimiento"] = kalshi_sent

    # FLUJO CAPITAL
    rsi = indicadores["rsi14"]
    cmf = indicadores["cmf20"]
    volumen_relativo = indicadores["volumen_relativo"]

    flujo_capital = 0.0

    if 55 <= rsi <= 72:
        flujo_capital += 3.0
    elif 28 <= rsi <= 45:
        flujo_capital -= 3.0
    elif rsi > 80:
        flujo_capital -= 1.0
    elif rsi < 20:
        flujo_capital += 1.0

    if cmf > 0.10:
        flujo_capital += 5.0
    elif cmf < -0.10:
        flujo_capital -= 5.0

    if volumen_relativo >= 1.50:
        direccion_base = (
            familias["tendencia"]
            + familias["momentum"]
        )

        if direccion_base > 0:
            flujo_capital += 2.0
        elif direccion_base < 0:
            flujo_capital -= 2.0

    familias["flujo_capital"] = limitar(
        flujo_capital,
        -10.0,
        10.0,
    )

    # CONSENSO
    consenso = calcular_consenso_fuentes(
        target,
        precios_fuentes,
    )

    consenso_score = 0.0

    # Máximo consenso solo con 4 fuentes.
    if consenso["total"] == 4:
        if consenso["arriba"] == 4:
            consenso_score = 10.0
            razones.append("4/4 fuentes sobre target")
        elif consenso["abajo"] == 4:
            consenso_score = -10.0
            razones.append("4/4 fuentes bajo target")
        elif consenso["arriba"] == 3:
            consenso_score = 6.0
            razones.append("3/4 fuentes arriba")
        elif consenso["abajo"] == 3:
            consenso_score = -6.0
            razones.append("3/4 fuentes abajo")

    elif consenso["total"] == 3:
        if consenso["arriba"] == 3:
            consenso_score = 5.0
            razones.append("3/3 fuentes disponibles arriba")
        elif consenso["abajo"] == 3:
            consenso_score = -5.0
            razones.append("3/3 fuentes disponibles abajo")
        elif consenso["arriba"] == 2:
            consenso_score = 2.0
        elif consenso["abajo"] == 2:
            consenso_score = -2.0

    familias["consenso"] = consenso_score

    score = limitar(
        sum(familias.values()),
        -100.0,
        100.0,
    )

    return {
        "score": score,
        "distancia_target_pct": distancia_pct,
        "obi_spot": obi_spot,
        "obi_kalshi": obi_ka,
        "orderflow": orderflow_total,
        "consenso": consenso,
        "familias": familias,
        "razones": razones,
    }


# ============================================================
# SCORE -> PROBABILIDAD
# ============================================================

def score_a_prob_arriba(score):
    # Más conservadora que V1.
    # Sigue siendo estimación heurística hasta disponer de historial
    # suficiente para calibración estadística real.
    prob = 1.0 / (1.0 + math.exp(-score / 28.0))

    return limitar(prob, 0.10, 0.90)


# ============================================================
# DECISION
# ============================================================

def decidir(
    score,
    prob_arriba,
    yes_ask,
    no_ask,
    distancia_target_pct,
    fuentes_disponibles,
    cf_disponible,
    dispersion_fuentes_pct,
):
    prob_abajo = 1.0 - prob_arriba
    score_abs = abs(score)

    zona_muerta = (
        abs(distancia_target_pct)
        < TARGET_ZONA_MUERTA_PCT
    )

    # Filtros duros de calidad
    if fuentes_disponibles < MIN_FUENTES_OPERAR:
        return {
            "decision": "NO APOSTAR",
            "fuerza": "POCAS FUENTES",
            "probabilidad": max(prob_arriba, prob_abajo) * 100.0,
            "edge": None,
            "precio_entrada": None,
            "lado": None,
        }

    if REQUIERE_CF_PARA_OPERAR and not cf_disponible:
        return {
            "decision": "NO APOSTAR",
            "fuerza": "SIN CF/BRTI",
            "probabilidad": max(prob_arriba, prob_abajo) * 100.0,
            "edge": None,
            "precio_entrada": None,
            "lado": None,
        }

    if (
        dispersion_fuentes_pct is not None
        and dispersion_fuentes_pct > MAX_DISPERSION_FUENTES_PCT
    ):
        return {
            "decision": "NO APOSTAR",
            "fuerza": "FUENTES DISPERSAS",
            "probabilidad": max(prob_arriba, prob_abajo) * 100.0,
            "edge": None,
            "precio_entrada": None,
            "lado": None,
        }

    # Zona muerta bloquea MEDIA Y FUERTE.
    if zona_muerta:
        return {
            "decision": "NO APOSTAR",
            "fuerza": "CERCA DEL TARGET",
            "probabilidad": max(prob_arriba, prob_abajo) * 100.0,
            "edge": None,
            "precio_entrada": None,
            "lado": None,
        }

    if score > 0:
        prob = prob_arriba * 100.0

        if yes_ask is None:
            return {
                "decision": "NO APOSTAR",
                "fuerza": "SIN PRECIO",
                "probabilidad": prob,
                "edge": None,
                "precio_entrada": None,
                "lado": None,
            }

        edge = prob_arriba - yes_ask

        if (
            prob >= PROBABILIDAD_FUERTE
            and score_abs >= SCORE_FUERTE
            and edge >= EDGE_MINIMO_FUERTE
        ):
            return {
                "decision": "ARRIBA",
                "fuerza": "FUERTE",
                "probabilidad": prob,
                "edge": edge,
                "precio_entrada": yes_ask,
                "lado": "YES",
            }

        if (
            prob >= PROBABILIDAD_MEDIA
            and score_abs >= SCORE_MEDIO
            and edge >= EDGE_MINIMO_MEDIO
        ):
            return {
                "decision": "ARRIBA",
                "fuerza": "MEDIA",
                "probabilidad": prob,
                "edge": edge,
                "precio_entrada": yes_ask,
                "lado": "YES",
            }

    if score < 0:
        prob = prob_abajo * 100.0

        if no_ask is None:
            return {
                "decision": "NO APOSTAR",
                "fuerza": "SIN PRECIO",
                "probabilidad": prob,
                "edge": None,
                "precio_entrada": None,
                "lado": None,
            }

        edge = prob_abajo - no_ask

        if (
            prob >= PROBABILIDAD_FUERTE
            and score_abs >= SCORE_FUERTE
            and edge >= EDGE_MINIMO_FUERTE
        ):
            return {
                "decision": "ABAJO",
                "fuerza": "FUERTE",
                "probabilidad": prob,
                "edge": edge,
                "precio_entrada": no_ask,
                "lado": "NO",
            }

        if (
            prob >= PROBABILIDAD_MEDIA
            and score_abs >= SCORE_MEDIO
            and edge >= EDGE_MINIMO_MEDIO
        ):
            return {
                "decision": "ABAJO",
                "fuerza": "MEDIA",
                "probabilidad": prob,
                "edge": edge,
                "precio_entrada": no_ask,
                "lado": "NO",
            }

    return {
        "decision": "NO APOSTAR",
        "fuerza": "DEBIL",
        "probabilidad": max(prob_arriba, prob_abajo) * 100.0,
        "edge": None,
        "precio_entrada": None,
        "lado": None,
    }


# ============================================================
# CONFIRMACIONES
# ============================================================

def registrar_confirmacion(ticker, decision):
    ahora = time.time()

    estado = CONFIRMACIONES.get(ticker)

    if decision not in ("ARRIBA", "ABAJO"):
        CONFIRMACIONES.pop(ticker, None)
        return 0

    if not estado:
        CONFIRMACIONES[ticker] = {
            "decision": decision,
            "contador": 1,
            "timestamp": ahora,
        }
        return 1

    misma = estado.get("decision") == decision
    reciente = (
        ahora - estado.get("timestamp", 0)
        <= MAX_SEGUNDOS_ENTRE_CONFIRMACIONES
    )

    if misma and reciente:
        estado["contador"] += 1
        estado["timestamp"] = ahora
        return estado["contador"]

    CONFIRMACIONES[ticker] = {
        "decision": decision,
        "contador": 1,
        "timestamp": ahora,
    }

    return 1


def limpiar_confirmacion(ticker):
    CONFIRMACIONES.pop(ticker, None)


# ============================================================
# HISTORIAL
# ============================================================

def cargar_historial():
    if not os.path.exists(HISTORIAL_FILE):
        return []

    try:
        with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
            datos = json.load(f)

        if isinstance(datos, list):
            return datos

    except Exception as e:
        print(f"[HISTORIAL] Error leyendo: {e}")

    return []


def guardar_historial(historial):
    temporal = HISTORIAL_FILE + ".tmp"

    try:
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(
                historial,
                f,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(temporal, HISTORIAL_FILE)

    except Exception as e:
        print(f"[HISTORIAL] Error guardando: {e}")


def buscar_registro(historial, ticker):
    for registro in historial:
        if registro.get("ticker") == ticker:
            return registro
    return None


# ============================================================
# P&L
# ============================================================

def calcular_pnl_teorico(
    decision,
    resultado_final,
    precio_entrada,
):
    if decision not in ("ARRIBA", "ABAJO"):
        return None

    if precio_entrada is None:
        return None

    if decision == resultado_final:
        return 1.0 - precio_entrada

    return -precio_entrada


# ============================================================
# RESULTADO OFICIAL
# ============================================================

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

        resultado_final = (
            "ARRIBA"
            if resultado == "yes"
            else "ABAJO"
        )

        decision = registro.get("decision")

        fecha_resultado_utc = iso_utc()
        fecha_resultado_local = iso_local()
        hora_resultado_local = formato_hora_local()

        registro["resultado"] = resultado_final
        registro["resultado_kalshi"] = resultado
        registro["resultado_actualizado"] = fecha_resultado_utc

        # NUEVO: horario visible del resultado
        registro["resultado_hora_local"] = hora_resultado_local
        registro["resultado_timestamp_local"] = fecha_resultado_local

        if decision == "NO APOSTAR":
            registro["evaluacion"] = "NO CONTABILIZA"
            registro["pnl_teorico_1_contrato"] = None

        elif decision == resultado_final:
            registro["evaluacion"] = "ACIERTO"
            registro["pnl_teorico_1_contrato"] = calcular_pnl_teorico(
                decision,
                resultado_final,
                registro.get("precio_entrada"),
            )

        else:
            registro["evaluacion"] = "FALLO"
            registro["pnl_teorico_1_contrato"] = calcular_pnl_teorico(
                decision,
                resultado_final,
                registro.get("precio_entrada"),
            )

        precio_entrada = registro.get("precio_entrada")
        pnl = registro.get("pnl_teorico_1_contrato")

        if (
            precio_entrada is not None
            and precio_entrada > 0
            and pnl is not None
        ):
            registro["roi_teorico_pct"] = (
                pnl / precio_entrada
            ) * 100.0
        else:
            registro["roi_teorico_pct"] = None

        cambio = True

        print("\n========================================")
        print("[RESULTADO KALSHI]")
        print(f"Ticker: {ticker}")
        print(f"Predicción: {decision}")
        print(f"Resultado oficial: {resultado_final}")
        print(f"Evaluación: {registro['evaluacion']}")
        print(
            "Hora predicción: "
            f"{registro.get('hora_prediccion_local', '-')}"
        )
        print(
            "Hora resultado: "
            f"{registro.get('resultado_hora_local', '-')}"
        )

        if registro.get("pnl_teorico_1_contrato") is not None:
            print(
                "P&L teórico: "
                f"${registro['pnl_teorico_1_contrato']:+.4f}"
            )

        print("========================================\n")

    if cambio:
        guardar_historial(historial)


# ============================================================
# ANALISIS
# ============================================================

def analizar_mercado(mercado):
    ticker = mercado.get("ticker")

    if not ticker:
        return None

    target = extraer_target_kalshi(mercado)

    if target is None:
        print("[KALSHI] Mercado sin target.")
        return None

    close_time = parse_fecha(mercado.get("close_time"))
    open_time = parse_fecha(mercado.get("open_time"))

    ahora = ahora_utc()

    segundos_restantes = None
    segundos_desde_apertura = None
    minuto_entrada = None

    if close_time is not None:
        segundos_restantes = (close_time - ahora).total_seconds()

    if open_time is not None:
        segundos_desde_apertura = (ahora - open_time).total_seconds()
        minuto_entrada = segundos_desde_apertura / 60.0

    cb = obtener_coinbase_ticker()
    kr = obtener_kraken_ticker()
    cmc = obtener_coinmarketcap()
    cf = obtener_cf_brti()

    fuentes = [cb, kr, cmc, cf]

    precio = construir_precio_consenso(
        cb,
        kr,
        cmc,
        cf,
    )

    fuentes_disponibles = sum(
        1
        for x in fuentes
        if x is not None
    )

    if precio is None or fuentes_disponibles < 2:
        print("[PRECIO] No hay suficientes fuentes.")
        return None

    dispersion_fuentes_pct = calcular_dispersion_fuentes(
        fuentes
    )

    candles = obtener_coinbase_candles()
    indicadores = construir_indicadores(candles)

    if indicadores is None:
        print("[INDICADORES] No hay suficientes velas cerradas.")
        return None

    cb_book = obtener_coinbase_book()
    kr_book = obtener_kraken_book()
    ka_book = obtener_orderbook_kalshi(ticker)

    obi_cb = obi_coinbase(cb_book)
    obi_kr = obi_kraken(kr_book)
    obi_ka = obi_kalshi(ka_book)

    profundidad_cb = profundidad_coinbase(cb_book)
    profundidad_kr = profundidad_kraken(kr_book)
    profundidad_ka = profundidad_kalshi(ka_book)

    spread_cb = spread_coinbase(cb_book)

    trades_cb = obtener_coinbase_trades()
    trades_kr = obtener_kraken_trades()

    flujo_cb = orderflow_coinbase(trades_cb)
    flujo_kr = orderflow_kraken(trades_kr)

    mercado_actual = obtener_mercado_por_ticker(ticker) or mercado

    yes_ask = precio_yes_ask(mercado_actual)
    no_ask = precio_no_ask(mercado_actual)

    calculo = calcular_score(
        target=target,
        precio=precio,
        indicadores=indicadores,
        obi_cb=obi_cb,
        obi_kr=obi_kr,
        obi_ka=obi_ka,
        orderflow_cb=flujo_cb,
        orderflow_kr=flujo_kr,
        precios_fuentes=fuentes,
    )

    score = calculo["score"]
    prob_arriba = score_a_prob_arriba(score)

    decision = decidir(
        score=score,
        prob_arriba=prob_arriba,
        yes_ask=yes_ask,
        no_ask=no_ask,
        distancia_target_pct=calculo["distancia_target_pct"],
        fuentes_disponibles=fuentes_disponibles,
        cf_disponible=(cf is not None),
        dispersion_fuentes_pct=dispersion_fuentes_pct,
    )

    fecha_pred_utc = iso_utc()
    fecha_pred_local = iso_local()
    hora_pred_local = formato_hora_local()

    return {
        "version": VERSION_MOTOR,
        "ticker": ticker,
        "event_ticker": mercado.get("event_ticker"),
        "timestamp": fecha_pred_utc,
        "hora_local": fecha_pred_local,

        # NUEVO: horario fácil de mostrar en app/historial
        "hora_prediccion_local": hora_pred_local,
        "prediccion_timestamp_local": fecha_pred_local,

        "target": target,
        "precio_consenso": precio,
        "precio_cf_brti": cf,
        "precio_coinbase": cb,
        "precio_kraken": kr,
        "precio_coinmarketcap": cmc,
        "fuentes_disponibles": fuentes_disponibles,
        "dispersion_fuentes_pct": dispersion_fuentes_pct,

        "yes_ask": yes_ask,
        "no_ask": no_ask,
        "precio_entrada": decision["precio_entrada"],
        "lado_contrato": decision["lado"],

        "segundos_restantes": segundos_restantes,
        "segundos_desde_apertura": segundos_desde_apertura,
        "minuto_entrada": minuto_entrada,

        "distancia_target_pct": calculo["distancia_target_pct"],
        "score": score,
        "score_familias": calculo["familias"],

        "probabilidad_arriba": prob_arriba * 100.0,
        "probabilidad_abajo": (1.0 - prob_arriba) * 100.0,

        "decision": decision["decision"],
        "fuerza": decision["fuerza"],
        "probabilidad": decision["probabilidad"],
        "edge": decision["edge"],

        "ema9": indicadores["ema9"],
        "ema21": indicadores["ema21"],
        "ema50": indicadores["ema50"],
        "rsi14": indicadores["rsi14"],
        "macd": indicadores["macd"],
        "macd_signal": indicadores["macd_signal"],
        "cmf20": indicadores["cmf20"],

        "momentum_1m": indicadores["mom1"],
        "momentum_3m": indicadores["mom3"],
        "momentum_5m": indicadores["mom5"],
        "momentum_10m": indicadores["mom10"],

        "velocidad": indicadores["velocidad"],
        "aceleracion": indicadores["aceleracion"],
        "volatilidad20": indicadores["vol20"],
        "volumen": indicadores["volume"],
        "volumen_promedio20": indicadores["volume_avg20"],
        "volumen_relativo": indicadores["volumen_relativo"],

        "obi_coinbase": obi_cb,
        "obi_kraken": obi_kr,
        "obi_kalshi": obi_ka,
        "obi_spot_promedio": calculo["obi_spot"],

        "orderflow_coinbase": flujo_cb,
        "orderflow_kraken": flujo_kr,
        "orderflow_promedio": calculo["orderflow"],

        "profundidad_coinbase": profundidad_cb,
        "profundidad_kraken": profundidad_kr,
        "profundidad_kalshi": profundidad_ka,
        "spread_coinbase": spread_cb,

        "consenso_fuentes": calculo["consenso"],
        "razones": calculo["razones"],

        "confirmaciones": 0,

        "resultado": None,
        "resultado_kalshi": None,
        "resultado_actualizado": None,

        # NUEVO
        "resultado_hora_local": None,
        "resultado_timestamp_local": None,

        "evaluacion": None,
        "pnl_teorico_1_contrato": None,
        "roi_teorico_pct": None,
    }


# ============================================================
# MOSTRAR ANALISIS
# ============================================================

def mostrar_analisis(a):
    print("\n========================================")
    print(" MOTOR KALSHI BTC 15M")
    print("========================================")
    print(f"Ticker: {a['ticker']}")
    print(f"Target Kalshi: ${a['target']:,.2f}")
    print(f"BTC consenso: ${a['precio_consenso']:,.2f}")
    print(f"Distancia target: {a['distancia_target_pct']:+.4f}%")
    print(f"Fuentes disponibles: {a['fuentes_disponibles']}")

    dispersion = a.get("dispersion_fuentes_pct")
    if dispersion is not None:
        print(f"Dispersión fuentes: {dispersion:.4f}%")

    print("")
    print(f"CF BRTI: {a['precio_cf_brti']}")
    print(f"Coinbase: {a['precio_coinbase']}")
    print(f"Kraken: {a['precio_kraken']}")
    print(f"CoinMarketCap: {a['precio_coinmarketcap']}")

    print("")
    print(f"EMA 9: {a['ema9']:.2f}")
    print(f"EMA 21: {a['ema21']:.2f}")
    print(f"EMA 50: {a['ema50']:.2f}")
    print(f"RSI 14: {a['rsi14']:.2f}")
    print(f"CMF 20: {a['cmf20']:+.3f}")
    print(f"Volumen relativo: {a['volumen_relativo']:.2f}x")
    print(f"Velocidad: {a['velocidad'] * 100:+.4f}%")
    print(f"Aceleración: {a['aceleracion'] * 100:+.4f}%")

    print("")
    print(f"OBI Coinbase: {a['obi_coinbase']:+.3f}")
    print(f"OBI Kraken: {a['obi_kraken']:+.3f}")
    print(f"OBI Spot promedio: {a['obi_spot_promedio']:+.3f}")
    print(f"OBI Kalshi: {a['obi_kalshi']:+.3f}")
    print(
        "Order flow Coinbase: "
        f"{a['orderflow_coinbase']['imbalance']:+.3f}"
    )
    print(
        "Order flow Kraken: "
        f"{a['orderflow_kraken']['imbalance']:+.3f}"
    )
    print(f"Order flow promedio: {a['orderflow_promedio']:+.3f}")

    print("")
    print(f"Score: {a['score']:+.2f}")
    print(f"Prob. ARRIBA: {a['probabilidad_arriba']:.1f}%")
    print(f"Prob. ABAJO: {a['probabilidad_abajo']:.1f}%")
    print(f"Kalshi YES ask: {a['yes_ask']}")
    print(f"Kalshi NO ask: {a['no_ask']}")

    print("")
    print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    print(f"PREDICCION: {a['decision']}")
    print(f"FUERZA: {a['fuerza']}")
    print(f"PROBABILIDAD: {a['probabilidad']:.1f}%")
    print(f"HORA: {a['hora_prediccion_local']}")

    if a["precio_entrada"] is not None:
        print(f"PRECIO ENTRADA: ${a['precio_entrada']:.3f}")

    if a["edge"] is not None:
        print(f"EDGE ESTIMADO: {a['edge'] * 100:+.2f}%")

    print("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")

    if a["minuto_entrada"] is not None:
        print(f"Minuto del contrato: {a['minuto_entrada']:.2f}")

    if a["segundos_restantes"] is not None:
        print(f"Tiempo restante: {int(a['segundos_restantes'])} s")

    print("========================================\n")


# ============================================================
# GUARDAR DECISION
# ============================================================

def guardar_si_corresponde(analisis):
    historial = cargar_historial()

    ticker = analisis["ticker"]

    if buscar_registro(historial, ticker) is not None:
        limpiar_confirmacion(ticker)
        return False

    segundos_restantes = analisis["segundos_restantes"]
    segundos_desde_apertura = analisis["segundos_desde_apertura"]

    # No guardar antes de 55 segundos.
    if (
        segundos_desde_apertura is not None
        and segundos_desde_apertura < MIN_SEGUNDOS_DESDE_APERTURA
    ):
        limpiar_confirmacion(ticker)
        return False

    # Si quedan <= 2 min y nunca apareció señal confirmada:
    # cerrar como NO APOSTAR.
    if (
        segundos_restantes is not None
        and segundos_restantes <= MIN_SEGUNDOS_RESTANTES
    ):
        limpiar_confirmacion(ticker)

        analisis["decision"] = "NO APOSTAR"
        analisis["fuerza"] = "SIN VENTAJA"
        analisis["precio_entrada"] = None
        analisis["lado_contrato"] = None
        analisis["edge"] = None
        analisis["confirmaciones"] = 0

        historial.append(analisis)
        guardar_historial(historial)

        print("[FINAL] Contrato guardado como NO APOSTAR.")
        return True

    # Fuera de la ventana de entrada: analiza, pero NO compromete.
    if segundos_restantes is not None:
        if segundos_restantes > MAX_SEGUNDOS_RESTANTES_ENTRADA:
            limpiar_confirmacion(ticker)
            print(
                "[ESPERA] Aún demasiado temprano para guardar. "
                f"Quedan {int(segundos_restantes)} s."
            )
            return False

        if segundos_restantes < MIN_SEGUNDOS_RESTANTES_ENTRADA:
            limpiar_confirmacion(ticker)
            print(
                "[ESPERA] Fuera de ventana de entrada. "
                "Se acerca al cierre final."
            )
            return False

    decision = analisis["decision"]

    if decision not in ("ARRIBA", "ABAJO"):
        limpiar_confirmacion(ticker)
        return False

    confirmaciones = registrar_confirmacion(
        ticker,
        decision,
    )

    analisis["confirmaciones"] = confirmaciones

    print(
        f"[CONFIRMACION] {decision} "
        f"{confirmaciones}/{CONFIRMACIONES_REQUERIDAS}"
    )

    if confirmaciones < CONFIRMACIONES_REQUERIDAS:
        return False

    historial.append(analisis)
    guardar_historial(historial)
    limpiar_confirmacion(ticker)

    print(
        "[DECISION GUARDADA] "
        f"{analisis['decision']} | "
        f"{analisis['hora_prediccion_local']}"
    )

    if analisis["precio_entrada"] is not None:
        print(
            "[PRECIO KALSHI] "
            f"{analisis['precio_entrada']:.3f}"
        )

    if analisis["edge"] is not None:
        print(
            "[EDGE] "
            f"{analisis['edge'] * 100:+.2f}%"
        )

    enviar_telegram(analisis)

    return True


# ============================================================
# FINAL SIN DECISION
# ============================================================

def guardar_no_apostar_final(mercado):
    historial = cargar_historial()
    ticker = mercado.get("ticker")

    if not ticker:
        return

    if buscar_registro(historial, ticker):
        return

    analisis = analizar_mercado(mercado)

    if analisis is None:
        return

    analisis["decision"] = "NO APOSTAR"
    analisis["fuerza"] = "SIN VENTAJA"
    analisis["precio_entrada"] = None
    analisis["lado_contrato"] = None
    analisis["edge"] = None
    analisis["confirmaciones"] = 0

    historial.append(analisis)
    guardar_historial(historial)
    limpiar_confirmacion(ticker)

    print(
        "[FINAL] Contrato anterior guardado como NO APOSTAR."
    )


# ============================================================
# ESTADISTICAS
# ============================================================

def mostrar_estadisticas():
    historial = cargar_historial()

    apuestas = [
        x
        for x in historial
        if x.get("decision") in ("ARRIBA", "ABAJO")
    ]

    resueltas = [
        x
        for x in apuestas
        if x.get("evaluacion") in ("ACIERTO", "FALLO")
    ]

    if not resueltas:
        return

    aciertos = sum(
        1
        for x in resueltas
        if x.get("evaluacion") == "ACIERTO"
    )

    fallos = sum(
        1
        for x in resueltas
        if x.get("evaluacion") == "FALLO"
    )

    total = len(resueltas)
    precision = (aciertos / total) * 100.0

    pnl_total = sum(
        safe_float(
            x.get("pnl_teorico_1_contrato"),
            0.0,
        )
        for x in resueltas
    )

    print("\n========================================")
    print("[ESTADISTICAS]")
    print(f"Operaciones resueltas: {total}")
    print(f"Aciertos: {aciertos}")
    print(f"Fallos: {fallos}")
    print(f"Precisión: {precision:.2f}%")
    print(f"P&L teórico acumulado: ${pnl_total:+.4f}")
    print("========================================")

    # NUEVO: últimas operaciones con hora de predicción y resultado.
    print("[ULTIMOS RESULTADOS]")

    for x in resueltas[-10:]:
        print(
            f"{x.get('evaluacion')} | "
            f"{x.get('decision')} -> {x.get('resultado')} | "
            f"Predicción: {x.get('hora_prediccion_local', '-')} | "
            f"Resultado: {x.get('resultado_hora_local', '-')}"
        )

    print("========================================\n")


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():
    global ULTIMO_RESULTADO_CHECK

    print("\n========================================")
    print(" MOTOR BTC 15M INICIADO")
    print(f" VERSION: {VERSION_MOTOR}")
    print(" MODO: PROFIT ENGINE V2 PRECISION")
    print(" DECISIONES: ARRIBA / ABAJO / NO APOSTAR")
    print(
        f" MIN. DESDE APERTURA: "
        f"{MIN_SEGUNDOS_DESDE_APERTURA}s"
    )
    print(
        f" CONFIRMACIONES: "
        f"{CONFIRMACIONES_REQUERIDAS}"
    )
    print(" NO COLOCA ORDENES REALES")
    print("========================================\n")

    ticker_anterior = None
    mercado_anterior = None

    while not DETENER:
        try:
            ahora = time.time()

            if (
                ahora - ULTIMO_RESULTADO_CHECK
                >= INTERVALO_RESULTADOS
            ):
                actualizar_resultados()
                mostrar_estadisticas()
                ULTIMO_RESULTADO_CHECK = ahora

            mercado = elegir_mercado_actual()

            if mercado is None:
                print("[KALSHI] No hay mercado BTC 15M abierto.")
                dormir_interrumpible(INTERVALO_REVISION)
                continue

            ticker = mercado.get("ticker")

            if not ticker:
                dormir_interrumpible(INTERVALO_REVISION)
                continue

            if (
                ticker_anterior
                and ticker != ticker_anterior
                and mercado_anterior is not None
            ):
                guardar_no_apostar_final(mercado_anterior)
                limpiar_confirmacion(ticker_anterior)

            ticker_anterior = ticker
            mercado_anterior = mercado

            historial = cargar_historial()
            existente = buscar_registro(historial, ticker)

            if existente is not None:
                print(
                    f"[{ticker}] Decisión ya guardada: "
                    f"{existente.get('decision')}"
                )
                dormir_interrumpible(INTERVALO_REVISION)
                continue

            analisis = analizar_mercado(mercado)

            if analisis is None:
                dormir_interrumpible(INTERVALO_REVISION)
                continue

            mostrar_analisis(analisis)
            guardar_si_corresponde(analisis)

        except Exception as e:
            print(f"[MOTOR] Error general: {e}")

        dormir_interrumpible(INTERVALO_REVISION)

    print("\n========================================")
    print(" MOTOR BTC 15M DETENIDO")
    print(" Cancelación completada correctamente.")
    print("========================================")


if __name__ == "__main__":
    main()
