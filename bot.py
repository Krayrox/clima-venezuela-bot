import os
import json
import logging
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

# --- Cargar variables de entorno ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Cargar estados/municipios ---
with open("estados_municipios.json", "r", encoding="utf-8") as f:
    ESTADOS = json.load(f)

# Mapa de municipio -> ciudad real (para geocodificación)
CIUDAD_REFERENCIA = {
    "Libertador": "Caracas", "Baruta": "Caracas", "Chacao": "Caracas",
    "El Hatillo": "Caracas", "Plaza": "Caracas", "Sucre": "Caracas",
    "Vargas": "La Guaira", "Iribarren": "Barquisimeto", "Girardot": "Maracay",
    "Valencia": "Valencia", "Maracaibo": "Maracaibo", "Cabimas": "Cabimas",
    "San Cristóbal": "San Cristóbal", "Maturín": "Maturín",
    "Heres": "Ciudad Bolívar", "Caroní": "Ciudad Guayana",
    "Guanare": "Guanare", "San Fernando": "San Fernando de Apure",
    "Tucupita": "Tucupita", "San Carlos": "San Carlos",
    "Trujillo": "Trujillo", "Valera": "Valera", "San Felipe": "San Felipe",
    "Los Salias": "San Antonio de los Altos", "Naguanagua": "Naguanagua",
    "Puerto Cabello": "Puerto Cabello", "Mariño": "Porlamar",
    "Maneiro": "Pampatar", "Arismendi": "La Asunción",
}


# --- Utilidad: construir teclado en filas de N columnas ---
def construir_teclado(botones, columnas=2):
    filas = []
    fila_actual = []
    for boton in botones:
        fila_actual.append(boton)
        if len(fila_actual) == columnas:
            filas.append(fila_actual)
            fila_actual = []
    if fila_actual:
        filas.append(fila_actual)
    return filas


# --- Obtener coordenadas con Open-Meteo Geocoding (sin API key) ---
def obtener_coordenadas(ciudad: str):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": ciudad, "count": 1, "language": "es", "countryCode": "VE"}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "results" not in data or not data["results"]:
            return None, None
        res = data["results"][0]
        return res["latitude"], res["longitude"]
    except Exception as e:
        logger.error(f"Error geocoding: {e}")
        return None, None


# --- Consulta del clima con Open-Meteo (sin API key) ---
def obtener_clima(ciudad: str) -> str:
    lat, lon = obtener_coordenadas(ciudad)
    if lat is None:
        return f"⚠️ No encontré la ubicación de *{ciudad}*."

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "timezone": "auto",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "current" not in data:
            return f"⚠️ No pude obtener el clima para *{ciudad}*."
        c = data["current"]
        temp = c["temperature_2m"]
        feels = c["apparent_temperature"]
        hum = c["relative_humidity_2m"]
        viento = c["wind_speed_10m"]
        codigo = c["weather_code"]

        descripciones = {
            0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado",
            3: "Nublado", 45: "Niebla", 48: "Niebla con escarcha",
            51: "Llovizna ligera", 53: "Llovizna moderada", 55: "Llovizna densa",
            61: "Lluvia ligera", 63: "Lluvia moderada", 65: "Lluvia fuerte",
            71: "Nieve ligera", 73: "Nieve moderada", 75: "Nieve fuerte",
            80: "Chubascos ligeros", 81: "Chubascos moderados", 82: "Chubascos violentos",
            95: "Tormenta", 96: "Tormenta con granizo ligero", 99: "Tormenta con granizo fuerte",
        }
        desc = descripciones.get(codigo, f"Código {codigo}")

        return (
            f"🌎 *Clima en {ciudad}*\n\n"
            f"🌡️ Temperatura: *{temp}°C* (sensación {feels}°C)\n"
            f"☁️ Estado: *{desc}*\n"
            f"💧 Humedad: *{hum}%*\n"
            f"🌬️ Viento: *{viento} km/h*"
        )
    except Exception as e:
        logger.error(f"Error clima: {e}")
        return "❌ Ocurrió un error consultando el clima."


# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botones = [
        InlineKeyboardButton(estado, callback_data=f"estado|{estado}")
        for estado in ESTADOS.keys()
    ]
    filas = construir_teclado(botones, columnas=2)
    await update.message.reply_text(
        "🇻🇪 *Bot del Clima de Venezuela*\n\nSelecciona un estado:",
        reply_markup=InlineKeyboardMarkup(filas),
        parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("estado|"):
        estado = data.split("|", 1)[1]
        municipios = ESTADOS.get(estado, [])
        botones = [
            InlineKeyboardButton(m, callback_data=f"clima|{m}")
            for m in municipios
        ]
        filas = construir_teclado(botones, columnas=2)
        filas.append([InlineKeyboardButton("⬅️ Volver", callback_data="volver")])
        await query.edit_message_text(
            f"📍 *{estado}*\nSelecciona un municipio:",
            reply_markup=InlineKeyboardMarkup(filas),
            parse_mode="Markdown"
        )

    elif data.startswith("clima|"):
        municipio = data.split("|", 1)[1]
        ciudad = CIUDAD_REFERENCIA.get(municipio, municipio)
        await query.edit_message_text(
            f"⏳ Consultando clima de *{ciudad}*...",
            parse_mode="Markdown"
        )
        resultado = obtener_clima(ciudad)
        filas = [[InlineKeyboardButton("⬅️ Volver al menú", callback_data="volver")]]
        await query.edit_message_text(
            resultado,
            reply_markup=InlineKeyboardMarkup(filas),
            parse_mode="Markdown"
        )

    elif data == "volver":
        botones = [
            InlineKeyboardButton(estado, callback_data=f"estado|{estado}")
            for estado in ESTADOS.keys()
        ]
        filas = construir_teclado(botones, columnas=2)
        await query.edit_message_text(
            "🇻🇪 *Bot del Clima de Venezuela*\n\nSelecciona un estado:",
            reply_markup=InlineKeyboardMarkup(filas),
            parse_mode="Markdown"
        )


# --- Webhook handlers para Render ---
async def telegram_webhook(request):
    """Recibe las actualizaciones de Telegram vía POST."""
    if request.method == "POST":
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    return PlainTextResponse("ok")


async def healthcheck(request):
    """Endpoint para el health check de Render (GET)."""
    return PlainTextResponse("ok")


# --- Main ---
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ Falta TELEGRAM_TOKEN en el archivo .env")

    # Construimos la aplicación de Telegram (necesaria para webhook y polling)
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Modo de ejecución
    if RENDER_EXTERNAL_URL:
        # Producción en Render: webhook
        logger.info("Modo Producción (Webhook) en Render")
        port = int(os.environ.get("PORT", 8443))
        webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"

        # Starlette solo se usa para el webhook
        routes = [
            Route("/", healthcheck),
            Route("/webhook", telegram_webhook, methods=["POST"]),
        ]
        web_app = Starlette(routes=routes)

        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=webhook_url,
        )
    else:
        # Local: polling
        logger.info("Modo Local (Polling)")
        print("✅ Bot iniciado. Presiona Ctrl+C para detenerlo.")
        application.run_polling()