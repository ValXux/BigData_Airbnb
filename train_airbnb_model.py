from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from pyspark.ml.feature import (
    StringIndexer,
    OneHotEncoder,
    VectorAssembler,
    StandardScaler
)
from pyspark.ml.regression import RandomForestRegressor
from pyspark.ml.clustering import KMeans
from pyspark.ml import Pipeline
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.tuning import CrossValidator, ParamGridBuilder

# ==========================
# RUTAS LOCALES (AJUSTA SI QUIERES)
# ==========================
BRONZE_BASE = "C:/airbnb/bronze"
GOLD_BASE = "C:/airbnb/gold"
MODEL_BASE = "C:/airbnb/modelos"

CLP_PER_USD = 930.0  # mismo ratio que usabas en el notebook


def limpiar_y_enriquecer_listings(listings_df, reviews_df, neigh_df):
    """
    Aplica la misma lógica de limpieza y enriquecimiento
    que usabas en el notebook para crear listings_ml.
    """
    listings = listings_df
    reviews = reviews_df
    neigh = neigh_df

    # -----------------------
    # Conversión de precio a CLP/USD
    # -----------------------
    listings = listings.withColumn(
        "price_clp",
        F.regexp_replace(F.col("price").cast("string"), r"[\$,]", "").cast("double")
    )

    listings = listings.withColumn(
        "price_usd",
        (F.col("price_clp") / F.lit(CLP_PER_USD))
    )

    # -----------------------
    # Cast de tipos numéricos
    # -----------------------
    listings = (listings
        .withColumn("minimum_nights", F.col("minimum_nights").cast("int"))
        .withColumn("number_of_reviews", F.col("number_of_reviews").cast("int"))
        .withColumn("availability_365", F.col("availability_365").cast("int"))
        .withColumn("calculated_host_listings_count", F.col("calculated_host_listings_count").cast("int"))
        .withColumn("number_of_reviews_ltm", F.col("number_of_reviews_ltm").cast("int"))
        .withColumn("latitude", F.col("latitude").cast("double"))
        .withColumn("longitude", F.col("longitude").cast("double"))
    )

    # Fechas
    listings = listings.withColumn(
        "last_review",
        F.to_date("last_review", "yyyy-MM-dd")
    )
    reviews = reviews.withColumn(
        "date",
        F.to_date("date", "yyyy-MM-dd")
    )

    # -----------------------
    # Filtros de calidad
    # -----------------------

    # 1) precio no nulo
    listings = listings.filter(F.col("price_usd").isNotNull())

    # 2) mínimo de noches razonable
    listings = listings.filter(
        (F.col("minimum_nights") >= 1) &
        (F.col("minimum_nights") <= 365)
    )

    # 3) disponibilidad [0, 365]
    listings = listings.filter(
        (F.col("availability_365") >= 0) &
        (F.col("availability_365") <= 365)
    )

    # 4) quitar outliers de precio (1% y 99%)
    q1, q99 = listings.approxQuantile("price_usd", [0.01, 0.99], 0.01)
    listings = listings.filter(
        (F.col("price_usd") >= q1) &
        (F.col("price_usd") <= q99)
    )

    # 5) columnas obligatorias
    cols_obligatorias = [
        "price_usd", "latitude", "longitude",
        "neighbourhood", "room_type",
        "minimum_nights", "availability_365",
        "number_of_reviews"
    ]
    listings = listings.dropna(subset=cols_obligatorias)

    # 6) rellenar reviews_per_month faltantes
    listings = listings.fillna({"reviews_per_month": 0.0})

    # 7) conservar solo el último registro por id (si hubiera duplicados)
    w = Window.partitionBy("id").orderBy(F.col("last_review").desc_nulls_last())
    listings = (listings
        .withColumn("rn", F.row_number().over(w))
        .filter(F.col("rn") == 1)
        .drop("rn")
    )

    # 8) recorte geográfico (zona Santiago, ejemplo)
    listings = listings.filter(
        (F.col("latitude").between(-33.7, -33.3)) &
        (F.col("longitude").between(-70.9, -70.4))
    )

    # 9) filtrar por neighbourhoods válidos
    neigh_validos = neigh.select("neighbourhood").distinct()
    listings = listings.join(
        neigh_validos,
        on="neighbourhood",
        how="inner"
    )

    # -----------------------
    # occupancy_rate y selección final
    # -----------------------
    listings_ml = listings.withColumn(
        "occupancy_rate",
        1 - (F.col("availability_365") / F.lit(365.0))
    )

    listings_ml = listings_ml.select(
        "id",
        "neighbourhood",
        "room_type",
        "latitude", "longitude",
        "price_usd",
        "minimum_nights",
        "availability_365",
        "number_of_reviews",
        "reviews_per_month",
        "calculated_host_listings_count",
        "occupancy_rate"
    ).dropna(subset=["price_usd"])

    return listings_ml, neigh


