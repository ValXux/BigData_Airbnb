# airbnb_prep_model.py
from pyspark.sql import functions as F, Window
from pyspark.ml.feature import StringIndexer, OneHotEncoder, VectorAssembler
from pyspark.ml.regression import RandomForestRegressor
from pyspark.ml import Pipeline
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.clustering import KMeans
from pyspark.ml.feature import StandardScaler

CLP_PER_USD = 930.0  # mismo valor que en el notebook


def limpiar_y_enriquecer_listings(listings_df, reviews_df, neigh_df):
    
    listings = listings_df
    reviews = reviews_df
    neigh = neigh_df

    # Precio: limpiar texto → numérico
    listings = listings.withColumn(
        "price_clp",
        F.regexp_replace(F.col("price"), r"[\$,]", "").cast("double")
    )

    # Conversión a USD (normalización de moneda)
    listings = listings.withColumn(
        "price_usd",
        (F.col("price_clp") / F.lit(CLP_PER_USD))
    )

    # Otras columnas numéricas
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

    # Filtros básicos de negocio
    listings = listings.filter(F.col("price_usd").isNotNull())

    # Noches mínimas razonables (ej. 1 a 365)
    listings = listings.filter(
        (F.col("minimum_nights") >= 1) &
        (F.col("minimum_nights") <= 365)
    )

    # Disponibilidad razonable (0 a 365)
    listings = listings.filter(
        (F.col("availability_365") >= 0) &
        (F.col("availability_365") <= 365)
    )

    # Tratamiento de outliers de precio (para evitar que distorsionen ML)
    q1, q99 = listings.approxQuantile("price_usd", [0.01, 0.99], 0.01)
    listings = listings.filter(
        (F.col("price_usd") >= q1) &
        (F.col("price_usd") <= q99)
    )

    # Tratamiento de nulos (pensando en ML)
    cols_obligatorias = [
        "price_usd", "latitude", "longitude",
        "neighbourhood", "room_type",
        "minimum_nights", "availability_365",
        "number_of_reviews"
    ]
    listings = listings.dropna(subset=cols_obligatorias)
    listings = listings.fillna({"reviews_per_month": 0.0})

    # Eliminación de duplicados: quedarnos con la fila más reciente según last_review
    w = Window.partitionBy("id").orderBy(F.col("last_review").desc_nulls_last())
    listings = (listings
        .withColumn("rn", F.row_number().over(w))
        .filter(F.col("rn") == 1)
        .drop("rn")
    )

    # Validación geográfica: latitud y longitud dentro de Santiago
    listings = listings.filter(
        (F.col("latitude").between(-33.7, -33.3)) &
        (F.col("longitude").between(-70.9, -70.4))
    )

    # Coherencia con tabla de neighbourhoods
    neigh_validos = neigh.select("neighbourhood").distinct()
    listings = listings.join(
        neigh_validos,
        on="neighbourhood",
        how="inner"
    )

    # Crear tasa de ocupación aproximada a partir de availability_365
    listings_ml = listings.withColumn(
        "occupancy_rate",
        1 - (F.col("availability_365") / F.lit(365.0))
    )

    # Seleccionar columnas relevantes para ML
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

    # K-Means: segmentar zonas
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

    # Preparación de features para clustering
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

    # Entrenamiento del modelo K-Means final
    best_k = 4
    kmeans_final = KMeans(featuresCol="features", k=best_k, seed=42)
    kmeans_model = kmeans_final.fit(zones_scaled)

    zones_clusters = kmeans_model.transform(zones_scaled) \
        .withColumnRenamed("prediction", "demand_cluster")

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
    Celdas 89–104: define columnas, pipeline RF + CrossValidator,
    entrena y devuelve el modelo y las métricas.
    """
    # Columnas numéricas y categóricas
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

    # Indexers + OHE + assembler (tal como en tu notebook)
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
        seed=42
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

    from pyspark.ml.tuning import CrossValidator, ParamGridBuilder

    param_grid = (ParamGridBuilder()
        .addGrid(rf.numTrees, [50, 100])
        .addGrid(rf.maxDepth, [5, 10])
        .build()
    )

    cv = CrossValidator(
        estimator=pipeline_rf,
        estimatorParamMaps=param_grid,
        evaluator=evaluator_rmse,
        numFolds=3,
        parallelism=2
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
