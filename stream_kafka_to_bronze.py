from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, IntegerType, LongType
)

# ==========================
# CONFIGURACIÓN BÁSICA
# ==========================
BOOTSTRAP_SERVERS = "localhost:9092"

TOPIC_LISTINGS = "airbnb_listings_raw"
TOPIC_REVIEWS = "airbnb_reviews_raw"
TOPIC_NEIGHBOURHOODS = "airbnb_neighbourhoods_raw"

# Rutas locales en Windows (cámbialas si quieres)
BRONZE_BASE = "C:/airbnb/bronze"
CHECKPOINT_BASE = "C:/airbnb/checkpoints"

# ==========================
# ESQUEMAS (StructType)
#  Coinciden con tus CSV + columnas extra
#  country, region, city, snapshot_date
# ==========================

schema_listings = StructType([
    StructField("id", LongType(), True),
    StructField("name", StringType(), True),
    StructField("host_id", LongType(), True),
    StructField("host_name", StringType(), True),
    StructField("neighbourhood_group", DoubleType(), True),
    StructField("neighbourhood", StringType(), True),
    StructField("latitude", DoubleType(), True),
    StructField("longitude", DoubleType(), True),
    StructField("room_type", StringType(), True),
    StructField("price", DoubleType(), True),
    StructField("minimum_nights", IntegerType(), True),
    StructField("number_of_reviews", IntegerType(), True),
    StructField("last_review", StringType(), True),
    StructField("reviews_per_month", DoubleType(), True),
    StructField("calculated_host_listings_count", IntegerType(), True),
    StructField("availability_365", IntegerType(), True),
    StructField("number_of_reviews_ltm", IntegerType(), True),
    StructField("license", StringType(), True),

    # metadata que añades en el productor
    StructField("country", StringType(), True),
    StructField("region", StringType(), True),
    StructField("city", StringType(), True),
    StructField("snapshot_date", StringType(), True),
])

schema_reviews = StructType([
    StructField("listing_id", LongType(), True),
    StructField("date", StringType(), True),

    StructField("country", StringType(), True),
    StructField("region", StringType(), True),
    StructField("city", StringType(), True),
    StructField("snapshot_date", StringType(), True),
])

schema_neighbourhoods = StructType([
    StructField("neighbourhood_group", DoubleType(), True),
    StructField("neighbourhood", StringType(), True),

    StructField("country", StringType(), True),
    StructField("region", StringType(), True),
    StructField("city", StringType(), True),
    StructField("snapshot_date", StringType(), True),
])

# ==========================
# FUNCIÓN AUXILIAR
# ==========================

def read_topic_as_stream(spark, topic, schema):
    """
    Lee un topic de Kafka y devuelve un DataFrame de streaming
    con las columnas del schema (parseando el JSON de 'value').
    """
    df_raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", BOOTSTRAP_SERVERS)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .load()
    )

    df = (
        df_raw
        .select(F.from_json(F.col("value").cast("string"), schema).alias("data"))
        .select("data.*")
    )
    return df

# ==========================
# PROGRAMA PRINCIPAL
# ==========================

if __name__ == "__main__":

    spark = (
        SparkSession.builder
        .appName("airbnb-kafka-to-bronze")
        .master("local[*]")
        .config("spark.executor.memory", "16g")
        .config("spark.driver.memory", "16g")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    # 1) Streams desde Kafka
    listings_stream = read_topic_as_stream(spark, TOPIC_LISTINGS, schema_listings)
    reviews_stream = read_topic_as_stream(spark, TOPIC_REVIEWS, schema_reviews)
    neigh_stream = read_topic_as_stream(spark, TOPIC_NEIGHBOURHOODS, schema_neighbourhoods)

    # 2) Escritura a capa BRONZE (parquet en disco local)
    query_listings = (
        listings_stream
        .writeStream
        .format("parquet")
        .option("path", f"{BRONZE_BASE}/listings")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/listings")
        .outputMode("append")
        # Trigger once: procesa todo lo que haya y termina
        .trigger(once=True)
        .start()
    )

    query_reviews = (
        reviews_stream
        .writeStream
        .format("parquet")
        .option("path", f"{BRONZE_BASE}/reviews")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/reviews")
        .outputMode("append")
        .trigger(once=True)
        .start()
    )

    query_neigh = (
        neigh_stream
        .writeStream
        .format("parquet")
        .option("path", f"{BRONZE_BASE}/neighbourhoods")
        .option("checkpointLocation", f"{CHECKPOINT_BASE}/neighbourhoods")
        .outputMode("append")
        .trigger(once=True)
        .start()
    )

    # Esperar a que terminen los tres
    query_listings.awaitTermination()
    query_reviews.awaitTermination()
    query_neigh.awaitTermination()
    
    spark.stop()