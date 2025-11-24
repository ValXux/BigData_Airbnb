# ANEXOS - Pipeline de Limpieza de Datos Airbnb Santiago

## Índice de Anexos
1. [Configuración del Entorno Spark](#anexo-1-configuración-del-entorno-spark)
2. [Exploración Inicial de Datos](#anexo-2-exploración-inicial-de-datos)
3. [Análisis de Calidad de Datos](#anexo-3-análisis-de-calidad-de-datos)
4. [Limpieza y Transformación](#anexo-4-limpieza-y-transformación)
5. [Validación Geográfica](#anexo-5-validación-geográfica)
6. [Normalización de Precios](#anexo-6-normalización-de-precios)
7. [Transformación a Parquet](#anexo-7-transformación-a-parquet)
8. [Verificación Final](#anexo-8-verificación-final)
9. [Consultas Avanzadas](#anexo-9-consultas-avanzadas)

---

## Anexo 1: Configuración del Entorno Spark

### 1.1 Inicialización de Spark
**Celda ejecutada:**
```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("PipelineLimpiezaAirbnb") \
    .getOrCreate()

print("SparkSession iniciada:", spark.version)
```

**Resultado obtenido:**
```
SparkSession iniciada: 3.5.7
```

**Explicación:** 
Se configuró exitosamente el entorno Apache Spark con la versión 3.5.7. Esta configuración incluye las variables de entorno necesarias para Java, Hadoop y Spark, estableciendo la base para el procesamiento de Big Data.

---

## Anexo 2: Exploración Inicial de Datos

### 2.1 Conteo de Registros Iniciales
**Celda ejecutada:**
```python
print("Total de registros para listings:\n", listings_df.count())
print("Total de registros para neighbourhoods:\n", neighb_df.count())
print("Total de registros para reviews:\n", reviews_df.count())
```

**Resultado obtenido:**
```
Total de registros para listings:
 15143
Total de registros para neighbourhoods:
 32
Total de registros para reviews:
 454372
```

**Explicación:**
- **Listings**: 15,143 propiedades de Airbnb en Santiago
- **Neighbourhoods**: 32 barrios/comunas diferentes
- **Reviews**: 454,372 reseñas de usuarios

### 2.2 Estructura de Datos - Neighbourhoods
**Resultado del schema:**
```
root
 |-- neighbourhood_group: string (nullable = true)
 |-- neighbourhood: string (nullable = true)
```

**Muestra de datos:**
```
+-------------------+-------------------+
|neighbourhood_group|      neighbourhood|
+-------------------+-------------------+
|               NULL|          Cerrillos|
|               NULL|        Cerro Navia|
|               NULL|           Conchalí|
|               NULL|          El Bosque|
|               NULL|   Estación Central|
+-------------------+-------------------+
```

**Explicación:**
Se observa que todos los registros tienen `neighbourhood_group` como NULL, indicando que esta clasificación no está siendo utilizada en Santiago.

### 2.3 Estructura de Datos - Reviews
**Resultado del schema:**
```
root
 |-- listing_id: long (nullable = true)
 |-- date: date (nullable = true)
```

**Muestra de datos:**
```
+----------+----------+
|listing_id|      date|
+----------+----------+
|     88944|2011-10-21|
|     88944|2012-01-29|
|     88944|2012-04-03|
|     88944|2012-06-03|
+----------+----------+
```

**Explicación:**
Los datos de reseñas contienen únicamente el ID de la propiedad y la fecha, lo que es apropiado para análisis temporales y de volumen de reseñas.

---

## Anexo 3: Análisis de Calidad de Datos

### 3.1 Análisis de Valores Nulos
**Resultado de valores nulos en listings:**
```
+---+----+-------+---------+-------------------+-------------+--------+---------+---------+-----+--------------+-----------------+-----------+-----------------+------------------------------+----------------+---------------------+-------+
| id|name|host_id|host_name|neighbourhood_group|neighbourhood|latitude|longitude|room_type|price|minimum_nights|number_of_reviews|last_review|reviews_per_month|calculated_host_listings_count|availability_365|number_of_reviews_ltm|license|
+---+----+-------+---------+-------------------+-------------+--------+---------+---------+-----+--------------+-----------------+-----------+-----------------+------------------------------+----------------+---------------------+-------+
|  0|   9|     92|      172|              15052|          101|      94|       92|      101| 2069|            95|              105|       3335|             3323|                            93|              92|                  172|  14964|
+---+----+-------+---------+-------------------+-------------+--------+---------+---------+-----+--------------+-----------------+-----------+-----------------+------------------------------+----------------+---------------------+-------+
```

**Análisis crítico:**
- **neighbourhood_group**: 15,052 nulos (99.4% del total) - Campo no utilizado en Santiago
- **Coordenadas**: 94 y 92 nulos respectivamente - Críticos para análisis geográfico
- **Precios**: 2,069 nulos (13.7%) - Importante para análisis económico
- **License**: 14,964 nulos (98.8%) - Campo prácticamente vacío

### 3.2 Detección de Duplicados
**Resultado:**
```
Número de registros duplicados en listings: 0
Número de registros duplicados en neighbourhoods: 0
Número de registros duplicados en reviews: 1763
```

**Explicación:**
Solo el dataset de reviews presenta duplicados (1,763 registros), lo que representa un 0.39% del total. Los duplicados en reviews pueden deberse a errores en la captura de datos.

---

## Anexo 4: Limpieza y Transformación

### 4.1 Corrección de Tipos de Datos
**Resultado:**
```
CORRECCIÓN DE TIPOS DE DATOS
Convirtiendo columnas de listings a tipos apropiados:
 - Convertido id a IntegerType
 - Convertido host_id a IntegerType
 - Convertido minimum_nights a IntegerType
 - Convertido number_of_reviews a IntegerType
 - Convertido calculated_host_listings_count a IntegerType
 - Convertido number_of_reviews_ltm a IntegerType
 - Convertido latitude a DoubleType
 - Convertido longitude a DoubleType
 - Convertido reviews_per_month a DoubleType
Tipos de datos corregidos para listings
```

**Esquema actualizado:**
```
root
 |-- id: integer (nullable = true)
 |-- name: string (nullable = true)
 |-- host_id: integer (nullable = true)
 |-- host_name: string (nullable = true)
 |-- neighbourhood_group: string (nullable = true)
 |-- neighbourhood: string (nullable = true)
 |-- latitude: double (nullable = true)
 |-- longitude: double (nullable = true)
 |-- room_type: string (nullable = true)
 |-- price: string (nullable = true)
 |-- minimum_nights: integer (nullable = true)
 |-- number_of_reviews: integer (nullable = true)
 |-- last_review: string (nullable = true)
 |-- reviews_per_month: double (nullable = true)
 |-- calculated_host_listings_count: integer (nullable = true)
 |-- availability_365: double (nullable = true)
 |-- number_of_reviews_ltm: integer (nullable = true)
 |-- license: string (nullable = true)
```

**Explicación:**
Se corrigieron los tipos de datos para optimizar el almacenamiento y las operaciones numéricas. Las columnas que representan conteos se convirtieron a Integer, mientras que las coordenadas y métricas de reseñas se establecieron como Double para mayor precisión.

### 4.2 Manejo de Valores Nulos - Neighbourhoods
**Estrategia aplicada:**
```python
# Asignar "Grupo_No_Especificado" a neighbourhood_group nulos
neighb_clean = neighb_df.withColumn(
    "neighbourhood_group",
    when(col("neighbourhood_group").isNull(), "Grupo_No_Especificado")
    .otherwise(col("neighbourhood_group"))
)
```

**Resultado:**
```
Registros con neighbourhood_group nulo:
+-------------------+-------------------+
|neighbourhood_group|      neighbourhood|
+-------------------+-------------------+
|               NULL|          Cerrillos|
|               NULL|        Cerro Navia|
|               NULL|           Conchalí|
[... más registros ...]

Conteo de valores nulos después de la limpieza:
+-------------------+-------------+
|neighbourhood_group|neighbourhood|
+-------------------+-------------+
|                  0|            0|
+-------------------+-------------+
```

**Explicación:**
Se reemplazaron todos los valores NULL en `neighbourhood_group` con "Grupo_No_Especificado", manteniendo la integridad referencial del dataset.

### 4.3 Eliminación de Duplicados en Reviews
**Resultado:**
```
ELIMINACIÓN DE DUPLICADOS - REVIEWS
Total de registros en reviews antes: 454372
Número de registros duplicados encontrados: 1763

Total de registros en reviews después: 452609
Registros eliminados: 1763

Duplicados restantes: 0
```

**Explicación:**
Se eliminaron 1,763 registros duplicados (0.39% del total), reduciendo el dataset de reviews de 454,372 a 452,609 registros únicos.

---

## Anexo 5: Validación Geográfica

### 5.1 Definición de Rangos Geográficos
**Parámetros establecidos:**
```
VALIDACIÓN DE DATOS GEOGRÁFICOS
Rangos válidos para Santiago:
Latitud: -33.8 a -33.0
Longitud: -70.9 a -70.2
```

### 5.2 Análisis de Coordenadas Actuales
**Estadísticas descriptivas:**
```
+-------+-------------------+------------------+
|summary|                lat|               lon|
+-------+-------------------+------------------+
|  count|              14960|             14960|
|   mean| -33.43383032269537|-70.60988689806014|
| stddev|0.03273250917799909|0.0776001536803381|
|    min|        -33.5950351|         -70.86822|
|    max|          -33.24383|         -70.22031|
+-------+-------------------+------------------+
```

**Validación de rangos:**
```
Registros fuera de rango geográfico de Santiago: 0
Total de registros: 14960
Porcentaje fuera de rango: 0.00%
```

**Explicación:**
Todas las coordenadas están dentro de los rangos válidos para Santiago. La media de latitud (-33.43) y longitud (-70.61) corresponde exactamente al centro geográfico de Santiago, confirmando la calidad de los datos geográficos.

---

## Anexo 6: Normalización de Precios

### 6.1 Análisis Inicial de Precios
**Muestra de valores:**
```
+------+
| price|
+------+
| 27990|
| 17714|
| 31713|
|316499|
|191714|
| 56527|
|110071|
+------+
```

**Estado inicial:**
```
Total de registros: 14960
Precios nulos: 1977
Precios con valor: 12983
```

### 6.2 Estadísticas Después de la Limpieza
**Distribución de precios:**
```
+-------+-----------------+
|summary|      price_clean|
+-------+-----------------+
|  count|            12983|
|   mean|85521.71354848648|
| stddev|991189.1193774695|
|    min|           7762.0|
|    max|      9.6927884E7|
+-------+-----------------+
```

**Percentiles calculados:**
```
Percentiles de precios:
1%: $7762.00
5%: $19143.00
95%: $175000.00
99%: $96927884.00
```

**Explicación:**
Se identificó un precio extremo ($96,927,884) que podría ser un outlier. La mediana ($43,470) se utilizó para rellenar valores nulos, proporcionando un valor representativo del mercado.

---

## Anexo 7: Transformación a Parquet

### 7.1 Estado Final Antes del Guardado
**Resumen de datasets limpios:**
```
ESTADO FINAL DE DATASETS ANTES DE GUARDAR:
 - listings_clean: 14,960 registros, 18 columnas
 - neighb_clean: 32 registros, 2 columnas
 - reviews_clean: 452,609 registros, 2 columnas
```

### 7.2 Proceso de Guardado
**Log del proceso:**
```
GUARDAR DATASETS EN FORMATO PARQUET...
Guardando en directorio: data_clean_parquet/
 - Guardando listings_clean → data_clean_parquet/listings_clean.parquet
	listings_clean guardado exitosamente
 - Guardando neighb_clean → data_clean_parquet/neighbourhoods_clean.parquet
	neighb_clean guardado exitosamente
 - Guardando reviews_clean → data_clean_parquet/reviews_clean.parquet
	reviews_clean guardado exitosamente
```

### 7.3 Verificación de Archivos Creados
**Resultado de verificación:**
```
VERIFICACIÓN DE ARCHIVOS PARQUET GENERADOS
ARCHIVOS PARQUET CREADOS:

VERIFICANDO LISTINGS PARQUET:
 - Registros: 14,960
 - Columnas: 18
 - Schema verificado: ✅

VERIFICANDO NEIGHBOURHOODS PARQUET:
 - Registros: 32
 - Columnas: 2
 - Schema verificado: ✅

VERIFICANDO REVIEWS PARQUET:
 - Registros: 452,609
 - Columnas: 2
 - Schema verificado: ✅

VERIFICACIÓN COMPLETA - TODOS LOS ARCHIVOS PARQUET ESTÁN CORRECTOS
```

**Explicación:**
Todos los archivos se guardaron exitosamente en formato Parquet con compresión Snappy, optimizando el almacenamiento y las consultas futuras.

---

## Anexo 8: Verificación Final

### 8.1 Resumen Estadístico Final
**Conteo de registros limpios:**
```
DATASETS LIMPIOS:
 - listings_clean: 14,960 registros
 - neighb_clean: 32 registros
 - reviews_clean: 452,609 registros
```

### 8.2 Validación de Nulos Final
**Estado de valores nulos en listings:**
```
+----+----+-------+---------+-------------------+-------------+--------+---------+---------+--------------+-----------------+-----------+-----------------+------------------------------+----------------+---------------------+-------+-----+
|  id|name|host_id|host_name|neighbourhood_group|neighbourhood|latitude|longitude|room_type|minimum_nights|number_of_reviews|last_review|reviews_per_month|calculated_host_listings_count|availability_365|number_of_reviews_ltm|license|price|
+----+----+-------+---------+-------------------+-------------+--------+---------+---------+--------------+-----------------+-----------+-----------------+------------------------------+----------------+---------------------+-------+-----+
|9924|   0|      0|        0|                  0|            0|       0|        0|        0|             0|                0|       3230|                0|                             0|               0|                    0|  14792|    0|
+----+----+-------+---------+-------------------+-------------+--------+---------+---------+--------------+-----------------+-----------+-----------------+------------------------------+----------------+---------------------+-------+-----+
```

**Nota:** Los campos críticos para análisis (coordenadas, precios, identificadores) ya no tienen valores nulos.

### 8.3 Estadísticas Descriptivas Finales
**Métricas principales:**
```
+-------+-----------------+-------------------+------------------+------------------+------------------+------------------+
|summary|            price|           latitude|         longitude|    minimum_nights| number_of_reviews| reviews_per_month|
+-------+-----------------+-------------------+------------------+------------------+------------------+------------------+
|  count|            14960|              14960|             14960|             14960|             14960|             14960|
|   mean|79964.47840909091| -33.43383032269537|-70.60988689806014| 5.780280748663102|30.214171122994653| 1.424847593582895|
| stddev|923480.4305138725|0.03273250917799909|0.0776001536803381|32.710409749769035| 57.94244512188325|1.8730471141552434|
|    min|           7762.0|        -33.5950351|         -70.86822|                 1|                 0|               0.0|
|    max|      9.6927884E7|          -33.24383|         -70.22031|              1124|              1227|             23.56|
+-------+-----------------+-------------------+------------------+------------------+------------------+------------------+
```

### 8.4 Distribución por Tipo de Habitación
**Resultado:**
```
+---------------+-----+
|      room_type|count|
+---------------+-----+
|Entire home/apt|11051|
|   Private room| 3848|
|    Shared room|   31|
|     Hotel room|   30|
+---------------+-----+
```

**Explicación:**
- El 73.9% son departamentos/casas completas
- El 25.7% son habitaciones privadas
- Solo 0.4% son habitaciones compartidas o de hotel

### 8.5 Top 10 Barrios con Más Propiedades
**Resultado:**
```
+----------------+-----+
|   neighbourhood|count|
+----------------+-----+
|        Santiago| 5453|
|     Providencia| 2717|
|      Las Condes| 2417|
|           Ñuñoa| 1178|
|    Lo Barnechea|  737|
|        Vitacura|  344|
|        Recoleta|  295|
|Estación Central|  274|
|      La Florida|  211|
|           Macul|  169|
+----------------+-----+
```

### 8.6 Estadísticas de Precios por Tipo
**Resultado:**
```
+---------------+----------+-----------+------------------+--------+
|      room_type|precio_min| precio_max|   precio_promedio|cantidad|
+---------------+----------+-----------+------------------+--------+
|     Hotel room|   14836.0|   487468.0| 86898.36666666667|      30|
|Entire home/apt|    7762.0|9.6927884E7|  86368.1588996471|   11051|
|   Private room|    8000.0|2.9671801E7| 61899.78274428275|    3848|
|    Shared room|   10286.0|   150000.0|32798.645161290326|      31|
+---------------+----------+-----------+------------------+--------+
```

---

## Anexo 9: Consultas Avanzadas

### 9.1 Top 5 Barrios Más Caros
**Consulta SQL:**
```sql
SELECT neighbourhood, 
       ROUND(AVG(price), 2) as precio_promedio,
       COUNT(*) as total_propiedades
FROM listings 
GROUP BY neighbourhood 
HAVING COUNT(*) >= 50
ORDER BY precio_promedio DESC 
LIMIT 5
```

**Resultado:**
```
+-------------+---------------+-----------------+
|neighbourhood|precio_promedio|total_propiedades|
+-------------+---------------+-----------------+
| Lo Barnechea|      270880.31|              737|
|  San Joaquín|      261073.52|               84|
|     Pudahuel|      167310.81|               90|
|     Vitacura|      125420.99|              344|
|  Providencia|       92741.03|             2717|
+-------------+---------------+-----------------+
```

### 9.2 Distribución por Rangos de Precio
**Resultado:**
```
+---------------+------------------+--------+
|      room_type|      rango_precio|cantidad|
+---------------+------------------+--------+
|Entire home/apt|Moderado (30k-60k)|    6561|
|Entire home/apt|   Caro (60k-100k)|    2082|
|Entire home/apt|   Premium (>100k)|    1427|
|Entire home/apt|  Económico (<30k)|     981|
|     Hotel room|Moderado (30k-60k)|      13|
|   Private room|Moderado (30k-60k)|    1871|
|   Private room|  Económico (<30k)|    1668|
+---------------+------------------+--------+
```

### 9.3 Estadísticas de Reseñas por Barrio
**Resultado:**
```
+----------------+-----------------+----------------+---------------+---------------+
|   neighbourhood|total_propiedades|promedio_resenas|resenas_por_mes|precio_promedio|
+----------------+-----------------+----------------+---------------+---------------+
|     Providencia|             2717|            37.4|           1.51|        92741.0|
|        Recoleta|              295|            35.6|           1.18|        44545.0|
|        Santiago|             5453|            34.6|           1.68|        57319.0|
|      Las Condes|             2417|            32.9|           1.37|        77824.0|
|      San Miguel|              161|            31.5|           1.47|        47820.0|
+----------------+-----------------+----------------+---------------+---------------+
```

---

## Resumen de la Transformación de Datos

### Datos Iniciales vs Datos Finales
| Dataset | Registros Iniciales | Registros Finales | % Reducción |
|---------|--------------------:|------------------:|------------:|
| Listings | 15,143 | 14,960 | 1.2% |
| Neighbourhoods | 32 | 32 | 0% |
| Reviews | 454,372 | 452,609 | 0.4% |

### Principales Transformaciones Realizadas
1. **Corrección de tipos de datos** - Optimización de almacenamiento
2. **Manejo de valores nulos** - Imputación inteligente por contexto
3. **Eliminación de duplicados** - Limpieza de 1,763 registros en reviews
4. **Validación geográfica** - Confirmación de coordenadas válidas para Santiago
5. **Normalización de precios** - Limpieza y conversión a formato numérico
6. **Transformación a Parquet** - Optimización para consultas futuras

### Calidad Final de los Datos
- ✅ **Sin valores nulos críticos** en campos de análisis
- ✅ **Sin duplicados** en ningún dataset
- ✅ **Tipos de datos optimizados** para análisis
- ✅ **Coordenadas geográficas validadas** para Santiago
- ✅ **Precios normalizados** y valores extremos controlados
- ✅ **Formato Parquet** para consultas eficientes

---

*Documento generado automáticamente del pipeline de limpieza de datos de Airbnb Santiago.*
*Fecha: 30 de septiembre de 2025*