def añadir_demand_cluster(listings_ml):
    """
    Calcula métricas por neighbourhood y aplica K-Means
    para obtener un 'demand_cluster'.
    """
    zones = (listings_ml
        .groupBy("neighbourhood")
        .agg(
            F.count("*").alias("n_listings"),
            F.mean("price_usd").alias("avg_price_usd"),
            F.mean("reviews_per_month").alias("avg_reviews_per_month"),
            F.mean("number_of_reviews").alias("avg_number_of_reviews"),
            F.mean("occupancy_rate").alias("avg_occupancy_rate")
        )
    )

    zone_feature_cols = [
        "avg_price_usd",
        "avg_reviews_per_month",
        "avg_number_of_reviews",
        "avg_occupancy_rate",
        "n_listings"
    ]

    assembler_zones = VectorAssembler(
        inputCols=zone_feature_cols,
        outputCol="features_unnorm"
    )
    zones_assembled = assembler_zones.transform(zones)

    scaler_zones = StandardScaler(
        inputCol="features_unnorm",
        outputCol="features",
        withMean=True,
        withStd=True
    )
    scaler_zones_model = scaler_zones.fit(zones_assembled)
    zones_scaled = scaler_zones_model.transform(zones_assembled)

    best_k = 4  # puedes cambiarlo si en tu notebook encontraste otro
    kmeans_final = KMeans(featuresCol="features", k=best_k, seed=42)
    kmeans_model = kmeans_final.fit(zones_scaled)

    zones_clusters = (kmeans_model.transform(zones_scaled)
        .withColumnRenamed("prediction", "demand_cluster")
    )

    zones_clusters_small = zones_clusters.select("neighbourhood", "demand_cluster")

    listings_ml = listings_ml.join(
        zones_clusters_small,
        on="neighbourhood",
        how="left"
    )

    listings_ml = listings_ml.withColumn(
        "demand_cluster",
        F.col("demand_cluster").cast("int")
    )

    return listings_ml, zones_clusters_small


