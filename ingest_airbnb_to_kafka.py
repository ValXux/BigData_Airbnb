from kafka import KafkaProducer
import pandas as pd
import requests
import re
import json

# Página general de Inside Airbnb
GET_DATA_URL = "https://insideairbnb.com/get-the-data/"

# De momento trabajamos con Chile / Santiago
CITY_PATH = "chile/rm/santiago"
CITY_META = {
    "country": "Chile",
    "region": "RM",
    "city": "Santiago",
}

# Topics de Kafka
BOOTSTRAP_SERVERS = ["localhost:9092"]
TOPIC_LISTINGS = "airbnb_listings_raw"
TOPIC_REVIEWS = "airbnb_reviews_raw"
TOPIC_NEIGHBOURHOODS = "airbnb_neighbourhoods_raw"


def get_latest_url(city_path: str, file_name: str):
    """
    Busca en la página 'get-the-data' la URL más reciente para
    un archivo (listings.csv, reviews.csv, neighbourhoods.csv)
    de una ciudad dada (city_path).
    Devuelve (url_completa, snapshot_date).
    """
    resp = requests.get(GET_DATA_URL)
    resp.raise_for_status()
    html = resp.text

    # Ejemplo de URL:
    # https://data.insideairbnb.com/chile/rm/santiago/2024-12-27/visualisations/listings.csv
    pattern = (
        rf"https://data\.insideairbnb\.com/{city_path}/"
        rf"(\d{{4}}-\d{{2}}-\d{{2}})/visualisations/{file_name}"
    )
    match = re.search(pattern, html)
    if not match:
        raise RuntimeError(f"No se encontró URL para {file_name} en {city_path}")

    url = match.group(0)
    snapshot_date = match.group(1)
    return url, snapshot_date


def create_producer():
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def send_dataframe(df: pd.DataFrame, topic: str, producer: KafkaProducer, batch_size: int = 1000):
    """
    Envía un DataFrame fila a fila a un tópico de Kafka.
    """
    count = 0
    for _, row in df.iterrows():
        producer.send(topic, value=row.to_dict())
        count += 1
        if count % batch_size == 0:
            producer.flush()
            print(f"{count} mensajes enviados a {topic}...")
    producer.flush()
    print(f"Total enviado a {topic}: {count} filas")


def main():
    producer = create_producer()

    print("Buscando URLs más recientes para Santiago...")
    url_listings, snapshot = get_latest_url(CITY_PATH, "listings.csv")
    url_reviews, _ = get_latest_url(CITY_PATH, "reviews.csv")
    url_neigh, _ = get_latest_url(CITY_PATH, "neighbourhoods.csv")

    print("URL listings:", url_listings)
    print("URL reviews:", url_reviews)
    print("URL neighbourhoods:", url_neigh)
    print("Fecha de snapshot:", snapshot)

    print("Leyendo listings...")
    df_listings = pd.read_csv(url_listings)
    # Añadimos metadata de ciudad y fecha
    for col, val in CITY_META.items():
        df_listings[col] = val
    df_listings["snapshot_date"] = snapshot
    send_dataframe(df_listings, TOPIC_LISTINGS, producer)

    print("Leyendo reviews...")
    df_reviews = pd.read_csv(url_reviews)
    for col, val in CITY_META.items():
        df_reviews[col] = val
    df_reviews["snapshot_date"] = snapshot
    send_dataframe(df_reviews, TOPIC_REVIEWS, producer)

    print("Leyendo neighbourhoods...")
    df_neigh = pd.read_csv(url_neigh)
    for col, val in CITY_META.items():
        df_neigh[col] = val
    df_neigh["snapshot_date"] = snapshot
    send_dataframe(df_neigh, TOPIC_NEIGHBOURHOODS, producer)

    producer.close()
    print("Fin de la ingesta.")


if __name__ == "__main__":
    main()
