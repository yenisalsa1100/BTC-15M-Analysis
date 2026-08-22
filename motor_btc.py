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
# MOTOR KALSHI BTC 15M
#
# VERSION:
# BTC_15M_PROFIT_ENGINE_V1
#
# OBJETIVO:
# - SOLO BTC
# - KALSHI DA EL TARGET OFICIAL
# - KALSHI DA EL RESULTADO FINAL
# - CF BENCHMARKS / BRTI
# - COINBASE
# - KRAKEN
# - COINMARKETCAP
# - BINANCE ORDER BOOK / ORDER FLOW
# - BITFINEX SPOT
# - METRICAS TIPO TAPESURF AGREGADAS DE EXCHANGES
# - EMA / RSI / MACD
# - MOMENTUM
# - VELOCIDAD / ACELERACION
# - VOLATILIDAD
# - VOLUMEN
# - CMF
# - ORDER BOOK IMBALANCE
# - PROFUNDIDAD
# - TRADES AGRESIVOS
# - ORDER FLOW
# - CONSENSO MULTIFUENTE
# - BUSQUEDA DINAMICA DE ENTRADA
# - EDGE CONTRA PRECIO KALSHI
# - HISTORIAL
# - P&L TEORICO
# - TELEGRAM ARRIBA / ABAJO SOLO 90%+
#
# SALIDAS:
# ARRIBA
# ABAJO
# NO APOSTAR
#
# IMPORTANTE:
# ESTE ARCHIVO NO COLOCA ORDENES REALES.
# ============================================================


# ============================================================
# CONFIGURACION GENERAL
# ============================================================

VERSION_MOTOR = "BTC_15M_PROFIT_ENGINE_V1"

SERIES_TICKER = "KXBTC15M"

KALSHI_BASE = (
    "https://external-api.kalshi.com/trade-api/v2"
)

COINBASE_BASE = (
    "https://api.exchange.coinbase.com"
)

KRAKEN_BASE = (
    "https://api.kraken.com"
)

BINANCE_BASE = (
    "https://api.binance.com"
)

BITFINEX_BASE = (
    "https://api-pub.bitfinex.com"
)

CMC_BASE = (
    "https://pro-api.coinmarketcap.com"
)

LOCAL_TZ = ZoneInfo(
    "America/Chicago"
)

HISTORIAL_FILE = (
    "historial_btc_15m.json"
)


# ============================================================
# INTERVALOS
# ============================================================

INTERVALO_REVISION = 10

INTERVALO_RESULTADOS = 30

TIMEOUT_HTTP = 10


# ============================================================
# VENTANA DINAMICA DE ENTRADA
# ============================================================

MIN_SEGUNDOS_DESDE_APERTURA = 55

MIN_SEGUNDOS_RESTANTES = 120


# ============================================================
# UMBRALES
# ============================================================

PROBABILIDAD_MEDIA = 56.0

PROBABILIDAD_FUERTE = 63.0

PROBABILIDAD_MINIMA_APUESTA = 90.0

SCORE_MEDIO = 26.0

SCORE_FUERTE = 42.0


# ============================================================
# EDGE
# ============================================================

EDGE_MINIMO_MEDIO = 0.015

EDGE_MINIMO_FUERTE = 0.030


# ============================================================
# TARGET
# ============================================================

TARGET_ZONA_MUERTA_PCT = 0.012

TARGET_DISTANCIA_FUERTE_PCT = 0.050


# ============================================================
# ORDER BOOK
# ============================================================

ORDERBOOK_NIVELES = 10


# ============================================================
# TRADES / ORDER FLOW
# ============================================================

TRADES_WINDOW_SEGUNDOS = 120

TRADES_MAX = 200


# ============================================================
# CONTROL
# ============================================================

DETENER = False

ULTIMO_RESULTADO_CHECK = 0

ULTIMO_CMC = {
    "precio": None,
    "timestamp": 0,
}

ULTIMO_CF = {
    "precio": None,
    "timestamp": 0,
}


# ============================================================
# SIGNAL HANDLER
# ============================================================

def manejar_senal(
    signum,
    frame,
):
    global DETENER

    print("")
    print(
        "[STOP] Señal de cancelación recibida."
    )

    DETENER = True


if __name__ == "__main__":
    signal.signal(
        signal.SIGTERM,
        manejar_senal,
    )

    signal.signal(
        signal.SIGINT,
        manejar_senal,
    )


# ============================================================
# UTILIDADES
# ============================================================

def ahora_utc():
    return datetime.now(
        timezone.utc
    )


def ahora_local():
    return datetime.now(
        LOCAL_TZ
    )


def iso_utc():
    return ahora_utc().isoformat()


def safe_float(
    valor,
    default=None,
):
    try:
        if valor is None:
            return default

        return float(valor)

    except Exception:
        return default


def limitar(
    valor,
    minimo,
    maximo,
):
    return max(
        minimo,
        min(
            maximo,
            valor,
        ),
    )


def media_valida(valores):
    salida = []

    for x in valores:
        try:
            if x is None:
                continue

            valor = float(x)

            if math.isfinite(valor):
                salida.append(
                    valor
                )

        except Exception:
            continue

    if not salida:
        return None

    return statistics.mean(
        salida
    )


def mediana_valida(valores):
    salida = []

    for x in valores:
        try:
            if x is None:
                continue

            valor = float(x)

            if math.isfinite(valor):
                salida.append(
                    valor
                )

        except Exception:
            continue

    if not salida:
        return None

    return statistics.median(
        salida
    )


def dormir_interrumpible(
    segundos,
):
    for _ in range(
        int(segundos)
    ):
        if DETENER:
            return

        time.sleep(1)


# ============================================================
# HTTP
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Kalshi-BTC-15M-Profit-Engine/1.0"
        ),
        "Accept": "application/json",
    }
)


def http_get(
    url,
    params=None,
    headers=None,
    timeout=TIMEOUT_HTTP,
):
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
        print(
            f"[HTTP] Error GET {url}: {e}"
        )

        return None


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(
    analisis,
):
    decision = analisis.get(
        "decision"
    )

    if decision not in [
        "ARRIBA",
        "ABAJO",
    ]:
        return

    probabilidad = safe_float(
        analisis.get(
            "probabilidad"
        ),
        0.0,
    )

    if (
        probabilidad
        < PROBABILIDAD_MINIMA_APUESTA
    ):
        print(
            "[TELEGRAM] "
            "No se envía señal: "
            f"{probabilidad:.1f}% "
            f"< {PROBABILIDAD_MINIMA_APUESTA:.1f}%"
        )

        return

    token = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip()

    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID",
        "",
    ).strip()

    if (
        not token
        or not chat_id
    ):
        return

    icono = (
        "🟢"
        if decision == "ARRIBA"
        else "🔴"
    )

    target = analisis.get(
        "target"
    )

    precio = analisis.get(
        "precio_consenso"
    )

    prob = analisis.get(
        "probabilidad"
    )

    fuerza = analisis.get(
        "fuerza"
    )

    edge = analisis.get(
        "edge"
    )

    minuto = analisis.get(
        "minuto_entrada"
    )

    texto = (
        f"{icono} BTC 15M - {decision}\n\n"
        f"Fuerza: {fuerza}\n"
        f"Probabilidad: {prob:.1f}%\n"
        f"Target Kalshi: ${target:,.2f}\n"
        f"BTC: ${precio:,.2f}\n"
    )

    if edge is not None:
        texto += (
            f"Edge: {edge * 100:+.2f}%\n"
        )

    if minuto is not None:
        texto += (
            f"Minuto de entrada: "
            f"{minuto:.2f}\n"
        )

    try:
        respuesta = SESSION.post(
            (
                "https://api.telegram.org/"
                f"bot{token}/sendMessage"
            ),
            data={
                "chat_id": chat_id,
                "text": texto,
            },
            timeout=30,
        )

        if not respuesta.ok:
            print(
                "[TELEGRAM] Error HTTP: "
                f"{respuesta.status_code}"
            )

    except Exception as e:
        print(
            f"[TELEGRAM] Error: {e}"
        )


# ============================================================
# KALSHI AUTH
# ============================================================

def cargar_private_key():
    texto = os.getenv(
        "KALSHI_PRIVATE_KEY",
        "",
    ).strip()

    texto_b64 = os.getenv(
        "KALSHI_PRIVATE_KEY_BASE64",
        "",
    ).strip()

    if (
        not texto
        and texto_b64
    ):
        try:
            texto = (
                base64.b64decode(
                    texto_b64
                ).decode(
                    "utf-8"
                )
            )

        except Exception:
            return None

    if not texto:
        return None

    texto = texto.replace(
        "\\n",
        "\n",
    )

    try:
        return (
            serialization.load_pem_private_key(
                texto.encode(
                    "utf-8"
                ),
                password=None,
            )
        )

    except Exception as e:
        print(
            "[KALSHI AUTH] "
            "No se pudo cargar private key: "
            f"{e}"
        )

        return None


PRIVATE_KEY = cargar_private_key()

KALSHI_API_KEY_ID = os.getenv(
    "KALSHI_API_KEY_ID",
    "",
).strip()


def firma_kalshi(
    timestamp_ms,
    method,
    path,
):
    if PRIVATE_KEY is None:
        return None

    path_sin_query = (
        path.split("?")[0]
    )

    mensaje = (
        f"{timestamp_ms}"
        f"{method.upper()}"
        f"{path_sin_query}"
    ).encode(
        "utf-8"
    )

    firma = PRIVATE_KEY.sign(
        mensaje,
        padding.PSS(
            mgf=padding.MGF1(
                hashes.SHA256()
            ),
            salt_length=(
                padding.PSS.DIGEST_LENGTH
            ),
        ),
        hashes.SHA256(),
    )

    return base64.b64encode(
        firma
    ).decode(
        "utf-8"
    )


def headers_kalshi(
    method,
    path,
):
    if (
        not KALSHI_API_KEY_ID
        or PRIVATE_KEY is None
    ):
        return None

    timestamp_ms = str(
        int(
            time.time()
            * 1000
        )
    )

    firma = firma_kalshi(
        timestamp_ms,
        method,
        (
            "/trade-api/v2"
            + path
        ),
    )

    return {
        "KALSHI-ACCESS-KEY":
        KALSHI_API_KEY_ID,

        "KALSHI-ACCESS-TIMESTAMP":
        timestamp_ms,

        "KALSHI-ACCESS-SIGNATURE":
        firma,
    }


# ============================================================
# FECHAS
# ============================================================

def parse_fecha(fecha):
    if not fecha:
        return None

    try:
        return datetime.fromisoformat(
            fecha.replace(
                "Z",
                "+00:00",
            )
        )

    except Exception:
        return None


