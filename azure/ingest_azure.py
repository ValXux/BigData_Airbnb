import time
import sys
import json
import pandas as pd
import requests
import re
from confluent_kafka import Producer

# ==============================================================================
# 1. CONFIGURACIÓN DE CONEXIÓN AZURE
# ==============================================================================
CONNECTION_STRING = ""

# El nombre de tu espacio de nombres
EVENT_HUB_NAMESPACE = "eh-airbnb"

# ==============================================================================
# 2. CONFIGURACIÓN DE DATOS (CASO ACTUAL: SANTIAGO DE CHILE)
# ==============================================================================
CURRENT_CITY_CONFIG = {
    "path": "chile/rm/santiago",
    "meta": {"country": "Chile", "region": "RM", "city": "Santiago"}
}

# ==============================================================================
# BLOQUE DE ESCALABILIDAD (PARA EXPLICACIÓN AL PROFESOR)
# ==============================================================================
# (Este código está comentado. Se usaría si quisiéramos descargar múltiples ciudades a la vez)
#
# MULTI_CITY_CONFIG = [
#     {"path": "chile/rm/santiago",          "meta": {"country": "Chile", "city": "Santiago"}},
#     {"path": "mexico/df/mexico-city",      "meta": {"country": "Mexico", "city": "CDMX"}},
#     {"path": "spain/catalonia/barcelona",  "meta": {"country": "Spain", "city": "Barcelona"}},
#     {"path": "argentina/.../buenos-aires", "meta": {"country": "Argentina", "city": "Buenos Aires"}}
# ]
#
# Lógica de escalado:
# def process_all_cities():
#     for city in MULTI_CITY_CONFIG:
#         print(f"Procesando país: {city['meta']['country']}...")
#         ingest_city_data(city['path'], city['meta'])
#
# ==============================================================================

# Configuración técnica de Kafka para Azure (SASL_SSL)
conf = {
    'bootstrap.servers': f'{EVENT_HUB_NAMESPACE}.servicebus.windows.net:9093',
    'security.protocol': 'SASL_SSL',
    'sasl.mechanism': 'PLAIN',
    'sasl.username': '$ConnectionString',
    'sasl.password': CONNECTION_STRING,
    'client.id': 'python-producer-airbnb-thesis'
}

# Mapeo de archivos a Topics de Azure
TOPICS = {
    "listings": "airbnb_listings_raw",
    "reviews": "airbnb_reviews_raw",
    "neighbourhoods": "airbnb_neighbourhoods_raw"
}

def get_latest_url(city_path, file_name):
    """Busca la URL más reciente en Inside Airbnb usando Scraping"""
    print(f"Buscando URL para {file_name} en [{city_path}]...")
    try:
        resp = requests.get("https://insideairbnb.com/get-the-data/")
        resp.raise_for_status()
        # Busca patrón de fecha (YYYY-MM-DD) en la URL específica de la ciudad
        pattern = rf"https://data\.insideairbnb\.com/{city_path}/(\d{{4}}-\d{{2}}-\d{{2}})/visualisations/{file_name}"
        match = re.search(pattern, resp.text)
        if match:
            return match.group(0), match.group(1)
    except Exception as e:
        print(f"Error buscando URL: {e}")
    return None, None

def delivery_callback(err, msg):
    if err: print(f'Error envío: {err}')

def send_dataframe(df, topic_name, producer):
    """Envía datos a Azure con LIMITADOR DE VELOCIDAD para evitar errores de Policy Violation"""
    total_rows = len(df)
    print(f"Enviando {total_rows} registros a topic [{topic_name}]...")
    
    count = 0
    for _, row in df.iterrows():
        value_json = json.dumps(row.to_dict())
        
        # Bucle de reintento robusto
        while True:
            try:
                producer.produce(topic_name, value_json.encode('utf-8'), callback=delivery_callback)
                break
            except BufferError:
                # Si la cola local se llena, esperamos un poco
                producer.poll(1)

        count += 1
        
        # --- EL FRENO DE MANO (Throttle) ---
        # Cada 50 mensajes, forzamos una pausa pequeña.
        # Esto mantiene la velocidad por debajo de los 1000 eventos/seg de Azure.
        if count % 50 == 0:
            producer.poll(0)
            time.sleep(0.1) # Pausa de 0.1 segundos cada 50 mensajes
            
        # Mostrar progreso cada 2000
        if count % 2000 == 0:
            print(f"   ... {count}/{total_rows} enviados (Velocidad controlada)")
            
    producer.flush()
    print(f"Carga completa en {topic_name}.\n")

def ingest_city_data(city_path, city_meta, producer):
    """Procesa una ciudad completa (Listings, Reviews, Neighbourhoods)"""
    
    # 1. Listings
    url, snap = get_latest_url(city_path, "listings.csv")
    if url:
        print(f"Descargando: {url}")
        df = pd.read_csv(url).fillna("")
        for k, v in city_meta.items(): df[k] = v # Inyectar metadata (Pais, Ciudad)
        df["snapshot_date"] = snap
        send_dataframe(df, TOPICS["listings"], producer)
    
    # 2. Reviews (Limitado para demo)
    url, snap = get_latest_url(city_path, "reviews.csv")
    if url:
        print(f"Descargando: {url}")
        df = pd.read_csv(url).fillna("")
        for k, v in city_meta.items(): df[k] = v
        df["snapshot_date"] = snap
        send_dataframe(df, TOPICS["reviews"], producer)

    # 3. Neighbourhoods
    url, snap = get_latest_url(city_path, "neighbourhoods.csv")
    if url:
        print(f"Descargando: {url}")
        df = pd.read_csv(url)
        for k, v in city_meta.items(): df[k] = v
        df["snapshot_date"] = snap
        send_dataframe(df, TOPICS["neighbourhoods"], producer)

def main():
    print("INICIANDO INGESTA A LA NUBE (AZURE EVENT HUBS)")
    try:
        producer = Producer(conf)
    except Exception as e:
        print(f"Error de configuración: {e}")
        return

    # Ejecutar ingesta para la configuración actual (Chile)
    ingest_city_data(CURRENT_CITY_CONFIG["path"], CURRENT_CITY_CONFIG["meta"], producer)
    
    print("Proceso finalizado.")

if __name__ == "__main__":
    main()