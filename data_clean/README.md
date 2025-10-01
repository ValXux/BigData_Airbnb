# Carpeta data_clean

Esta carpeta contiene enlaces simbólicos a los archivos Parquet limpios del proyecto.

## Archivos disponibles:

- `listings_clean.parquet` - 14,960 propiedades de Airbnb limpias
- `neighbourhoods_clean.parquet` - 32 barrios de Santiago
- `reviews_clean.parquet` - 452,609 reseñas sin duplicados

## Uso:

Estos archivos pueden ser leídos directamente con Spark:

```python
# Leer desde data_clean
listings = spark.read.parquet("data_clean/listings_clean.parquet")
neighbourhoods = spark.read.parquet("data_clean/neighbourhoods_clean.parquet")
reviews = spark.read.parquet("data_clean/reviews_clean.parquet")
```

Los archivos están en formato Parquet con compresión Snappy para optimizar el almacenamiento y las consultas.
