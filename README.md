
# DC Master Address Repository (MAR) Geocoding Toolset

This is a collection of small tools developed for DC Health using the [DC Master Address Repository](https://developers.data.dc.gov/guide/overview) (MAR). While it contains some functions for using MAR, it is not a comprehensive Python API port. It was developed for overdose quantification, but is applicable for all projects using DC locations. It also provides miscellaneous geo-algorithms which do not require an API key such as a point clustering tool and DC Ward/Neighborhood location identifier using publically available shapefiles.

MAR API keys are free and can be obtained here: https://developers.data.dc.gov/Identity/Account/Register?returnUrl=/authentication/login

Features **requiring an API key**:
 - Conversion of address string to MAR compatible address string
 - Individual geocoding (address → coordinates)
 - Batch geocoding (addresses → coordinates)
 - Conversion of coordinates or address to proximate street intersection

Features **not requiring an API key**:
 - Clustering from points (coordinates → cluster centers/points per cluster)
 - Location identifier (coordinates → DC Ward/Neighborhood)

## API Reference

### address_to_MAR (address)
Takes string address removes/replaces MAR unfriendly elements.

**Parameters:**
- **address: *string***

address to be converted
 
**Returns: *string***

MAR friendly address

### geocode (address_data, apikey, *batch_size=40*)
Queries the MAR service for an address or list of addresses and returns coordinates and location type for each address in batches. Tests addresses individually when batches fail. Smaller batch sizes are recommended for address sets with high error rates in order to improve processing time.

**Parameters:**
- **addresses: *string* or *list(string)***

raw address string or set of addresses to be geocoded. these are converted to MAR automatically.

- **apikey: *string***

MAR API key

- **batch_size: *int, default=40***

number of addresses included in batch. batch geocoding is more efficient, however MAR has no error function for individual addresses and therefore the whole batch fails on error (i.e. bad address). the geocode function will default to single address testing for these batches.
 
**Returns: *DataFrame(columns=["lat", "lon", "type])***

latitude, longitude, and location type portion of the get_geodata() query

### get_census (points)
Takes a set of points and returns the DC census tract which contains each point

**Parameters:**
- **points : *DataFrame(columns=["lat", "lon"])***

points to find census tract

**Returns: *DataFrame(columns=["points", "census"])***

point objects and census labels with original index numbers

### get_clusters (points, *cluster_radius_miles=0.5*, *cluster_number_points=5*)

Groups points together based on proximity and frequency. It takes a list of coordinate points and finds all possible sets given a radius. All sets with the minimum cluster total (number of points per cluster) are kept. The program then selects the clusters with the maximum number of possible points so that all sets have no common elements. The cluster center and points per cluster is returned.

**Parameters:**
- **points : *DataFrame(columns=["lat", "lon"])***

set of coordinates to cluster

- **cluster_radius_mile : *int, default=0.5***

maximum radius between points to be clustered together

- **cluster_number_point : *int, default=5***

minimum number of points per cluster
 
**Returns: *DataFrame(columns=["clusters", "points"])***

dataframe object containing cluster centers and associated points.

### get_geodata (addresses, apikey)

Queries the MAR service for an address or list of addresses and returns the result. Requires a MAR friendly address.

**Parameters:**
- **addresses: *string* or *list(string)***

address or set of addresses to be queried

- **apikey: *string***

MAR API key
 
**Returns: *list(dict)***

results of query containing json dict "Result" portion of the MAR response for each input address

### get_intersection (loc_data, apikey)
Queries the MAR service for an address or coordinate and returns an approximate intersection/block within 200 meters.

**Parameters:**
- **loc_data: *string* or *point(lat, lon)***

address or coordinate to be converted to intersection

- **apikey: *string***

MAR API key

**Returns: *string***

intersection text

### get_nhood (points)
Takes a set of points and returns the DC neighborhood which contains each point.

**Parameters:**
- **points : *DataFrame(columns=["lat", "lon"])***

points to be neighborhooded

**Returns: *DataFrame(columns=["points", "nhood"])***

point objects and neighborhood labels with original index numbers

### get_ward (points)
Takes a set of points and returns the DC neighborhood which contains each point

**Parameters:**
- **points : *DataFrame(columns=["lat", "lon"])***

points to be warded

**Returns: *DataFrame(columns=["points", "ward"])***

point objects and ward labels with original index numbers

### get_zipcode (points)
Takes a set of points and returns the DC zip code which contains each point

**Parameters:**
- **points : *DataFrame(columns=["lat", "lon"])***

points to find zip code

**Returns: *DataFrame(columns=["points", "zipcode"])***

point objects and zip code labels with original index numbers