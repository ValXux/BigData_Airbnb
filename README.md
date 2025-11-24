# Proyecto Big Data Airbnb – Predicción de Precios

Este proyecto implementa un pipeline de Big Data para **predecir precios de alojamientos de Airbnb** a partir de información histórica de anuncios y calendario.

## 1. Arquitectura general

Componentes principales:

1. **Kafka**: cola de mensajes para simular la ingesta en *streaming* de los datasets de Airbnb.
2. **Apache Spark (PySpark)**:
   - Ingesta desde Kafka y generación de capas **BRONZE / SILVER / GOLD** en formato Parquet.
   - Limpieza, enriquecimiento y *feature engineering*.
   - Entrenamiento de un modelo de **Random Forest Regressor** con validación cruzada.
3. **Almacenamiento local** (simulación de data lake) en `C:/airbnb/`.
4. **Power BI**: consumo de la tabla GOLD (predicciones) y construcción del dashboard.

## 2. Requisitos de entorno

- Windows 11
- JDK 17
- Apache Spark 3.5.x
- Hadoop (librerías, `HADOOP_HOME`)
- Python 3.10 + `venv`
- Kafka 3.x
- Power BI Desktop

Variables de entorno típicas:

- `JAVA_HOME`
- `SPARK_HOME`
- `HADOOP_HOME`
- Añadir a `PATH`: `SPARK_HOME/bin`, `HADOOP_HOME/bin` y binarios de Kafka.

## 3. Estructura de carpetas

```text
Proyecto/
├─ train_airbnb_model.py          # Script de entrenamiento (PySpark)
├─ data_raw/                      # CSV originales de Airbnb
└─ C:/airbnb/
   ├─ bronze/
   │   ├─ listings/
   │   └─ calendar/
   ├─ silver/
   │   ├─ listings/
   │   └─ calendar/
   └─ gold/
       └─ predicciones/
```

## 4. Kafka: topics e ingesta

### 4.1. Arranque de Kafka

```bat
.\bin\windows\zookeeper-server-start.bat .\config\zookeeper.properties
.\bin\windows\kafka-server-start.bat .\config\server.properties
```

### 4.2. Creación de topics

```bat
.\bin\windows\kafka-topics.bat --create --topic airbnb_listings --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
.\bin\windows\kafka-topics.bat --create --topic airbnb_calendar --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
```

### 4.3. Productores en Python (simulación de streaming)

```python
from kafka import KafkaProducer
import csv, json, time

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

with open('data_raw/listings.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        producer.send('airbnb_listings', row)
        time.sleep(0.01)

producer.flush()
producer.close()
```

## 5. Spark: capa BRONZE

Lectura desde Kafka con Structured Streaming y escritura en Parquet:

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json
from pyspark.sql.types import *

spark = (
    SparkSession.builder
    .appName('airbnb-bronze-listings')
    .master('local[*]')
    .getOrCreate()
)

schema_listings = StructType([...])  # definir columnas

raw_stream = (
    spark.readStream
    .format('kafka')
    .option('kafka.bootstrap.servers', 'localhost:9092')
    .option('subscribe', 'airbnb_listings')
    .load()
)

parsed = (
    raw_stream
    .select(from_json(col('value').cast('string'), schema_listings).alias('data'))
    .select('data.*')
)

query = (
    parsed.writeStream
    .format('parquet')
    .option('path', 'C:/airbnb/bronze/listings')
    .option('checkpointLocation', 'C:/airbnb/checkpoints/listings')
    .outputMode('append')
    .start()
)

query.awaitTermination()
```

## 6. Limpieza, enriquecimiento y unión con calendario

En `train_airbnb_model.py` se realiza:

1. Lectura de BRONZE (`listings` y `calendar`).
2. Limpieza de columnas, tipos y outliers (`limpiar_y_enriquecer_listings`).
3. Cálculo de `occupancy_rate` desde `calendar`.
4. Unión listings + calendario → `listings_ml`.

## 7. Entrenamiento del modelo Random Forest

La función `entrenar_random_forest(df)`:

- Define columnas categóricas (`room_type`, `neighbourhood`) y numéricas.
- Aplica `StringIndexer` + `OneHotEncoder`.
- Crea el vector `features` con `VectorAssembler`.
- Define `RandomForestRegressor`.
- Construye un `Pipeline` de ML.
- Divide en train/test (80/20).
- Evalúa con `RegressionEvaluator` (RMSE, MAE, R²).
- Usa `CrossValidator` con una grid reducida (por ejemplo `numTrees=[50,100]`, `maxDepth=[5,10]`, `numFolds=2`, `parallelism=1`).

Al final se imprime algo como:

```text
Metricas RandomForest: {'rmse': 668.99, 'mae': 59.43, 'r2': -0.0573}
```

## 8. Generación de la capa GOLD

Se aplica el mejor modelo (`cv_model`) a todo `listings_ml` y se generan las columnas:

- Datos originales del anuncio (id, neighbourhood, room_type, coordenadas, etc.).
- Variables numéricas (minimum_nights, availability_365, number_of_reviews, ...).
- `occupancy_rate`.
- `predicted_price_usd` (salida del modelo).

Escritura en Parquet:

```python
output_path = 'C:/airbnb/gold/predicciones'
(predicciones
 .coalesce(1)
 .write.mode('overwrite')
 .parquet(output_path))
```

## 9. Consumo desde Power BI

1. Abrir Power BI Desktop.
2. Ir a **Inicio → Obtener datos → Parquet**.
3. Seleccionar el archivo dentro de `C:/airbnb/gold/predicciones/` (por ejemplo `part-00000-....snappy.parquet`).
4. Cargar los datos.
5. Asegurar tipos de datos correctos (decimales para precios).
6. Crear visualizaciones:
   - Mapa (lat/long, precio real y predicho).
   - Barras por barrio y tipo de habitación.
   - Tarjetas con promedio de precio predicho y ocupación.

## 10. Resumen del flujo completo

1. Kafka recibe datos históricos vía productores y los envía a los topics.
2. Spark Streaming lee de Kafka y genera la capa BRONZE en Parquet.
3. Un job batch (`train_airbnb_model.py`) limpia, enriquece y calcula `occupancy_rate`.
4. Se entrena un Random Forest con validación cruzada y se obtienen métricas.
5. Se generan predicciones y se guarda la tabla GOLD en `C:/airbnb/gold/predicciones`.
6. Power BI consume la capa GOLD y presenta el dashboard para el anfitrión.
