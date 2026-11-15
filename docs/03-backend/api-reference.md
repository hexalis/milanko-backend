# API reference — Milanko API

> Generated from `docs/03-backend/openapi.json` (OpenAPI 3.1). Do not edit by hand:
> change the code or the schemas and re-run `api/build_api_docs.py`.

**Version:** 0.1.0<br>
**Swagger UI:** [https://milanko.hexalis.org/api/v1/docs](https://milanko.hexalis.org/api/v1/docs)<br>
**ReDoc:** [https://milanko.hexalis.org/api/v1/redoc](https://milanko.hexalis.org/api/v1/redoc)<br>
**OpenAPI:** [https://milanko.hexalis.org/api/v1/openapi.json](https://milanko.hexalis.org/api/v1/openapi.json)

**Base URL:** `https://milanko.hexalis.org/api/v1` (production). Each environment uses its own subdomain:
`https://dev-milanko.hexalis.org/api/v1`, `https://qa-milanko.hexalis.org/api/v1`.

## Index

| Method | Path | What it returns |
|---|---|---|
| `GET` | `/anomalies` | Daily anomalies (empirical baseline by day of year) |
| `GET` | `/trends` | Monthly trends (Mann–Kendall + Sen, seasonal adjustment) |
| `GET` | `/correlations` | Correlation of events/month vs anomalies (lags −N…+N, FDR) |
| `GET` | `/events/{event_id}/analysis` | Anomalies of an event at a point (adaptive window) |
| `POST` | `/analysis/point` | Full analysis at a point: trends + events + correlations |
| `GET` | `/catalog/variables` | Lists the master catalog variables |
| `GET` | `/catalog/variables/{code}` | Details of a variable or layer |
| `GET` | `/catalog/events/categories` | EONET event categories (live) |
| `GET` | `/events` | Normalized EONET events |
| `GET` | `/events/stats` | Statistics for the persisted EONET catalog |
| `GET` | `/events/map` | Representative event points for the globe |
| `GET` | `/events/persisted` | EONET catalog persisted in PostgreSQL |
| `GET` | `/events/{event_id}/context` | Persisted environmental context for an EONET event |
| `GET` | `/events/{event_id}` | Details of an EONET event |
| `GET` | `/hexgrid/meta` | Metadata for the hexagonal geodesic grid (frequencies, sizes, biomes) |
| `GET` | `/hexbin/events` | EONET events aggregated into hexagonal cells |
| `POST` | `/hexbin/points` | Aggregates arbitrary points (with optional value) into hexagonal cells |
| `GET` | `/observations` | Normalized POWER series (daily or monthly, single point) |
| `GET` | `/regions` | Lists the 162 Milanko geodesic regions |
| `GET` | `/regions/rankings` | Global ranking of regions by value, anomaly, or trend |
| `GET` | `/regions/snapshot` | Value or anomaly of a variable across the 162 regions |
| `GET` | `/regions/{region_code}/observations` | Persisted series for a region |
| `GET` | `/regions/{region_code}/latest` | Last valid value of each variable in a region |
| `GET` | `/regions/{region_code}/events` | EONET events associated with a region |
| `GET` | `/regions/{region_code}/trends` | Trends for a region using persisted data |
| `GET` | `/regions/{region_code}/anomalies` | Anomalies for a region using persisted data |
| `GET` | `/health` | Service status and core size |
| `GET` | `/ping` | Protected smoke-test endpoint |
| `GET` | `/data/coverage` | Coverage of persisted data by variable |
| `GET` | `/world/config` | Configuration to render the planet in the Milanko globe |
| `GET` | `/world/meta.json` | Base world metadata |
| `GET` | `/world/base-56.bin` | Base world f=56 (31.362 cells, ~158 km per cell) |
| `GET` | `/world/base-80.bin` | Base world f=80 (64.002 cells, ~111 km per cell) |
| `GET` | `/world/fine-288/{filename}` | Fine level f=288 per region (r000.bin … r161.bin) |
| `GET` | `/world/cells` | Decoded base world cells (biome, elevation, color, water) |
| `GET` | `/world/snapshot` | Satellite image of a point (GIBS proxy, MODIS TrueColor) |

## analysis

### `GET /anomalies`

Daily anomalies (empirical baseline by day of year)

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `variables` | query | yes | `string` |  |
| `lat` | query | yes | `number` |  |
| `lon` | query | yes | `number` |  |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `community` | query | no | `string (RE, AG, SB)` |  |
| `site_elevation` | query | no | `number \| null` |  |
| `baseline_window_days` | query | no | `integer` | ±days window per day of the year |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/anomalies?variables=<variables>&lat=<lat>&lon=<lon>"
```

### `GET /trends`

Monthly trends (Mann–Kendall + Sen, seasonal adjustment)

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `variables` | query | yes | `string` |  |
| `lat` | query | yes | `number` |  |
| `lon` | query | yes | `number` |  |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `community` | query | no | `string (RE, AG, SB)` |  |
| `site_elevation` | query | no | `number \| null` |  |
| `alpha` | query | no | `number` | Significance level |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/trends?variables=<variables>&lat=<lat>&lon=<lon>"
```

### `GET /correlations`

Correlation of events/month vs anomalies (lags −N…+N, FDR)

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `variables` | query | yes | `string` |  |
| `lat` | query | yes | `number` |  |
| `lon` | query | yes | `number` |  |
| `category` | query | no | `string \| null` | Comma-separated EONET categories; empty = all events |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `community` | query | no | `string (RE, AG, SB)` |  |
| `site_elevation` | query | no | `number \| null` |  |
| `bbox` | query | no | `string \| null` | minLon,maxLat,maxLon,minLat (EONET format) |
| `status` | query | no | `string (open, closed, all)` |  |
| `limit` | query | no | `integer` | Maximum number of EONET events to consider |
| `max_lag_months` | query | no | `integer` |  |
| `method` | query | no | `string (spearman, pearson)` |  |
| `baseline_window_days` | query | no | `integer` |  |
| `mag_id` | query | no | `string \| null` |  |
| `mag_min` | query | no | `number \| null` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/correlations?variables=<variables>&lat=<lat>&lon=<lon>"
```

### `GET /events/{event_id}/analysis`

Anomalies of an event at a point (adaptive window)

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `event_id` | path | yes | `string` |  |
| `variables` | query | yes | `string` |  |
| `lat` | query | yes | `number` |  |
| `lon` | query | yes | `number` |  |
| `start` | query | no | `string` | Start of the series used for the baseline (historical) |
| `end` | query | no | `string \| null` |  |
| `community` | query | no | `string (RE, AG, SB)` |  |
| `site_elevation` | query | no | `number \| null` |  |
| `baseline_window_days` | query | no | `integer` |  |
| `max_context_days` | query | no | `integer` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/events/{event_id}/analysis?variables=<variables>&lat=<lat>&lon=<lon>"
```

### `POST /analysis/point`

Full analysis at a point: trends + events + correlations

Runs the Phase 2 pipeline in a single call: daily series, trends, per-event summaries (adaptive windows), and correlations with lags/FDR. If `events` is omitted, only trends are computed.


**JSON body** (`PointAnalysisRequest`):

| Field | Type | Required | Description |
|---|---|---|---|
| `lat` | `number` | yes |  |
| `lon` | `number` | yes |  |
| `variables` | `array[string]` | yes |  |
| `start` | `string` | no |  |
| `end` | `string \| null` | no |  |
| `community` | `string (RE, AG, SB)` | no |  |
| `site_elevation` | `number \| null` | no | Meters; required if PSC is included |
| `baseline_window_days` | `integer` | no |  |
| `max_context_days` | `integer` | no |  |
| `max_lag_months` | `integer` | no |  |
| `alpha` | `number` | no |  |
| `correlation_method` | `string (spearman, pearson)` | no |  |
| `events` | `object \| null` | no | If omitted, only trends are computed |

**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

## catalog

### `GET /catalog/variables`

Lists the master catalog variables

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `source` | query | no | `string \| null` | Filter by source: NASA POWER, EONET v3, NASA GIBS… |
| `section` | query | no | `string \| null` | Filter by section/topic of the master CSV |
| `q` | query | no | `string \| null` | Text search in code, name, and definition |
| `limit` | query | no | `integer` | Maximum number of results |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/catalog/variables"
```

### `GET /catalog/variables/{code}`

Details of a variable or layer

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `code` | path | yes | `string` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/catalog/variables/{code}"
```

### `GET /catalog/events/categories`

EONET event categories (live)


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/catalog/events/categories"
```

## events

### `GET /events`

Normalized EONET events

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `category` | query | no | `string \| null` | One or more categories separated by commas (e.g. wildfires,floods) |
| `status` | query | no | `string (open, closed, all)` | Event status |
| `start` | query | no | `string \| null` |  |
| `end` | query | no | `string \| null` |  |
| `days` | query | no | `integer \| null` | Last N days |
| `bbox` | query | no | `string \| null` | minLon,maxLat,maxLon,minLat (EONET format) |
| `limit` | query | no | `integer` |  |
| `mag_id` | query | no | `string \| null` | E.g. mag_kts |
| `mag_min` | query | no | `number \| null` | Minimum magnitude |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/events"
```

### `GET /events/stats`

Statistics for the persisted EONET catalog

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `category` | query | no | `string \| null` | Comma-separated categories |
| `status` | query | no | `string (open, closed, all)` |  |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/events/stats"
```

### `GET /events/map`

Representative event points for the globe

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `category` | query | no | `string \| null` | Comma-separated categories |
| `status` | query | no | `string (open, closed, all)` |  |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `limit` | query | no | `integer` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object<string, any>` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/events/map"
```

### `GET /events/persisted`

EONET catalog persisted in PostgreSQL

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `category` | query | no | `string \| null` | Comma-separated categories |
| `status` | query | no | `string (open, closed, all)` |  |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `limit` | query | no | `integer` |  |
| `offset` | query | no | `integer` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/events/persisted"
```

### `GET /events/{event_id}/context`

Persisted environmental context for an EONET event

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `event_id` | path | yes | `string` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object<string, any>` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/events/{event_id}/context"
```

### `GET /events/{event_id}`

Details of an EONET event

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `event_id` | path | yes | `string` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/events/{event_id}"
```

## hexbin

### `GET /hexgrid/meta`

Metadata for the hexagonal geodesic grid (frequencies, sizes, biomes)


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response |  |

```bash
curl "https://milanko.hexalis.org/api/v1/hexgrid/meta"
```

### `GET /hexbin/events`

EONET events aggregated into hexagonal cells

Groups each event by its first geometry on the Milanko geodesic grid. Returns cell code, centroid, count, events, and magnitude totals. Use `format=geojson` for a FeatureCollection (point or polygon).

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `f` | query | no | `integer` | Grid frequency (56 or 80) |
| `category` | query | no | `string \| null` | Comma-separated EONET categories; empty = all |
| `status` | query | no | `string (open, closed, all)` |  |
| `start` | query | no | `string \| null` |  |
| `end` | query | no | `string \| null` |  |
| `bbox` | query | no | `string \| null` | EONET format: minLon,maxLat,maxLon,minLat |
| `limit` | query | no | `integer` |  |
| `include_geometry` | query | no | `boolean` | Include the cell polygon |
| `format` | query | no | `string (json, geojson)` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/hexbin/events"
```

### `POST /hexbin/points`

Aggregates arbitrary points (with optional value) into hexagonal cells

Works with any research data that has coordinates: events, POWER observations, field samples… `aggregate` = count/sum/mean/max. If `geojson=true`, returns a FeatureCollection instead of the typed JSON.


**JSON body** (`HexbinPointsRequest`):

| Field | Type | Required | Description |
|---|---|---|---|
| `f` | `integer (56, 80)` | no |  |
| `points` | `array[object]` | yes |  |
| `aggregate` | `string (count, sum, mean, max)` | no |  |
| `include_geometry` | `boolean` | no |  |
| `geojson` | `boolean` | no |  |

**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

## observations

### `GET /observations`

Normalized POWER series (daily or monthly, single point)

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `variables` | query | yes | `string` | Comma-separated POWER codes (the server splits them into ≤20 per request) |
| `lat` | query | yes | `number` |  |
| `lon` | query | yes | `number` |  |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `community` | query | no | `string (RE, AG, SB)` |  |
| `site_elevation` | query | no | `number \| null` | Meters; required when querying PSC |
| `granularity` | query | no | `string (daily, monthly)` | daily uses daily POWER; monthly uses monthly POWER (start/end are trimmed to the year). |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/observations?variables=<variables>&lat=<lat>&lon=<lon>"
```

## regions

### `GET /regions`

Lists the 162 Milanko geodesic regions


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/regions"
```

### `GET /regions/rankings`

Global ranking of regions by value, anomaly, or trend

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `variable` | query | yes | `string` | Variable code, e.g. T2M |
| `metric` | query | no | `string (value, anomaly, trend)` |  |
| `order` | query | no | `string (desc, asc)` |  |
| `date` | query | no | `string \| null` |  |
| `start` | query | no | `string` |  |
| `limit` | query | no | `integer` |  |
| `source` | query | no | `string \| null` | Source; inferred from the catalog |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/regions/rankings?variable=<variable>"
```

### `GET /regions/snapshot`

Value or anomaly of a variable across the 162 regions

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `variable` | query | yes | `string` | Variable code, e.g. T2M |
| `date` | query | yes | `string` |  |
| `metric` | query | no | `string (value, anomaly)` |  |
| `source` | query | no | `string \| null` | Source; inferred from the catalog |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/regions/snapshot?variable=<variable>&date=<date>"
```

### `GET /regions/{region_code}/observations`

Persisted series for a region

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `region_code` | path | yes | `integer` |  |
| `variables` | query | no | `string \| null` | Comma-separated codes (e.g. LST_DAY,SST) |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `limit` | query | no | `integer` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/regions/{region_code}/observations"
```

### `GET /regions/{region_code}/latest`

Last valid value of each variable in a region

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `region_code` | path | yes | `integer` |  |
| `source` | query | no | `string \| null` | E.g. NASA POWER, NASA GIBS |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/regions/{region_code}/latest"
```

### `GET /regions/{region_code}/events`

EONET events associated with a region

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `region_code` | path | yes | `integer` |  |
| `category` | query | no | `string \| null` | Comma-separated categories |
| `status` | query | no | `string (open, closed, all)` |  |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `limit` | query | no | `integer` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/regions/{region_code}/events"
```

### `GET /regions/{region_code}/trends`

Trends for a region using persisted data

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `region_code` | path | yes | `integer` |  |
| `variables` | query | no | `string \| null` | Comma-separated codes |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `alpha` | query | no | `number` |  |
| `source` | query | no | `string` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object<string, any>` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/regions/{region_code}/trends"
```

### `GET /regions/{region_code}/anomalies`

Anomalies for a region using persisted data

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `region_code` | path | yes | `integer` |  |
| `variables` | query | no | `string \| null` | Comma-separated codes |
| `start` | query | no | `string` |  |
| `end` | query | no | `string \| null` |  |
| `window_days` | query | no | `integer` |  |
| `source` | query | no | `string` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object<string, any>` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/regions/{region_code}/anomalies"
```

## system

### `GET /health`

Service status and core size


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/health"
```

### `GET /ping`

Protected smoke-test endpoint

Used by the deployment pipeline; nginx requires the API key.


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object<string, boolean>` |

```bash
curl "https://milanko.hexalis.org/api/v1/ping"
```

### `GET /data/coverage`

Coverage of persisted data by variable

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `source` | query | no | `string \| null` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/data/coverage"
```

## world

### `GET /world/config`

Configuration to render the planet in the Milanko globe

Returns all the URLs and metadata the 3D globe needs: base binaries (ETDW), fine level, decoded cells, hexbinning, and GIBS snapshots.


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response |  |

```bash
curl "https://milanko.hexalis.org/api/v1/world/config"
```

### `GET /world/meta.json`

Base world metadata


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response |  |

```bash
curl "https://milanko.hexalis.org/api/v1/world/meta.json"
```

### `GET /world/base-56.bin`

Base world f=56 (31.362 cells, ~158 km per cell)


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response |  |

```bash
curl "https://milanko.hexalis.org/api/v1/world/base-56.bin"
```

### `GET /world/base-80.bin`

Base world f=80 (64.002 cells, ~111 km per cell)


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response |  |

```bash
curl "https://milanko.hexalis.org/api/v1/world/base-80.bin"
```

### `GET /world/fine-288/{filename}`

Fine level f=288 per region (r000.bin … r161.bin)

ETDW format; 162 files, one per region.

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `filename` | path | yes | `string` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response |  |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/world/fine-288/{filename}"
```

### `GET /world/cells`

Decoded base world cells (biome, elevation, color, water)

JSON view of the base binary to explore/color the planet without parsing ETDW. Lets you filter by biome, water/land, and bbox (west,south,east,north).

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `f` | query | no | `integer` | Grid frequency (56 or 80) |
| `biome` | query | no | `string \| null` | E.g. forest, desert, ice, sea, urban |
| `water` | query | no | `boolean \| null` | true=water, false=land |
| `bbox` | query | no | `string \| null` | west,south,east,north (supports antimeridian crossing) |
| `limit` | query | no | `integer` |  |
| `offset` | query | no | `integer` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response | `object` |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/world/cells"
```

### `GET /world/snapshot`

Satellite image of a point (GIBS proxy, MODIS TrueColor)

Returns a PNG of ~km×km centered on the point (MODIS/Terra TrueColor by default). Useful for the 'view from orbit' of a case file. Default date: today-3.

| Name | In | Required | Type | Description |
|---|---|---|---|---|
| `lat` | query | yes | `number` |  |
| `lon` | query | yes | `number` |  |
| `date` | query | no | `string \| null` | YYYY-MM-DD (default today-3) |
| `km` | query | no | `number` | Width of the crop in km |
| `px` | query | no | `integer` |  |


**Responses**

| Code | Description | Schema |
|---|---|---|
| `200` | Successful Response |  |
| `422` | Validation Error | `object` |

```bash
curl "https://milanko.hexalis.org/api/v1/world/snapshot?lat=<lat>&lon=<lon>"
```