# ============================================================
# MERCADOS KALSHI
# ============================================================

def obtener_mercados_kalshi(
    status="open",
):
    datos = http_get(
        (
            f"{KALSHI_BASE}"
            "/markets"
        ),
        params={
            "series_ticker":
            SERIES_TICKER,

            "status":
            status,

            "limit":
            100,
        },
    )

    if not datos:
        return []

    return datos.get(
        "markets",
        [],
    )


def elegir_mercado_actual():
    mercados = obtener_mercados_kalshi(
        "open"
    )

    if not mercados:
        return None

    ahora = ahora_utc()

    candidatos = []

    for mercado in mercados:
        close_time = parse_fecha(
            mercado.get(
                "close_time"
            )
        )

        if close_time is None:
            continue

        segundos = (
            close_time
            - ahora
        ).total_seconds()

        if segundos <= 0:
            continue

        candidatos.append(
            (
                segundos,
                mercado,
            )
        )

    if not candidatos:
        return None

    candidatos.sort(
        key=lambda x: x[0]
    )

    return candidatos[0][1]


def obtener_mercado_por_ticker(
    ticker,
):
    datos = http_get(
        (
            f"{KALSHI_BASE}"
            f"/markets/{ticker}"
        )
    )

    if not datos:
        return None

    return datos.get(
        "market",
        datos,
    )


# ============================================================
# TARGET KALSHI
# ============================================================

def extraer_target_kalshi(
    mercado,
):
    posibles = [
        mercado.get(
            "floor_strike"
        ),
        mercado.get(
            "functional_strike"
        ),
    ]

    for valor in posibles:
        numero = safe_float(
            valor
        )

        if numero is not None:
            return numero

    custom = mercado.get(
        "custom_strike",
        {},
    )

    if isinstance(
        custom,
        dict,
    ):
        for valor in custom.values():
            numero = safe_float(
                valor
            )

            if numero is not None:
                return numero

    return None


# ============================================================
# PRECIOS KALSHI
# ============================================================

def convertir_precio_kalshi(
    valor,
):
    if valor is None:
        return None

    numero = safe_float(
        valor
    )

    if numero is None:
        return None

    if numero > 1:
        numero /= 100.0

    return limitar(
        numero,
        0.0,
        1.0,
    )


def precio_yes_ask(
    mercado,
):
    candidatos = [
        mercado.get(
            "yes_ask_dollars"
        ),
        mercado.get(
            "yes_ask"
        ),
    ]

    for x in candidatos:
        p = convertir_precio_kalshi(
            x
        )

        if p is not None:
            return p

    return None


def precio_no_ask(
    mercado,
):
    candidatos = [
        mercado.get(
            "no_ask_dollars"
        ),
        mercado.get(
            "no_ask"
        ),
    ]

    for x in candidatos:
        p = convertir_precio_kalshi(
            x
        )

        if p is not None:
            return p

    return None


# ============================================================
# KALSHI ORDER BOOK
# ============================================================

def obtener_orderbook_kalshi(
    ticker,
):
    datos = http_get(
        (
            f"{KALSHI_BASE}"
            f"/markets/{ticker}"
            "/orderbook"
        )
    )

    if not datos:
        return None

    return datos.get(
        "orderbook",
        datos,
    )


def sumar_book_kalshi(
    lados,
):
    total = 0.0

    if not isinstance(
        lados,
        list,
    ):
        return 0.0

    for nivel in lados[
        :ORDERBOOK_NIVELES
    ]:

        if isinstance(
            nivel,
            list,
        ):

            if len(nivel) >= 2:
                total += safe_float(
                    nivel[1],
                    0.0,
                )

        elif isinstance(
            nivel,
            dict,
        ):

            cantidad = safe_float(
                nivel.get(
                    "quantity",
                    nivel.get(
                        "count",
                        nivel.get(
                            "quantity_fp",
                            nivel.get(
                                "count_fp",
                                0,
                            ),
                        ),
                    ),
                ),
                0,
            )

            total += cantidad

    return total


def obi_kalshi(
    orderbook,
):
    if not orderbook:
        return 0.0

    yes = (
        orderbook.get(
            "yes"
        )
        or orderbook.get(
            "yes_dollars"
        )
        or []
    )

    no = (
        orderbook.get(
            "no"
        )
        or orderbook.get(
            "no_dollars"
        )
        or []
    )

    qty_yes = sumar_book_kalshi(
        yes
    )

    qty_no = sumar_book_kalshi(
        no
    )

    total = (
        qty_yes
        + qty_no
    )

    if total <= 0:
        return 0.0

    return (
        qty_yes
        - qty_no
    ) / total


def profundidad_kalshi(
    orderbook,
):
    if not orderbook:
        return {
            "yes": 0.0,
            "no": 0.0,
            "total": 0.0,
        }

    yes = (
        orderbook.get(
            "yes"
        )
        or orderbook.get(
            "yes_dollars"
        )
        or []
    )

    no = (
        orderbook.get(
            "no"
        )
        or orderbook.get(
            "no_dollars"
        )
        or []
    )

    qty_yes = sumar_book_kalshi(
        yes
    )

    qty_no = sumar_book_kalshi(
        no
    )

    return {
        "yes": qty_yes,
        "no": qty_no,
        "total": (
            qty_yes
            + qty_no
        ),
    }


# ============================================================
# COINBASE
# ============================================================

def obtener_coinbase_ticker():
    datos = http_get(
        (
            f"{COINBASE_BASE}"
            "/products/BTC-USD/ticker"
        )
    )

    if not datos:
        return None

    return safe_float(
        datos.get(
            "price"
        )
    )


def obtener_coinbase_candles():
    datos = http_get(
        (
            f"{COINBASE_BASE}"
            "/products/BTC-USD/candles"
        ),
        params={
            "granularity":
            60,
        },
    )

    if not datos:
        return None

    filas = []

    for item in datos:
        try:
            filas.append(
                {
                    "time":
                    int(item[0]),

                    "low":
                    float(item[1]),

                    "high":
                    float(item[2]),

                    "open":
                    float(item[3]),

                    "close":
                    float(item[4]),

                    "volume":
                    float(item[5]),
                }
            )

        except Exception:
            continue

    if not filas:
        return None

    df = pd.DataFrame(
        filas
    )

    df = df.sort_values(
        "time"
    ).reset_index(
        drop=True
    )

    return df


def obtener_coinbase_book():
    return http_get(
        (
            f"{COINBASE_BASE}"
            "/products/BTC-USD/book"
        ),
        params={
            "level":
            2,
        },
    )


def obtener_coinbase_trades():
    datos = http_get(
        (
            f"{COINBASE_BASE}"
            "/products/BTC-USD/trades"
        ),
        params={
            "limit":
            100,
        },
    )

    if not isinstance(
        datos,
        list,
    ):
        return []

    return datos


def obi_coinbase(
    book,
):
    if not book:
        return 0.0

    bids = book.get(
        "bids",
        [],
    )

    asks = book.get(
        "asks",
        [],
    )

    bid_qty = 0.0

    ask_qty = 0.0

    for nivel in bids[
        :ORDERBOOK_NIVELES
    ]:
        if len(nivel) >= 2:
            bid_qty += safe_float(
                nivel[1],
                0,
            )

    for nivel in asks[
        :ORDERBOOK_NIVELES
    ]:
        if len(nivel) >= 2:
            ask_qty += safe_float(
                nivel[1],
                0,
            )

    total = (
        bid_qty
        + ask_qty
    )

    if total <= 0:
        return 0.0

    return (
        bid_qty
        - ask_qty
    ) / total