def entrenar_random_forest(listings_ml):
    """
    Define el pipeline de RandomForest (con indexers + OHE),
    hace cross-validation y devuelve el modelo y métricas.
    """
    numeric_cols = [
        "minimum_nights",
        "availability_365",
        "number_of_reviews",
        "reviews_per_month",
        "calculated_host_listings_count",
        "occupancy_rate",
        "latitude",
        "longitude",
        "demand_cluster"
    ]
    cat_cols = ["room_type", "neighbourhood"]

    listings_ml_model = listings_ml.dropna(
        subset=numeric_cols + cat_cols + ["price_usd"]
    )

    # Indexers para variables categóricas
    indexers = [
        StringIndexer(
            inputCol=c,
            outputCol=c + "_idx",
            handleInvalid="keep"
        )
        for c in cat_cols
    ]

    encoder = OneHotEncoder(
        inputCols=[c + "_idx" for c in cat_cols],
        outputCols=[c + "_ohe" for c in cat_cols]
    )

    feature_cols = numeric_cols + [c + "_ohe" for c in cat_cols]
    assembler = VectorAssembler(
        inputCols=feature_cols,
        outputCol="features"
    )

    rf = RandomForestRegressor(
        featuresCol="features",
        labelCol="price_usd",
        predictionCol="prediction",
        seed=42,
        numTrees=42,
        maxDepth=6,
        maxBins=32,
        featureSubsetStrategy="sqrt"
    )

    pipeline_rf = Pipeline(stages=indexers + [encoder, assembler, rf])

    evaluator_rmse = RegressionEvaluator(
        labelCol="price_usd",
        predictionCol="prediction",
        metricName="rmse"
    )
    evaluator_mae = RegressionEvaluator(
        labelCol="price_usd",
        predictionCol="prediction",
        metricName="mae"
    )
    evaluator_r2 = RegressionEvaluator(
        labelCol="price_usd",
        predictionCol="prediction",
        metricName="r2"
    )

    # Grid pequeño para no tardar tanto
    param_grid = (ParamGridBuilder()
        .addGrid(rf.numTrees, [50])
        .addGrid(rf.maxDepth, [8])
        .build()
    )

    cv = CrossValidator(
        estimator=pipeline_rf,
        estimatorParamMaps=param_grid,
        evaluator=evaluator_rmse,
        numFolds=2,
        parallelism=1
    )

    train_df, test_df = listings_ml_model.randomSplit([0.8, 0.2], seed=42)

    cv_model = cv.fit(train_df)
    pred_rf = cv_model.transform(test_df)

    rmse_rf = evaluator_rmse.evaluate(pred_rf)
    mae_rf = evaluator_mae.evaluate(pred_rf)
    r2_rf = evaluator_r2.evaluate(pred_rf)

    metrics = {
        "rmse": rmse_rf,
        "mae": mae_rf,
        "r2": r2_rf
    }

    return cv_model, metrics


if __name__ == "__main__":

    spark = (
        SparkSession.builder
        .appName("airbnb-train-model")
        .master("local[*]")
        .config("spark.driver.memory", "16g")    # memoria para el driver
        .config("spark.executor.memory", "16g")  # memoria para el ejecutor
        .config("spark.sql.shuffle.partitions", "16")  # menos particiones en los shuffle
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    # ==========================
    # 1) LEER CAPA BRONZE (SALIDA DEL STREAMING)
    # ==========================
    listings_df = spark.read.parquet(f"{BRONZE_BASE}/listings")
    reviews_df = spark.read.parquet(f"{BRONZE_BASE}/reviews")
    neigh_df = spark.read.parquet(f"{BRONZE_BASE}/neighbourhoods")

    # ==========================
    # 2) LIMPIEZA + FEATURES
    # ==========================
    listings_ml, neigh = limpiar_y_enriquecer_listings(listings_df, reviews_df, neigh_df)
    listings_ml, zones_clusters_small = añadir_demand_cluster(listings_ml)

    # ==========================
    # 3) ENTRENAR MODELO
    # ==========================
    cv_model, metrics = entrenar_random_forest(listings_ml)
    print("Métricas RandomForest:", metrics)

    # Guardar modelo para poder reutilizarlo
    cv_model.write().overwrite().save(f"{MODEL_BASE}/rf_airbnb_cv")

    # ==========================
    # 4) GENERAR TABLA GOLD PARA POWER BI
    # ==========================
    predicciones = cv_model.transform(listings_ml)

    predicciones_select = predicciones.select(
        "id",
        "neighbourhood",
        "room_type",
        "latitude",
        "longitude",
        "price_usd",
        "demand_cluster",
        "minimum_nights",
        "availability_365",
        "number_of_reviews",
        "reviews_per_month",
        "calculated_host_listings_count",
        "occupancy_rate",
        "prediction"
    )

    (predicciones_select
        .write
        .mode("overwrite")
        .parquet(f"{GOLD_BASE}/predicciones")
    )

    print("Tabla GOLD generada en:", f"{GOLD_BASE}/predicciones")

    spark.stop()