def profundidad_coinbase(
    book,
):
    if not book:
        return {
            "bid": 0.0,
            "ask": 0.0,
            "total": 0.0,
        }

    bid_qty = sum(
        safe_float(
            x[1],
            0,
        )
        for x in book.get(
            "bids",
            [],
        )[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(
            x[1],
            0,
        )
        for x in book.get(
            "asks",
            [],
        )[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    return {
        "bid":
        bid_qty,

        "ask":
        ask_qty,

        "total":
        (
            bid_qty
            + ask_qty
        ),
    }


def spread_coinbase(
    book,
):
    if not book:
        return None

    try:
        best_bid = float(
            book[
                "bids"
            ][0][0]
        )

        best_ask = float(
            book[
                "asks"
            ][0][0]
        )

        mid = (
            best_bid
            + best_ask
        ) / 2

        if mid <= 0:
            return None

        return (
            best_ask
            - best_bid
        ) / mid

    except Exception:
        return None


# ============================================================
# KRAKEN
# ============================================================

def kraken_pair_key(
    resultado,
):
    if not isinstance(
        resultado,
        dict,
    ):
        return None

    for key in resultado.keys():
        if key != "last":
            return key

    return None


def obtener_kraken_ticker():
    datos = http_get(
        (
            f"{KRAKEN_BASE}"
            "/0/public/Ticker"
        ),
        params={
            "pair":
            "XBTUSD",
        },
    )

    if not datos:
        return None

    resultado = datos.get(
        "result",
        {},
    )

    key = kraken_pair_key(
        resultado
    )

    if not key:
        return None

    try:
        return float(
            resultado[
                key
            ]["c"][0]
        )

    except Exception:
        return None


def obtener_kraken_book():
    datos = http_get(
        (
            f"{KRAKEN_BASE}"
            "/0/public/Depth"
        ),
        params={
            "pair":
            "XBTUSD",

            "count":
            ORDERBOOK_NIVELES,
        },
    )

    if not datos:
        return None

    resultado = datos.get(
        "result",
        {},
    )

    key = kraken_pair_key(
        resultado
    )

    if not key:
        return None

    return resultado.get(
        key
    )


def obtener_kraken_trades():
    datos = http_get(
        (
            f"{KRAKEN_BASE}"
            "/0/public/Trades"
        ),
        params={
            "pair":
            "XBTUSD",

            "count":
            TRADES_MAX,
        },
    )

    if not datos:
        return []

    resultado = datos.get(
        "result",
        {},
    )

    key = kraken_pair_key(
        resultado
    )

    if not key:
        return []

    return resultado.get(
        key,
        [],
    )


def obi_kraken(
    book,
):
    if not book:
        return 0.0

    bids = book.get(
        "bids",
        [],
    )

    asks = book.get(
        "asks",
        [],
    )

    bid_qty = sum(
        safe_float(
            x[1],
            0.0,
        )
        for x in bids[
            :ORDERBOOK_NIVELES
        ]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(
            x[1],
            0.0,
        )
        for x in asks[
            :ORDERBOOK_NIVELES
        ]
        if len(x) >= 2
    )

    total = (
        bid_qty
        + ask_qty
    )

    if total <= 0:
        return 0.0

    return (
        bid_qty
        - ask_qty
    ) / total


def profundidad_kraken(
    book,
):
    if not book:
        return {
            "bid": 0.0,
            "ask": 0.0,
            "total": 0.0,
        }

    bid_qty = sum(
        safe_float(
            x[1],
            0,
        )
        for x in book.get(
            "bids",
            [],
        )[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(
            x[1],
            0,
        )
        for x in book.get(
            "asks",
            [],
        )[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    return {
        "bid":
        bid_qty,

        "ask":
        ask_qty,

        "total":
        (
            bid_qty
            + ask_qty
        ),
    }


# ============================================================
# BINANCE
# ============================================================

def obtener_binance_book():
    return http_get(
        (
            f"{BINANCE_BASE}"
            "/api/v3/depth"
        ),
        params={
            "symbol":
            "BTCUSDT",

            "limit":
            ORDERBOOK_NIVELES,
        },
    )


def obtener_binance_trades():
    datos = http_get(
        (
            f"{BINANCE_BASE}"
            "/api/v3/aggTrades"
        ),
        params={
            "symbol":
            "BTCUSDT",

            "limit":
            TRADES_MAX,
        },
    )

    if not isinstance(
        datos,
        list,
    ):
        return []

    return datos


def obi_binance(
    book,
):
    if not book:
        return 0.0

    bids = book.get(
        "bids",
        [],
    )

    asks = book.get(
        "asks",
        [],
    )

    bid_qty = sum(
        safe_float(
            x[1],
            0.0,
        )
        for x in bids[
            :ORDERBOOK_NIVELES
        ]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(
            x[1],
            0.0,
        )
        for x in asks[
            :ORDERBOOK_NIVELES
        ]
        if len(x) >= 2
    )

    total = (
        bid_qty
        + ask_qty
    )

    if total <= 0:
        return 0.0

    return (
        bid_qty
        - ask_qty
    ) / total


def profundidad_binance(
    book,
):
    if not book:
        return {
            "bid": 0.0,
            "ask": 0.0,
            "total": 0.0,
        }

    bid_qty = sum(
        safe_float(
            x[1],
            0,
        )
        for x in book.get(
            "bids",
            [],
        )[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    ask_qty = sum(
        safe_float(
            x[1],
            0,
        )
        for x in book.get(
            "asks",
            [],
        )[:ORDERBOOK_NIVELES]
        if len(x) >= 2
    )

    return {
        "bid":
        bid_qty,

        "ask":
        ask_qty,

        "total":
        (
            bid_qty
            + ask_qty
        ),
    }


# ============================================================
# BITFINEX SPOT
# ============================================================

def obtener_bitfinex_book():
    datos = http_get(
        (
            f"{BITFINEX_BASE}"
            "/v2/book/tBTCUSD/P0"
        ),
        params={
            "len":
            25,
        },
    )

    if not isinstance(
        datos,
        list,
    ):
        return []

    return datos


def obtener_bitfinex_trades():
    datos = http_get(
        (
            f"{BITFINEX_BASE}"
            "/v2/trades/tBTCUSD/hist"
        ),
        params={
            "limit":
            TRADES_MAX,

            "sort":
            -1,
        },
    )

    if not isinstance(
        datos,
        list,
    ):
        return []

    return datos


def obi_bitfinex(
    book,
):
    if not book:
        return 0.0

    bids = []

    asks = []

    for nivel in book:
        try:
            if len(nivel) < 3:
                continue

            amount = safe_float(
                nivel[2],
                0.0,
            )

            if amount > 0:
                bids.append(
                    abs(
                        amount
                    )
                )

            elif amount < 0:
                asks.append(
                    abs(
                        amount
                    )
                )

        except Exception:
            continue

    bid_qty = sum(
        bids[
            :ORDERBOOK_NIVELES
        ]
    )

    ask_qty = sum(
        asks[
            :ORDERBOOK_NIVELES
        ]
    )

    total = (
        bid_qty
        + ask_qty
    )

    if total <= 0:
        return 0.0

    return (
        bid_qty
        - ask_qty
    ) / total


def profundidad_bitfinex(
    book,
):
    if not book:
        return {
            "bid": 0.0,
            "ask": 0.0,
            "total": 0.0,
        }

    bids = []

    asks = []

    for nivel in book:
        try:
            if len(nivel) < 3:
                continue

            amount = safe_float(
                nivel[2],
                0.0,
            )

            if amount > 0:
                bids.append(
                    abs(
                        amount
                    )
                )

            elif amount < 0:
                asks.append(
                    abs(
                        amount
                    )
                )

        except Exception:
            continue

    bid_qty = sum(
        bids[
            :ORDERBOOK_NIVELES
        ]
    )

    ask_qty = sum(
        asks[
            :ORDERBOOK_NIVELES
        ]
    )

    return {
        "bid":
        bid_qty,

        "ask":
        ask_qty,

        "total":
        (
            bid_qty
            + ask_qty
        ),
    }


# ============================================================
# ORDER FLOW COINBASE
# ============================================================

def orderflow_coinbase(
    trades,
):
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
            fecha = parse_fecha(
                trade.get(
                    "time"
                )
            )

            if fecha:
                edad = (
                    ahora
                    - fecha
                ).total_seconds()

                if (
                    edad
                    > TRADES_WINDOW_SEGUNDOS
                ):
                    continue

            size = safe_float(
                trade.get(
                    "size"
                ),
                0,
            )

            side = str(
                trade.get(
                    "side",
                    "",
                )
            ).lower()

            if side == "sell":
                buy_volume += size

            elif side == "buy":
                sell_volume += size

            usados += 1

        except Exception:
            continue

    total = (
        buy_volume
        + sell_volume
    )

    imbalance = 0.0

    if total > 0:
        imbalance = (
            buy_volume
            - sell_volume
        ) / total

    return {
        "imbalance":
        imbalance,

        "buy_volume":
        buy_volume,

        "sell_volume":
        sell_volume,

        "trades":
        usados,
    }


# ============================================================
# ORDER FLOW KRAKEN
# ============================================================

def orderflow_kraken(
    trades,
):
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

            volume = safe_float(
                trade[1],
                0,
            )

            timestamp = safe_float(
                trade[2],
                0,
            )

            side = str(
                trade[3]
            ).lower()

            if (
                timestamp
                and (
                    ahora_ts
                    - timestamp
                )
                > TRADES_WINDOW_SEGUNDOS
            ):
                continue

            if side == "b":
                buy_volume += volume

            elif side == "s":
                sell_volume += volume

            usados += 1

        except Exception:
            continue

    total = (
        buy_volume
        + sell_volume
    )

    imbalance = 0.0

    if total > 0:
        imbalance = (
            buy_volume
            - sell_volume
        ) / total

    return {
        "imbalance":
        imbalance,

        "buy_volume":
        buy_volume,

        "sell_volume":
        sell_volume,

        "trades":
        usados,
    }


# ============================================================
# ORDER FLOW BINANCE
# ============================================================

def orderflow_binance(
    trades,
):
    if not trades:
        return {
            "imbalance": 0.0,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "trades": 0,
        }

    ahora_ms = (
        time.time()
        * 1000
    )

    buy_volume = 0.0

    sell_volume = 0.0

    usados = 0

    for trade in trades:
        try:
            volume = safe_float(
                trade.get(
                    "q"
                ),
                0,
            )

            timestamp = safe_float(
                trade.get(
                    "T"
                ),
                0,
            )

            buyer_is_maker = bool(
                trade.get(
                    "m",
                    False,
                )
            )

            if (
                timestamp
                and (
                    ahora_ms
                    - timestamp
                )
                > (
                    TRADES_WINDOW_SEGUNDOS
                    * 1000
                )
            ):
                continue

            if buyer_is_maker:
                sell_volume += volume

            else:
                buy_volume += volume

            usados += 1

        except Exception:
            continue

    total = (
        buy_volume
        + sell_volume
    )

    imbalance = 0.0

    if total > 0:
        imbalance = (
            buy_volume
            - sell_volume
        ) / total

    return {
        "imbalance":
        imbalance,

        "buy_volume":
        buy_volume,

        "sell_volume":
        sell_volume,

        "trades":
        usados,
    }


# ============================================================
# ORDER FLOW BITFINEX
# ============================================================

def orderflow_bitfinex(
    trades,
):
    if not trades:
        return {
            "imbalance": 0.0,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "trades": 0,
        }

    ahora_ms = (
        time.time()
        * 1000
    )

    buy_volume = 0.0

    sell_volume = 0.0

    usados = 0

    for trade in trades:
        try:
            if len(trade) < 4:
                continue

            timestamp = safe_float(
                trade[1],
                0.0,
            )

            if (
                timestamp
                and (
                    ahora_ms
                    - timestamp
                )
                > (
                    TRADES_WINDOW_SEGUNDOS
                    * 1000
                )
            ):
                continue

            amount = safe_float(
                trade[2],
                0.0,
            )

            if amount > 0:
                buy_volume += abs(
                    amount
                )

            elif amount < 0:
                sell_volume += abs(
                    amount
                )

            usados += 1

        except Exception:
            continue

    total = (
        buy_volume
        + sell_volume
    )

    imbalance = 0.0

    if total > 0:
        imbalance = (
            buy_volume
            - sell_volume
        ) / total

    return {
        "imbalance":
        imbalance,

        "buy_volume":
        buy_volume,

        "sell_volume":
        sell_volume,

        "trades":
        usados,
    }


# ============================================================
# METRICAS TIPO TAPESURF
# ============================================================

def calcular_metricas_tapesurf(
    profundidad_cb,
    profundidad_kr,
    profundidad_bi,
    profundidad_bf,
    flujo_cb,
    flujo_kr,
    flujo_bi,
    flujo_bf,
):
    bid_total = sum(
        safe_float(
            x.get(
                "bid"
            ),
            0.0,
        )
        for x in [
            profundidad_cb,
            profundidad_kr,
            profundidad_bi,
            profundidad_bf,
        ]
        if isinstance(
            x,
            dict,
        )
    )

    ask_total = sum(
        safe_float(
            x.get(
                "ask"
            ),
            0.0,
        )
        for x in [
            profundidad_cb,
            profundidad_kr,
            profundidad_bi,
            profundidad_bf,
        ]
        if isinstance(
            x,
            dict,
        )
    )

    profundidad_total = (
        bid_total
        + ask_total
    )

    delta_profundidad = (
        bid_total
        - ask_total
    )

    imbalance_profundidad = 0.0

    if profundidad_total > 0:
        imbalance_profundidad = (
            delta_profundidad
            / profundidad_total
        )

    buy_volume = sum(
        safe_float(
            x.get(
                "buy_volume"
            ),
            0.0,
        )
        for x in [
            flujo_cb,
            flujo_kr,
            flujo_bi,
            flujo_bf,
        ]
        if isinstance(
            x,
            dict,
        )
    )

    sell_volume = sum(
        safe_float(
            x.get(
                "sell_volume"
            ),
            0.0,
        )
        for x in [
            flujo_cb,
            flujo_kr,
            flujo_bi,
            flujo_bf,
        ]
        if isinstance(
            x,
            dict,
        )
    )

    volumen_total = (
        buy_volume
        + sell_volume
    )

    delta_orderflow = (
        buy_volume
        - sell_volume
    )

    imbalance_orderflow = 0.0

    if volumen_total > 0:
        imbalance_orderflow = (
            delta_orderflow
            / volumen_total
        )

    return {
        "bid":
        bid_total,

        "ask":
        ask_total,

        "delta_depth":
        delta_profundidad,

        "imbalance_depth":
        imbalance_profundidad,

        "buy_volume":
        buy_volume,

        "sell_volume":
        sell_volume,

        "delta_orderflow":
        delta_orderflow,

        "imbalance_orderflow":
        imbalance_orderflow,
    }


# ============================================================
# COINMARKETCAP
# ============================================================

def obtener_coinmarketcap():
    global ULTIMO_CMC

    ahora = time.time()

    if (
        ULTIMO_CMC["precio"] is not None
        and (
            ahora
            - ULTIMO_CMC["timestamp"]
        ) < 60
    ):
        return ULTIMO_CMC["precio"]

    api_key = os.getenv(
        "COINMARKETCAP_API_KEY",
        "",
    ).strip()

    if not api_key:
        print(
            "[CMC] Falta COINMARKETCAP_API_KEY."
        )

        return ULTIMO_CMC["precio"]

    datos = http_get(
        (
            f"{CMC_BASE}"
            "/v2/cryptocurrency/quotes/latest"
        ),
        params={
            "id": "1",
            "convert": "USD",
        },
        headers={
            "X-CMC_PRO_API_KEY":
            api_key,

            "Accept":
            "application/json",
        },
    )

    if not datos:
        print(
            "[CMC] Sin respuesta."
        )

        return ULTIMO_CMC["precio"]

    try:
        data = datos.get(
            "data"
        )

        if data is None:
            print(
                "[CMC] Respuesta sin campo data."
            )

            return ULTIMO_CMC["precio"]

        btc = None

        if isinstance(
            data,
            dict,
        ):

            btc = data.get(
                "1"
            )

            if btc is None:
                btc = data.get(
                    1
                )

            if btc is None:

                for valor in data.values():

                    if isinstance(
                        valor,
                        dict,
                    ):

                        simbolo = str(
                            valor.get(
                                "symbol",
                                "",
                            )
                        ).upper()

                        if simbolo == "BTC":
                            btc = valor
                            break

        elif isinstance(
            data,
            list,
        ):

            for item in data:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                item_id = item.get(
                    "id"
                )

                simbolo = str(
                    item.get(
                        "symbol",
                        "",
                    )
                ).upper()

                if (
                    str(item_id) == "1"
                    or simbolo == "BTC"
                ):
                    btc = item
                    break

            if (
                btc is None
                and data
                and isinstance(
                    data[0],
                    dict,
                )
            ):
                btc = data[0]

        else:

            print(
                "[CMC] Formato de data desconocido: "
                f"{type(data).__name__}"
            )

            return ULTIMO_CMC["precio"]

        if not isinstance(
            btc,
            dict,
        ):

            print(
                "[CMC] No se encontró BTC "
                "en la respuesta."
            )

            return ULTIMO_CMC["precio"]

        quote = btc.get(
            "quote",
            {},
        )

        if not isinstance(
            quote,
            dict,
        ):

            print(
                "[CMC] Quote inválido."
            )

            return ULTIMO_CMC["precio"]

        usd = quote.get(
            "USD"
        )

        if usd is None:
            usd = quote.get(
                "usd"
            )

        if isinstance(
            usd,
            list,
        ):

            if (
                usd
                and isinstance(
                    usd[0],
                    dict,
                )
            ):
                usd = usd[0]

        if not isinstance(
            usd,
            dict,
        ):

            print(
                "[CMC] No se encontró quote USD."
            )

            return ULTIMO_CMC["precio"]

        precio = safe_float(
            usd.get(
                "price"
            )
        )

        if precio is None:

            print(
                "[CMC] Precio BTC no encontrado."
            )

            return ULTIMO_CMC["precio"]

        if (
            not math.isfinite(
                precio
            )
            or precio <= 0
        ):

            print(
                "[CMC] Precio BTC inválido."
            )

            return ULTIMO_CMC["precio"]

        ULTIMO_CMC = {
            "precio":
            precio,

            "timestamp":
            ahora,
        }

        print(
            "[CMC OK] BTC: "
            f"${precio:,.2f}"
        )

        return precio

    except Exception as e:

        print(
            "[CMC EXCEPTION] "
            f"{repr(e)}"
        )

        return ULTIMO_CMC["precio"]


# ============================================================
# CF BENCHMARKS / BRTI
# ============================================================

def buscar_valor_brti(
    objeto,
):
    if objeto is None:
        return None

    if isinstance(
        objeto,
        dict,
    ):

        for llave in [
            "value",
            "price",
            "rate",
            "indexValue",
            "index_value",
        ]:

            if llave in objeto:

                numero = safe_float(
                    objeto.get(
                        llave
                    )
                )

                if (
                    numero is not None
                    and numero > 1000
                ):
                    return numero

        for llave, valor in objeto.items():

            if str(llave).upper() == "BRTI":

                encontrado = buscar_valor_brti(
                    valor
                )

                if encontrado is not None:
                    return encontrado

        for valor in objeto.values():

            encontrado = buscar_valor_brti(
                valor
            )

            if encontrado is not None:
                return encontrado

    elif isinstance(
        objeto,
        list,
    ):

        for item in objeto:

            if isinstance(
                item,
                dict,
            ):

                identificador = str(
                    item.get(
                        "id",
                        item.get(
                            "symbol",
                            item.get(
                                "ticker",
                                "",
                            ),
                        ),
                    )
                ).upper()

                if identificador == "BRTI":

                    encontrado = buscar_valor_brti(
                        item
                    )

                    if encontrado is not None:
                        return encontrado

        for item in objeto:

            encontrado = buscar_valor_brti(
                item
            )

            if encontrado is not None:
                return encontrado

    return None


def obtener_cf_brti():
    global ULTIMO_CF

    ahora = time.time()

    if (
        ULTIMO_CF["precio"] is not None
        and (
            ahora
            - ULTIMO_CF["timestamp"]
        ) < 2
    ):
        return ULTIMO_CF["precio"]

    path = "/cfbenchmarks/values"

    headers = headers_kalshi(
        "GET",
        path,
    )

    if headers is None:
        print(
            "[CF BRTI] "
            "No hay autenticación Kalshi."
        )

        return ULTIMO_CF["precio"]

    datos = http_get(
        (
            f"{KALSHI_BASE}"
            f"{path}"
        ),
        params={
            "id": "BRTI",
        },
        headers=headers,
    )

    if not datos:
        print(
            "[CF BRTI] "
            "Sin respuesta."
        )

        return ULTIMO_CF["precio"]

    try:
        contenido = datos.get(
            "data",
            datos,
        )

        precio = buscar_valor_brti(
            contenido
        )

        if precio is None:

            print(
                "[CF BRTI] "
                "Respuesta recibida pero "
                "no se encontró el precio."
            )

            print(
                "[CF BRTI RAW] "
                + json.dumps(
                    datos,
                    ensure_ascii=False,
                )[:1500]
            )

            return ULTIMO_CF["precio"]

        ULTIMO_CF = {
            "precio": precio,
            "timestamp": ahora,
        }

        return precio

    except Exception as e:

        print(
            "[CF BRTI] "
            f"Error procesando: {e}"
        )

        return ULTIMO_CF["precio"]


# ============================================================
# INDICADORES
# ============================================================

def ema(
    serie,
    periodo,
):
    return serie.ewm(
        span=periodo,
        adjust=False,
    ).mean()


def calcular_rsi(
    serie,
    periodo=14,
):
    delta = serie.diff()

    ganancias = delta.clip(
        lower=0
    )

    perdidas = (
        -delta.clip(
            upper=0
        )
    )

    avg_gain = ganancias.ewm(
        alpha=1 / periodo,
        adjust=False,
    ).mean()

    avg_loss = perdidas.ewm(
        alpha=1 / periodo,
        adjust=False,
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        float(
            "nan"
        ),
    )

    rsi = 100 - (
        100
        / (
            1
            + rs
        )
    )

    return rsi.fillna(
        50
    )


def calcular_cmf(
    df,
    periodo=20,
):
    high = df[
        "high"
    ]

    low = df[
        "low"
    ]

    close = df[
        "close"
    ]

    volume = df[
        "volume"
    ]

    rango = (
        high
        - low
    ).replace(
        0,
        float(
            "nan"
        ),
    )

    multiplier = (
        (
            (
                close
                - low
            )
            -
            (
                high
                - close
            )
        )
        / rango
    ).fillna(
        0
    )

    money_flow = (
        multiplier
        * volume
    )

    cmf = (
        money_flow
        .rolling(
            periodo
        )
        .sum()
        /
        volume
        .rolling(
            periodo
        )
        .sum()
        .replace(
            0,
            float(
                "nan"
            ),
        )
    )

    return cmf.fillna(
        0
    )


def construir_indicadores(
    df,
):
    if (
        df is None
        or len(df) < 55
    ):
        return None

    x = df.copy()

    x["ema9"] = ema(
        x["close"],
        9,
    )

    x["ema21"] = ema(
        x["close"],
        21,
    )

    x["ema50"] = ema(
        x["close"],
        50,
    )

    x["rsi14"] = calcular_rsi(
        x["close"],
        14,
    )

    x["macd"] = (
        ema(
            x["close"],
            12,
        )
        -
        ema(
            x["close"],
            26,
        )
    )

    x["macd_signal"] = ema(
        x["macd"],
        9,
    )

    x["cmf20"] = calcular_cmf(
        x,
        20,
    )

    x["ret"] = (
        x["close"]
        .pct_change()
    )

    x["vol20"] = (
        x["ret"]
        .rolling(
            20
        )
        .std()
    )

    x[
        "volume_avg20"
    ] = (
        x["volume"]
        .rolling(
            20
        )
        .mean()
    )

    ultimo = x.iloc[
        -1
    ]

    close = float(
        ultimo[
            "close"
        ]
    )

    def momentum(n):
        if len(x) <= n:
            return 0.0

        anterior = float(
            x.iloc[
                -1 - n
            ][
                "close"
            ]
        )

        if anterior == 0:
            return 0.0

        return (
            close
            / anterior
            - 1
        )

    mom1 = momentum(1)
    mom2 = momentum(2)
    mom3 = momentum(3)
    mom5 = momentum(5)
    mom10 = momentum(10)

    velocidad = mom1

    velocidad_anterior = (
        mom2
        - mom1
    )

    aceleracion = (
        velocidad
        - velocidad_anterior
    )

    volume_actual = safe_float(
        ultimo[
            "volume"
        ],
        0,
    )

    volume_avg = safe_float(
        ultimo[
            "volume_avg20"
        ],
        0,
    )

    volumen_relativo = 1.0

    if volume_avg > 0:
        volumen_relativo = (
            volume_actual
            / volume_avg
        )

    return {
        "close":
        close,

        "ema9":
        float(
            ultimo[
                "ema9"
            ]
        ),

        "ema21":
        float(
            ultimo[
                "ema21"
            ]
        ),

        "ema50":
        float(
            ultimo[
                "ema50"
            ]
        ),

        "rsi14":
        float(
            ultimo[
                "rsi14"
            ]
        ),

        "macd":
        float(
            ultimo[
                "macd"
            ]
        ),

        "macd_signal":
        float(
            ultimo[
                "macd_signal"
            ]
        ),

        "cmf20":
        float(
            ultimo[
                "cmf20"
            ]
        ),

        "vol20":
        safe_float(
            ultimo[
                "vol20"
            ],
            0.0,
        ),

        "volume":
        volume_actual,

        "volume_avg20":
        volume_avg,

        "volumen_relativo":
        volumen_relativo,

        "mom1":
        mom1,

        "mom3":
        mom3,

        "mom5":
        mom5,

        "mom10":
        mom10,

        "velocidad":
        velocidad,

        "aceleracion":
        aceleracion,
    }


# ============================================================
# CONSENSO DE PRECIO
# ============================================================

def construir_precio_consenso(
    coinbase,
    kraken,
    cmc,
    cf,
):
    return mediana_valida(
        [
            coinbase,
            kraken,
            cmc,
            cf,
        ]
    )


def calcular_consenso_fuentes(
    target,
    fuentes,
):
    validas = [
        x
        for x in fuentes
        if x is not None
    ]

    if not validas:
        return {
            "arriba": 0,
            "abajo": 0,
            "total": 0,
            "ratio": 0.0,
        }

    arriba = sum(
        1
        for x in validas
        if x > target
    )

    abajo = sum(
        1
        for x in validas
        if x < target
    )

    total = len(
        validas
    )

    ratio = (
        arriba
        - abajo
    ) / total

    return {
        "arriba":
        arriba,

        "abajo":
        abajo,

        "total":
        total,

        "ratio":
        ratio,
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
    obi_bi,
    obi_bf,
    orderflow_cb,
    orderflow_kr,
    orderflow_bi,
    orderflow_bf,
    precios_fuentes,
    tapesurf,
):
    razones = []

    familias = {
        "target": 0.0,
        "tendencia": 0.0,
        "momentum": 0.0,
        "microestructura": 0.0,
        "flujo_capital": 0.0,
        "consenso": 0.0,
    }

    distancia_pct = (
        (
            precio
            - target
        )
        / target
    ) * 100.0

    abs_distancia = abs(
        distancia_pct
    )

    puntos_target = limitar(
        (
            abs_distancia
            / TARGET_DISTANCIA_FUERTE_PCT
        ) * 18.0,
        0.0,
        18.0,
    )

    if distancia_pct > 0:

        familias[
            "target"
        ] = puntos_target

        razones.append(
            "BTC sobre target "
            f"{distancia_pct:+.4f}%"
        )

    elif distancia_pct < 0:

        familias[
            "target"
        ] = (
            -puntos_target
        )

        razones.append(
            "BTC bajo target "
            f"{distancia_pct:+.4f}%"
        )

    ema9 = indicadores[
        "ema9"
    ]

    ema21 = indicadores[
        "ema21"
    ]

    ema50 = indicadores[
        "ema50"
    ]

    macd = indicadores[
        "macd"
    ]

    macd_signal = indicadores[
        "macd_signal"
    ]

    tendencia = 0.0

    if (
        precio > ema9
        > ema21
        > ema50
    ):

        tendencia += 10.0

        razones.append(
            "Estructura EMA alcista"
        )

    elif (
        precio < ema9
        < ema21
        < ema50
    ):

        tendencia -= 10.0

        razones.append(
            "Estructura EMA bajista"
        )

    elif ema9 > ema21:

        tendencia += 5.0

        razones.append(
            "EMA9 sobre EMA21"
        )

    elif ema9 < ema21:

        tendencia -= 5.0

        razones.append(
            "EMA9 bajo EMA21"
        )

    if (
        macd
        > macd_signal
    ):

        tendencia += 4.0

        razones.append(
            "MACD confirma arriba"
        )

    elif (
        macd
        < macd_signal
    ):

        tendencia -= 4.0

        razones.append(
            "MACD confirma abajo"
        )

    familias[
        "tendencia"
    ] = limitar(
        tendencia,
        -14.0,
        14.0,
    )

    moms = [
        indicadores[
            "mom1"
        ],
        indicadores[
            "mom3"
        ],
        indicadores[
            "mom5"
        ],
        indicadores[
            "mom10"
        ],
    ]

    votos_up = sum(
        1
        for x in moms
        if x > 0
    )

    votos_down = sum(
        1
        for x in moms
        if x < 0
    )

    velocidad = indicadores[
        "velocidad"
    ]

    aceleracion = indicadores[
        "aceleracion"
    ]

    momentum_score = 0.0

    if votos_up >= 3:

        momentum_score += 7.0

        razones.append(
            "Momentum mayormente alcista"
        )

    elif votos_down >= 3:

        momentum_score -= 7.0

        razones.append(
            "Momentum mayormente bajista"
        )

    if velocidad > 0:
        momentum_score += 3.0

    elif velocidad < 0:
        momentum_score -= 3.0

    if (
        velocidad > 0
        and aceleracion > 0
    ):

        momentum_score += 3.0

        razones.append(
            "Precio acelerando arriba"
        )

    elif (
        velocidad < 0
        and aceleracion < 0
    ):

        momentum_score -= 3.0

        razones.append(
            "Precio acelerando abajo"
        )

    familias[
        "momentum"
    ] = limitar(
        momentum_score,
        -13.0,
        13.0,
    )

    obi_total = media_valida(
        [
            obi_cb,
            obi_kr,
            obi_ka,
            obi_bi,
            obi_bf,
        ]
    )

    if obi_total is None:
        obi_total = 0.0

    flujo_cb = orderflow_cb.get(
        "imbalance",
        0.0,
    )

    flujo_kr = orderflow_kr.get(
        "imbalance",
        0.0,
    )

    flujo_bi = orderflow_bi.get(
        "imbalance",
        0.0,
    )

    flujo_bf = orderflow_bf.get(
        "imbalance",
        0.0,
    )

    orderflow_total = media_valida(
        [
            flujo_cb,
            flujo_kr,
            flujo_bi,
            flujo_bf,
        ]
    )

    if orderflow_total is None:
        orderflow_total = 0.0

    micro = 0.0

    if obi_total >= 0.20:

        micro += 7.0

        razones.append(
            "Order books compradores"
        )

    elif obi_total >= 0.08:

        micro += 4.0

    elif obi_total <= -0.20:

        micro -= 7.0

        razones.append(
            "Order books vendedores"
        )

    elif obi_total <= -0.08:

        micro -= 4.0

    if orderflow_total >= 0.20:

        micro += 7.0

        razones.append(
            "Trades agresivos compradores"
        )

    elif orderflow_total >= 0.08:

        micro += 4.0

    elif orderflow_total <= -0.20:

        micro -= 7.0

        razones.append(
            "Trades agresivos vendedores"
        )

    elif orderflow_total <= -0.08:

        micro -= 4.0

    if (
        obi_total > 0.08
        and orderflow_total > 0.08
    ):

        micro += 2.0

        razones.append(
            "OBI + order flow coinciden arriba"
        )

    elif (
        obi_total < -0.08
        and orderflow_total < -0.08
    ):

                micro += 2.0

        razones.append(
            "OBI + order flow coinciden arriba"
        )

    elif (
        obi_total < -0.08
        and orderflow_total < -0.08
    ):

        micro -= 2.0

        razones.append(
            "OBI + order flow coinciden abajo"
        )

    tapesurf_depth = safe_float(
        tapesurf.get(
            "imbalance_depth"
        ),
        0.0,
    )

    tapesurf_flow = safe_float(
        tapesurf.get(
            "imbalance_orderflow"
        ),
        0.0,
    )

    if (
        tapesurf_depth >= 0.10
        and tapesurf_flow >= 0.10
    ):

        micro += 2.0

        razones.append(
            "TapeSurf apoya subida"
        )

    elif (
        tapesurf_depth <= -0.10
        and tapesurf_flow <= -0.10
    ):

        micro -= 2.0

        razones.append(
            "TapeSurf apoya caída"
        )

    familias[
        "microestructura"
    ] = limitar(
        micro,
        -20.0,
        20.0,
    )

    rsi = indicadores[
        "rsi14"
    ]

    cmf = indicadores[
        "cmf20"
    ]

    volumen_relativo = indicadores[
        "volumen_relativo"
    ]

    flujo_capital = 0.0

    if 55 <= rsi <= 72:

        flujo_capital += 3.0

        razones.append(
            "RSI favorable arriba "
            f"{rsi:.1f}"
        )

    elif 28 <= rsi <= 45:

        flujo_capital -= 3.0

        razones.append(
            "RSI favorable abajo "
            f"{rsi:.1f}"
        )

    elif rsi > 80:
        flujo_capital -= 1.0

    elif rsi < 20:
        flujo_capital += 1.0

    if cmf > 0.10:

        flujo_capital += 5.0

        razones.append(
            "CMF comprador "
            f"{cmf:+.2f}"
        )

    elif cmf < -0.10:

        flujo_capital -= 5.0

        razones.append(
            "CMF vendedor "
            f"{cmf:+.2f}"
        )

    if volumen_relativo >= 1.50:

        direccion_base = (
            familias[
                "tendencia"
            ]
            +
            familias[
                "momentum"
            ]
        )

        if direccion_base > 0:

            flujo_capital += 2.0

            razones.append(
                "Volumen alto confirma subida"
            )

        elif direccion_base < 0:

            flujo_capital -= 2.0

            razones.append(
                "Volumen alto confirma caída"
            )

    familias[
        "flujo_capital"
    ] = limitar(
        flujo_capital,
        -10.0,
        10.0,
    )

    consenso = calcular_consenso_fuentes(
        target,
        precios_fuentes,
    )

    consenso_score = 0.0

    if consenso[
        "total"
    ] >= 2:

        if consenso[
            "ratio"
        ] >= 1.0:

            consenso_score = 10.0

            razones.append(
                "Todas las fuentes sobre target"
            )

        elif consenso[
            "ratio"
        ] <= -1.0:

            consenso_score = -10.0

            razones.append(
                "Todas las fuentes bajo target"
            )

        elif consenso[
            "ratio"
        ] >= 0.50:

            consenso_score = 6.0

            razones.append(
                "Mayoría de fuentes arriba"
            )

        elif consenso[
            "ratio"
        ] <= -0.50:

            consenso_score = -6.0

            razones.append(
                "Mayoría de fuentes abajo"
            )

        elif consenso[
            "ratio"
        ] > 0:

            consenso_score = 3.0

        elif consenso[
            "ratio"
        ] < 0:

            consenso_score = -3.0

    familias[
        "consenso"
    ] = consenso_score

    score = sum(
        familias.values()
    )

    score = limitar(
        score,
        -100.0,
        100.0,
    )

    return {
        "score":
        score,

        "distancia_target_pct":
        distancia_pct,

        "obi":
        obi_total,

        "orderflow":
        orderflow_total,

        "consenso":
        consenso,

        "familias":
        familias,

        "razones":
        razones,
    }


# ============================================================
# SCORE -> PROBABILIDAD
# ============================================================

def score_a_prob_arriba(
    score,
):
    prob = (
        1.0
        /
        (
            1.0
            +
            math.exp(
                -score
                / 18.0
            )
        )
    )

    return limitar(
        prob,
        0.05,
        0.95,
    )


# ============================================================
# DECISION
# ============================================================

def decidir(
    score,
    prob_arriba,
    yes_ask,
    no_ask,
    distancia_target_pct,
):
    prob_abajo = (
        1.0
        - prob_arriba
    )

    score_abs = abs(
        score
    )

    zona_muerta = (
        abs(
            distancia_target_pct
        )
        < TARGET_ZONA_MUERTA_PCT
    )

    if score > 0:

        prob = (
            prob_arriba
            * 100.0
        )

        precio_entrada = (
            yes_ask
        )

        if precio_entrada is None:

            return {
                "decision": "NO APOSTAR",
                "fuerza": "SIN PRECIO",
                "probabilidad": prob,
                "edge": None,
                "precio_entrada": None,
                "lado": None,
            }

        edge = (
            prob_arriba
            - precio_entrada
        )

        if (
            prob
            >= PROBABILIDAD_MINIMA_APUESTA
            and prob
            >= PROBABILIDAD_FUERTE
            and score_abs
            >= SCORE_FUERTE
            and edge
            >= EDGE_MINIMO_FUERTE
        ):

            return {
                "decision": "ARRIBA",
                "fuerza": "FUERTE",
                "probabilidad": prob,
                "edge": edge,
                "precio_entrada": precio_entrada,
                "lado": "YES",
            }

        if (
            prob
            >= PROBABILIDAD_MINIMA_APUESTA
            and prob
            >= PROBABILIDAD_MEDIA
            and score_abs
            >= SCORE_MEDIO
            and edge
            >= EDGE_MINIMO_MEDIO
            and not zona_muerta
        ):

            return {
                "decision": "ARRIBA",
                "fuerza": "MEDIA",
                "probabilidad": prob,
                "edge": edge,
                "precio_entrada": precio_entrada,
                "lado": "YES",
            }

    if score < 0:

        prob = (
            prob_abajo
            * 100.0
        )

        precio_entrada = (
            no_ask
        )

        if precio_entrada is None:

            return {
                "decision": "NO APOSTAR",
                "fuerza": "SIN PRECIO",
                "probabilidad": prob,
                "edge": None,
                "precio_entrada": None,
                "lado": None,
            }

        edge = (
            prob_abajo
            - precio_entrada
        )

        if (
            prob
            >= PROBABILIDAD_MINIMA_APUESTA
            and prob
            >= PROBABILIDAD_FUERTE
            and score_abs
            >= SCORE_FUERTE
            and edge
            >= EDGE_MINIMO_FUERTE
        ):

            return {
                "decision": "ABAJO",
                "fuerza": "FUERTE",
                "probabilidad": prob,
                "edge": edge,
                "precio_entrada": precio_entrada,
                "lado": "NO",
            }

        if (
            prob
            >= PROBABILIDAD_MINIMA_APUESTA
            and prob
            >= PROBABILIDAD_MEDIA
            and score_abs
            >= SCORE_MEDIO
            and edge
            >= EDGE_MINIMO_MEDIO
            and not zona_muerta
        ):

            return {
                "decision": "ABAJO",
                "fuerza": "MEDIA",
                "probabilidad": prob,
                "edge": edge,
                "precio_entrada": precio_entrada,
                "lado": "NO",
            }

    prob_mayor = max(
        prob_arriba,
        prob_abajo,
    ) * 100.0

    return {
        "decision": "NO APOSTAR",
        "fuerza": "DEBIL",
        "probabilidad": prob_mayor,
        "edge": None,
        "precio_entrada": None,
        "lado": None,
    }


# ============================================================
# HISTORIAL
# ============================================================

def cargar_historial():
    if not os.path.exists(
        HISTORIAL_FILE
    ):
        return []

    try:
        with open(
            HISTORIAL_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            datos = json.load(
                f
            )

        if isinstance(
            datos,
            list,
        ):
            return datos

    except Exception as e:
        print(
            "[HISTORIAL] "
            f"Error leyendo: {e}"
        )

    return []


def guardar_historial(
    historial,
):
    temporal = (
        HISTORIAL_FILE
        + ".tmp"
    )

    try:
        with open(
            temporal,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                historial,
                f,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(
            temporal,
            HISTORIAL_FILE,
        )

    except Exception as e:
        print(
            "[HISTORIAL] "
            f"Error guardando: {e}"
        )


def buscar_registro(
    historial,
    ticker,
):
    for registro in historial:

        if (
            registro.get(
                "ticker"
            )
            == ticker
        ):
            return registro

    return None


# ============================================================
# P&L TEORICO
# ============================================================

def calcular_pnl_teorico(
    decision,
    resultado_final,
    precio_entrada,
):
    if decision not in [
        "ARRIBA",
        "ABAJO",
    ]:
        return None

    if precio_entrada is None:
        return None

    if (
        decision
        == resultado_final
    ):

        return (
            1.0
            - precio_entrada
        )

    return (
        -precio_entrada
    )


# ============================================================
# RESULTADO OFICIAL KALSHI
# ============================================================

def actualizar_resultados():
    historial = cargar_historial()

    cambio = False

    for registro in historial:

        if (
            registro.get(
                "resultado"
            )
            is not None
        ):
            continue

        ticker = registro.get(
            "ticker"
        )

        if not ticker:
            continue

        mercado = obtener_mercado_por_ticker(
            ticker
        )

        if not mercado:
            continue

        resultado = str(
            mercado.get(
                "result",
                "",
            )
        ).lower()

        if resultado not in [
            "yes",
            "no",
        ]:
            continue

        resultado_final = (
            "ARRIBA"
            if resultado == "yes"
            else "ABAJO"
        )

        decision = registro.get(
            "decision"
        )

        registro[
            "resultado"
        ] = resultado_final

        registro[
            "resultado_kalshi"
        ] = resultado

        registro[
            "resultado_actualizado"
        ] = iso_utc()

        if (
            decision
            == "NO APOSTAR"
        ):

            registro[
                "evaluacion"
            ] = "NO CONTABILIZA"

            registro[
                "pnl_teorico_1_contrato"
            ] = None

        elif (
            decision
            == resultado_final
        ):

            registro[
                "evaluacion"
            ] = "ACIERTO"

            registro[
                "pnl_teorico_1_contrato"
            ] = calcular_pnl_teorico(
                decision,
                resultado_final,
                registro.get(
                    "precio_entrada"
                ),
            )

        else:

            registro[
                "evaluacion"
            ] = "FALLO"

            registro[
                "pnl_teorico_1_contrato"
            ] = calcular_pnl_teorico(
                decision,
                resultado_final,
                registro.get(
                    "precio_entrada"
                ),
            )

        precio_entrada = registro.get(
            "precio_entrada"
        )

        pnl = registro.get(
            "pnl_teorico_1_contrato"
        )

        if (
            precio_entrada is not None
            and precio_entrada > 0
            and pnl is not None
        ):

            registro[
                "roi_teorico_pct"
            ] = (
                pnl
                / precio_entrada
            ) * 100.0

        else:

            registro[
                "roi_teorico_pct"
            ] = None

        cambio = True

        print("")
        print(
            "========================================"
        )

        print(
            "[RESULTADO KALSHI]"
        )

        print(
            f"Ticker: {ticker}"
        )

        print(
            f"Predicción: {decision}"
        )

        print(
            "Resultado oficial: "
            f"{resultado_final}"
        )

        print(
            "Evaluación: "
            f"{registro['evaluacion']}"
        )

        if (
            registro.get(
                "pnl_teorico_1_contrato"
            )
            is not None
        ):

            print(
                "P&L teórico: "
                f"${registro['pnl_teorico_1_contrato']:+.4f}"
            )

        print(
            "========================================"
        )
        print("")

    if cambio:
        guardar_historial(
            historial
        )


# ============================================================
# ANALISIS COMPLETO
# ============================================================

def analizar_mercado(
    mercado,
):
    ticker = mercado.get(
        "ticker"
    )

    if not ticker:
        return None

    target = extraer_target_kalshi(
        mercado
    )

    if target is None:

        print(
            "[KALSHI] "
            "Mercado sin target."
        )

        return None

    close_time = parse_fecha(
        mercado.get(
            "close_time"
        )
    )

    open_time = parse_fecha(
        mercado.get(
            "open_time"
        )
    )

    ahora = ahora_utc()

    segundos_restantes = None

    segundos_desde_apertura = None

    minuto_entrada = None

    if close_time is not None:

        segundos_restantes = (
            close_time
            - ahora
        ).total_seconds()

    if open_time is not None:

        segundos_desde_apertura = (
            ahora
            - open_time
        ).total_seconds()

        minuto_entrada = (
            segundos_desde_apertura
            / 60.0
        )

    cb = obtener_coinbase_ticker()

    kr = obtener_kraken_ticker()

    cmc = obtener_coinmarketcap()

    cf = obtener_cf_brti()

    precio = construir_precio_consenso(
        cb,
        kr,
        cmc,
        cf,
    )

    fuentes_disponibles = sum(
        1
        for x in [
            cb,
            kr,
            cmc,
            cf,
        ]
        if x is not None
    )

    if (
        precio is None
        or fuentes_disponibles < 2
    ):

        print(
            "[PRECIO] "
            "No hay suficientes fuentes."
        )

        return None

    candles = obtener_coinbase_candles()

    indicadores = construir_indicadores(
        candles
    )

    if indicadores is None:

        print(
            "[INDICADORES] "
            "No hay suficientes velas."
        )

        return None

    cb_book = obtener_coinbase_book()

    kr_book = obtener_kraken_book()

    bi_book = obtener_binance_book()

    bf_book = obtener_bitfinex_book()

    ka_book = obtener_orderbook_kalshi(
        ticker
    )

    obi_cb = obi_coinbase(
        cb_book
    )

    obi_kr = obi_kraken(
        kr_book
    )

    obi_bi = obi_binance(
        bi_book
    )

    obi_bf = obi_bitfinex(
        bf_book
    )

    obi_ka = obi_kalshi(
        ka_book
    )

    profundidad_cb = profundidad_coinbase(
        cb_book
    )

    profundidad_kr = profundidad_kraken(
        kr_book
    )

    profundidad_bi = profundidad_binance(
        bi_book
    )

    profundidad_bf = profundidad_bitfinex(
        bf_book
    )

    profundidad_ka = profundidad_kalshi(
        ka_book
    )

    spread_cb = spread_coinbase(
        cb_book
    )

    trades_cb = obtener_coinbase_trades()

    trades_kr = obtener_kraken_trades()

    trades_bi = obtener_binance_trades()

    trades_bf = obtener_bitfinex_trades()

    flujo_cb = orderflow_coinbase(
        trades_cb
    )

    flujo_kr = orderflow_kraken(
        trades_kr
    )

    flujo_bi = orderflow_binance(
        trades_bi
    )

    flujo_bf = orderflow_bitfinex(
        trades_bf
    )

    tapesurf = calcular_metricas_tapesurf(
        profundidad_cb,
        profundidad_kr,
        profundidad_bi,
        profundidad_bf,
        flujo_cb,
        flujo_kr,
        flujo_bi,
        flujo_bf,
    )

    mercado_actual = (
        obtener_mercado_por_ticker(
            ticker
        )
        or mercado
    )

    yes_ask = precio_yes_ask(
        mercado_actual
    )

    no_ask = precio_no_ask(
        mercado_actual
    )

    calculo = calcular_score(
        target=target,
        precio=precio,
        indicadores=indicadores,
        obi_cb=obi_cb,
        obi_kr=obi_kr,
        obi_ka=obi_ka,
        obi_bi=obi_bi,
        obi_bf=obi_bf,
        orderflow_cb=flujo_cb,
        orderflow_kr=flujo_kr,
        orderflow_bi=flujo_bi,
        orderflow_bf=flujo_bf,   
        precios_fuentes=[
            cb,
            kr,
            cmc,
            cf,
        ],
        tapesurf=tapesurf,
    )

    score = calculo[
        "score"
    ]

    prob_arriba = score_a_prob_arriba(
        score
    )

    decision = decidir(
        score=score,
        prob_arriba=prob_arriba,
        yes_ask=yes_ask,
        no_ask=no_ask,
        distancia_target_pct=(
            calculo[
                "distancia_target_pct"
            ]
        ),
    )

    return {
        "version":
        VERSION_MOTOR,

        "ticker":
        ticker,

        "event_ticker":
        mercado.get(
            "event_ticker"
        ),

        "timestamp":
        iso_utc(),

        "hora_local":
        ahora_local().isoformat(),

        "target":
        target,

        "precio_consenso":
        precio,

        "precio_cf_brti":
        cf,

        "precio_coinbase":
        cb,

        "precio_kraken":
        kr,

        "precio_coinmarketcap":
        cmc,

        "fuentes_disponibles":
        fuentes_disponibles,

        "yes_ask":
        yes_ask,

        "no_ask":
        no_ask,

        "precio_entrada":
        decision[
            "precio_entrada"
        ],

        "lado_contrato":
        decision[
            "lado"
        ],

        "segundos_restantes":
        segundos_restantes,

        "segundos_desde_apertura":
        segundos_desde_apertura,

        "minuto_entrada":
        minuto_entrada,

        "distancia_target_pct":
        calculo[
            "distancia_target_pct"
        ],

        "score":
        score,

        "score_familias":
        calculo[
            "familias"
        ],

        "probabilidad_arriba":
        (
            prob_arriba
            * 100.0
        ),

        "probabilidad_abajo":
        (
            (
                1.0
                - prob_arriba
            )
            * 100.0
        ),

        "decision":
        decision[
            "decision"
        ],

        "fuerza":
        decision[
            "fuerza"
        ],

        "probabilidad":
        decision[
            "probabilidad"
        ],

        "edge":
        decision[
            "edge"
        ],

        "ema9":
        indicadores[
            "ema9"
        ],

        "ema21":
        indicadores[
            "ema21"
        ],

        "ema50":
        indicadores[
            "ema50"
        ],

        "rsi14":
        indicadores[
            "rsi14"
        ],

        "macd":
        indicadores[
            "macd"
        ],

        "macd_signal":
        indicadores[
            "macd_signal"
        ],

        "cmf20":
        indicadores[
            "cmf20"
        ],

        "momentum_1m":
        indicadores[
            "mom1"
        ],

        "momentum_3m":
        indicadores[
            "mom3"
        ],

        "momentum_5m":
        indicadores[
            "mom5"
        ],

        "momentum_10m":
        indicadores[
            "mom10"
        ],

        "velocidad":
        indicadores[
            "velocidad"
        ],

        "aceleracion":
        indicadores[
            "aceleracion"
        ],

        "volatilidad20":
        indicadores[
            "vol20"
        ],

        "volumen":
        indicadores[
            "volume"
        ],

        "volumen_promedio20":
        indicadores[
            "volume_avg20"
        ],

        "volumen_relativo":
        indicadores[
            "volumen_relativo"
        ],

        "obi_coinbase":
        obi_cb,

        "obi_kraken":
        obi_kr,

        "obi_binance":
        obi_bi,

        "obi_bitfinex":
        obi_bf,

        "obi_kalshi":
        obi_ka,

        "obi_promedio":
        calculo[
            "obi"
        ],

        "orderflow_coinbase":
        flujo_cb,

        "orderflow_kraken":
        flujo_kr,

        "orderflow_binance":
        flujo_bi,

        "orderflow_bitfinex":
        flujo_bf,

        "orderflow_promedio":
        calculo[
            "orderflow"
        ],

        "profundidad_coinbase":
        profundidad_cb,

        "profundidad_kraken":
        profundidad_kr,

        "profundidad_binance":
        profundidad_bi,

        "profundidad_bitfinex":
        profundidad_bf,

        "profundidad_kalshi":
        profundidad_ka,

        "tapesurf_agregado":
        tapesurf,

        "spread_coinbase":
        spread_cb,

        "consenso_fuentes":
        calculo[
            "consenso"
        ],

        "razones":
        calculo[
            "razones"
        ],

        "resultado":
        None,

        "resultado_kalshi":
        None,

        "resultado_actualizado":
        None,

        "evaluacion":
        None,

        "pnl_teorico_1_contrato":
        None,

        "roi_teorico_pct":
        None,
    }


# ============================================================
# MOSTRAR ANALISIS
# ============================================================

def mostrar_analisis(a):
    print("")
    print(
        "========================================"
    )
    print(
        " MOTOR KALSHI BTC 15M"
    )
    print(
        "========================================"
    )

    print(
        f"Ticker: {a['ticker']}"
    )

    print(
        "Target Kalshi: "
        f"${a['target']:,.2f}"
    )

    print(
        "BTC consenso: "
        f"${a['precio_consenso']:,.2f}"
    )

    print(
        "Distancia target: "
        f"{a['distancia_target_pct']:+.4f}%"
    )

    print("")

    print(
        "CF BRTI: "
        f"{a['precio_cf_brti']}"
    )

    print(
        "Coinbase: "
        f"{a['precio_coinbase']}"
    )

    print(
        "Kraken: "
        f"{a['precio_kraken']}"
    )

    print(
        "CoinMarketCap: "
        f"{a['precio_coinmarketcap']}"
    )

    print("")

    print(
        f"EMA 9: "
        f"{a['ema9']:.2f}"
    )

    print(
        f"EMA 21: "
        f"{a['ema21']:.2f}"
    )

    print(
        f"EMA 50: "
        f"{a['ema50']:.2f}"
    )

    print(
        f"RSI 14: "
        f"{a['rsi14']:.2f}"
    )

    print(
        f"CMF 20: "
        f"{a['cmf20']:+.3f}"
    )

    print(
        "Volumen relativo: "
        f"{a['volumen_relativo']:.2f}x"
    )

    print(
        "Velocidad: "
        f"{a['velocidad'] * 100:+.4f}%"
    )

    print(
        "Aceleración: "
        f"{a['aceleracion'] * 100:+.4f}%"
    )

    print("")

    print(
        "OBI Coinbase: "
        f"{a['obi_coinbase']:+.3f}"
    )

    print(
        "OBI Kraken: "
        f"{a['obi_kraken']:+.3f}"
    )

    print(
        "OBI Binance: "
        f"{a['obi_binance']:+.3f}"
    )

    print(
        "OBI Bitfinex: "
        f"{a['obi_bitfinex']:+.3f}"
    )

    print(
        "OBI Kalshi: "
        f"{a['obi_kalshi']:+.3f}"
    )

    print(
        "OBI promedio: "
        f"{a['obi_promedio']:+.3f}"
    )

    print(
        "Order flow Coinbase: "
        f"{a['orderflow_coinbase']['imbalance']:+.3f}"
    )

    print(
        "Order flow Kraken: "
        f"{a['orderflow_kraken']['imbalance']:+.3f}"
    )

    print(
        "Order flow Binance: "
        f"{a['orderflow_binance']['imbalance']:+.3f}"
    )

    print(
        "Order flow Bitfinex: "
        f"{a['orderflow_bitfinex']['imbalance']:+.3f}"
    )

    print(
        "Order flow promedio: "
        f"{a['orderflow_promedio']:+.3f}"
    )

    print("")

    print(
        "TapeSurf agregado BID: "
        f"{a['tapesurf_agregado']['bid']:.3f}"
    )

    print(
        "TapeSurf agregado ASK: "
        f"{a['tapesurf_agregado']['ask']:.3f}"
    )

    print(
        "TapeSurf delta profundidad: "
        f"{a['tapesurf_agregado']['delta_depth']:+.3f}"
    )

    print(
        "TapeSurf imbalance profundidad: "
        f"{a['tapesurf_agregado']['imbalance_depth']:+.3f}"
    )

    print(
        "TapeSurf delta order flow: "
        f"{a['tapesurf_agregado']['delta_orderflow']:+.3f}"
    )

    print(
        "TapeSurf imbalance order flow: "
        f"{a['tapesurf_agregado']['imbalance_orderflow']:+.3f}"
    )

    print("")

    print(
        f"Score: "
        f"{a['score']:+.2f}"
    )

    print(
        "Prob. ARRIBA: "
        f"{a['probabilidad_arriba']:.1f}%"
    )

    print(
        "Prob. ABAJO: "
        f"{a['probabilidad_abajo']:.1f}%"
    )

    print(
        "Kalshi YES ask: "
        f"{a['yes_ask']}"
    )

    print(
        "Kalshi NO ask: "
        f"{a['no_ask']}"
    )

    print("")
    print(
        ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    )

    print(
        "PREDICCION: "
        f"{a['decision']}"
    )

    print(
        "FUERZA: "
        f"{a['fuerza']}"
    )

    print(
        "PROBABILIDAD: "
        f"{a['probabilidad']:.1f}%"
    )

    if (
        a[
            "precio_entrada"
        ]
        is not None
    ):

        print(
            "PRECIO ENTRADA: "
            f"${a['precio_entrada']:.3f}"
        )

    if (
        a[
            "edge"
        ]
        is not None
    ):

        print(
            "EDGE ESTIMADO: "
            f"{a['edge'] * 100:+.2f}%"
        )

    print(
        "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    )

    if (
        a[
            "minuto_entrada"
        ]
        is not None
    ):

        print(
            "Minuto del contrato: "
            f"{a['minuto_entrada']:.2f}"
        )

    if (
        a[
            "segundos_restantes"
        ]
        is not None
    ):

        print(
            "Tiempo restante: "
            f"{int(a['segundos_restantes'])} s"
        )

    print(
        "========================================"
    )
    print("")


# ============================================================
# GUARDAR DECISION
# ============================================================

def guardar_si_corresponde(
    analisis,
):
    historial = cargar_historial()

    ticker = analisis[
        "ticker"
    ]

    existente = buscar_registro(
        historial,
        ticker,
    )

    if existente is not None:
        return False

    segundos_restantes = analisis[
        "segundos_restantes"
    ]

    segundos_desde_apertura = analisis[
        "segundos_desde_apertura"
    ]

    if (
        segundos_desde_apertura
        is not None
        and segundos_desde_apertura
        < MIN_SEGUNDOS_DESDE_APERTURA
    ):
        return False

    if (
        segundos_restantes
        is not None
        and segundos_restantes
        <= MIN_SEGUNDOS_RESTANTES
    ):

        analisis[
            "decision"
        ] = "NO APOSTAR"

        analisis[
            "fuerza"
        ] = "SIN VENTAJA"

        analisis[
            "precio_entrada"
        ] = None

        analisis[
            "lado_contrato"
        ] = None

        analisis[
            "edge"
        ] = None

        historial.append(
            analisis
        )

        guardar_historial(
            historial
        )

        print(
            "[FINAL] "
            "Contrato guardado como "
            "NO APOSTAR."
        )

        return True

    if analisis[
        "decision"
    ] in [
        "ARRIBA",
        "ABAJO",
    ]:

        probabilidad = safe_float(
            analisis.get(
                "probabilidad"
            ),
            0.0,
        )

        if (
            probabilidad
            < PROBABILIDAD_MINIMA_APUESTA
        ):

            analisis[
                "decision"
            ] = "NO APOSTAR"

            analisis[
                "fuerza"
            ] = "PROBABILIDAD < 90%"

            analisis[
                "precio_entrada"
            ] = None

            analisis[
                "lado_contrato"
            ] = None

            analisis[
                "edge"
            ] = None

    if analisis[
        "decision"
    ] in [
        "ARRIBA",
        "ABAJO",
    ]:

        historial.append(
            analisis
        )

        guardar_historial(
            historial
        )

        print(
            "[DECISION GUARDADA] "
            f"{analisis['decision']}"
        )

        if (
            analisis[
                "minuto_entrada"
            ]
            is not None
        ):

            print(
                "[ENTRADA] "
                f"Minuto "
                f"{analisis['minuto_entrada']:.2f}"
            )

        if (
            analisis[
                "precio_entrada"
            ]
            is not None
        ):

            print(
                "[PRECIO KALSHI] "
                f"{analisis['precio_entrada']:.3f}"
            )

        if (
            analisis[
                "edge"
            ]
            is not None
        ):

            print(
                "[EDGE] "
                f"{analisis['edge'] * 100:+.2f}%"
            )

        enviar_telegram(
            analisis
        )

        return True

    if (
        analisis[
            "decision"
        ]
        == "NO APOSTAR"
    ):

        analisis[
            "precio_entrada"
        ] = None

        analisis[
            "lado_contrato"
        ] = None

        analisis[
            "edge"
        ] = None

        historial.append(
            analisis
        )

        guardar_historial(
            historial
        )

        print(
            "[DECISION GUARDADA] "
            "NO APOSTAR"
        )

        print(
            "[PROBABILIDAD] "
            f"{analisis['probabilidad']:.1f}%"
        )

        return True

    return False


# ============================================================
# FINAL SIN DECISION
# ============================================================

def guardar_no_apostar_final(
    mercado,
):
    historial = cargar_historial()

    ticker = mercado.get(
        "ticker"
    )

    if not ticker:
        return

    if buscar_registro(
        historial,
        ticker,
    ):
        return

    analisis = analizar_mercado(
        mercado
    )

    if analisis is None:
        return

    analisis[
        "decision"
    ] = "NO APOSTAR"

    analisis[
        "fuerza"
    ] = "SIN VENTAJA"

    analisis[
        "precio_entrada"
    ] = None

    analisis[
        "lado_contrato"
    ] = None

    analisis[
        "edge"
    ] = None

    historial.append(
        analisis
    )

    guardar_historial(
        historial
    )

    print(
        "[FINAL] "
        "Contrato anterior guardado "
        "como NO APOSTAR."
    )


# ============================================================
# ESTADISTICAS
# ============================================================

def mostrar_estadisticas():
    historial = cargar_historial()

    apuestas = [
        x
        for x in historial
        if x.get(
            "decision"
        )
        in [
            "ARRIBA",
            "ABAJO",
        ]
    ]

    resueltas = [
        x
        for x in apuestas
        if x.get(
            "evaluacion"
        )
        in [
            "ACIERTO",
            "FALLO",
        ]
    ]

    if not resueltas:
        return

    aciertos = sum(
        1
        for x in resueltas
        if x.get(
            "evaluacion"
        )
        == "ACIERTO"
    )

    fallos = sum(
        1
        for x in resueltas
        if x.get(
            "evaluacion"
        )
        == "FALLO"
    )

    total = len(
        resueltas
    )

    precision = (
        aciertos
        / total
    ) * 100.0

    pnl_total = sum(
        safe_float(
            x.get(
                "pnl_teorico_1_contrato"
            ),
            0.0,
        )
        for x in resueltas
    )

    print("")
    print(
        "========================================"
    )
    print(
        "[ESTADISTICAS]"
    )

    print(
        f"Operaciones resueltas: "
        f"{total}"
    )

    print(
        f"Aciertos: "
        f"{aciertos}"
    )

    print(
        f"Fallos: "
        f"{fallos}"
    )

    print(
        f"Precisión: "
        f"{precision:.2f}%"
    )

    print(
        "P&L teórico acumulado: "
        f"${pnl_total:+.4f}"
    )

    print(
        "========================================"
    )
    print("")


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():
    global ULTIMO_RESULTADO_CHECK

    print("")
    print(
        "========================================"
    )

    print(
        " MOTOR BTC 15M INICIADO"
    )

    print(
        f" VERSION: "
        f"{VERSION_MOTOR}"
    )

    print(
        " MODO: PROFIT ENGINE"
    )

    print(
        " DECISIONES:"
    )

    print(
        " ARRIBA / ABAJO / NO APOSTAR"
    )

    print(
        " ARRIBA / ABAJO SOLO CON 90%+"
    )

    print(
        " BITFINEX: ACTIVO"
    )

    print(
        " METRICAS TIPO TAPESURF: ACTIVAS"
    )

    print(
        " NO COLOCA ORDENES REALES"
    )

    print(
        "========================================"
    )
    print("")

    ticker_anterior = None

    mercado_anterior = None

    while not DETENER:

        try:
            ahora = time.time()

            if (
                ahora
                - ULTIMO_RESULTADO_CHECK
                >= INTERVALO_RESULTADOS
            ):

                actualizar_resultados()

                mostrar_estadisticas()

                ULTIMO_RESULTADO_CHECK = (
                    ahora
                )

            mercado = elegir_mercado_actual()

            if mercado is None:

                print(
                    "[KALSHI] "
                    "No hay mercado BTC 15M abierto."
                )

                dormir_interrumpible(
                    INTERVALO_REVISION
                )

                continue

            ticker = mercado.get(
                "ticker"
            )

            if not ticker:

                dormir_interrumpible(
                    INTERVALO_REVISION
                )

                continue

            if (
                ticker_anterior
                and ticker
                != ticker_anterior
                and mercado_anterior
                is not None
            ):

                guardar_no_apostar_final(
                    mercado_anterior
                )

            ticker_anterior = ticker

            mercado_anterior = mercado

            historial = cargar_historial()

            existente = buscar_registro(
                historial,
                ticker,
            )

            if existente is not None:

                print(
                    f"[{ticker}] "
                    "Decisión ya guardada: "
                    f"{existente.get('decision')}"
                )

                dormir_interrumpible(
                    INTERVALO_REVISION
                )

                continue

            analisis = analizar_mercado(
                mercado
            )

            if analisis is None:

                dormir_interrumpible(
                    INTERVALO_REVISION
                )

                continue

            mostrar_analisis(
                analisis
            )

            guardar_si_corresponde(
                analisis
            )

        except Exception as e:

            print(
                "[MOTOR] "
                f"Error general: {e}"
            )

        dormir_interrumpible(
            INTERVALO_REVISION
        )

    print("")
    print(
        "========================================"
    )

    print(
        " MOTOR BTC 15M DETENIDO"
    )

    print(
        " Cancelación completada correctamente."
    )

    print(
        "========================================"
    )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":
    main()
