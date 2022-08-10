import math, base64, json, urllib.request, re
import geopandas as gpd
import pandas as pd
import numpy as np

import base64, pkg_resources

def address_to_MAR(address):
  if type(address) is float or not " " in address:
    address = "!{} Not an address".format(address)
  
  address = address.lower()
  if " apt" in address:
    address = address[:address.find(" apt")]
  if "#" in address:
    address = address[:address.find("#")]

  url_string = address.lower().replace(", washington dc", "").replace(".", "").replace(",", "").replace("?", "").replace("blk", "").replace("block", "").replace("of", "").replace("-", " ").replace("/", " and ").replace("\\", " and ")
  return re.sub(" +", " ", url_string)

# takes [MAR address]
def get_geodata(addresses, apikey):
  if type(addresses) == str: addresses = [addresses]
  addresses = base64.b64encode("||".join(addresses).encode("ascii")).decode("utf-8")
  request = "https://datagate.dc.gov/mar/open/api/v2.0/locationbatch/{}?address_separator=%7C%7C&chunkSequnce_separator=%3A&parallel=false&apikey={}".format(addresses,apikey)
  with urllib.request.urlopen(request) as url:
      data = json.loads(url.read().decode())
      address_list = []
      for d in data["Results"]:
        first_key = next(iter(d["Result"]))
        second_key = next(iter(d["Result"][first_key][0]))
        address_data = d["Result"][first_key][0][second_key]["properties"]
      return address_data

# takes [address] or (address)
def geocode(address_data, apikey, batch_size=40):
  if type(address_data) == str: address_data = [address_data]

  addresses = pd.DataFrame(columns=["lat", "lon", "type"])
  for i in range(len(address_data)):
    print("{}/{}".format(i*batch_size+1,len(address_data)))
    # Try addresses in batch
    if address_data[i*batch_size:(i*batch_size)+batch_size] == []: break
    addys = [address_to_MAR(addy) for addy in address_data[i*batch_size:(i*batch_size)+batch_size]]
    if addys == []: break
    try: 
      address_result = get_geodata(addys, apikey)
      addresses = address.append({"lat":address_result["Latitude"], "lon":address_result["Longitude"], "type":address_result["ResidenceType"] if "ResidenceType" in address_result else "INTERSECTION"}, ignore_index=True)
    # When something breaks, test each individually
    except Exception as e:
      for addy in addys:
        try: 
          address_result = get_geodata(addy, apikey)
          addresses = addresses.append({"lat":address_result["Latitude"], "lon":address_result["Longitude"], "type":address_result["ResidenceType"] if "ResidenceType" in address_result else "INTERSECTION"}, ignore_index=True)
        except Exception as e2:
          print(e2)
          addresses = addresses.append({"lat":np.nan, "lon":np.nan, "type":np.nan}, ignore_index=True)
          print("Address failure:", addy)
  return addresses

# takes (lat,lon) or (address)
def get_intersection(loc_data, apikey):
  def street_from_address(address):
    address = address[address.find(" ")+1:]
    return address
    
  square = None
  # Address to SSL - Square
  if type(loc_data) == str:
    try: 
      square = get_geodata(loc_data, apikey)["SSL"]
      if square == None: return np.nan
      square = square[:square.find(" ")]
    except Exception as e:
      print(e)
      return np.nan
  else:
    # Coords to SSL - Square
    request = "https://datagate.dc.gov/mar/open/api/v2.0/locations/{},{}/200m?apikey={}".format(loc_data[1],loc_data[0],apikey)
    try:
      with urllib.request.urlopen(request) as url:
          data = json.loads(url.read().decode())
          if data["Result"] == []: return np.nan
          square = None
          for r in range(len(data["Result"])):
            square = data["Result"][r]["address"]["properties"]["SSL"]
            if not square == None:
              break
          if square == None: return np.nan
          square = square[:square.find(" ")]
    except Exception as e:
      print(e)
      return np.nan
  # Square to intersection
  request = "https://datagate.dc.gov/mar/open/api/v2.0/ssls?square={}&apikey={}".format(square,apikey)
  try:
    with urllib.request.urlopen(request) as url:
        data = json.loads(url.read().decode())
        # Make sure the two streets are different
        for i in range(len(data["Result"]["ssls"])):
          if data["Result"]["ssls"][i]["FullAddress"] == None: continue
          street1 = street_from_address(data["Result"]["ssls"][i]["FullAddress"])
          street2 = street_from_address(data["Result"]["ssls"][0]["FullAddress"])
          if not street1 == street2:
            return street1 + " AND " + street2
  except Exception as e:
    print(e)
    return np.nan
  return np.nan

# Accepts dataframe [[lat, lon]]
# Returns dataframe [[cluster center (x,y), [points (x,y)]]]
def get_clusters(points, cluster_radius_miles=0.5, cluster_number_points=5):
  def haversine(origin, destination):
    origin_lat = math.radians(float(origin[0]))
    origin_lon = math.radians(float(origin[1]))
    destination_lat = math.radians(float(destination[0]))
    destination_lon = math.radians(float(destination[1]))
    lat_delta = destination_lat - origin_lat
    lon_delta = destination_lon - origin_lon

    # Radius of earth in meters
    r = 6378127

    # Haversine formula
    a = math.sin(lat_delta / 2) ** 2 + math.cos(origin_lat) * math.cos(destination_lat) * math.sin(lon_delta / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    meters_traveled = c * r

    # return in miles
    return meters_traveled * 0.000621371

  clusters = pd.DataFrame(columns=["center", "points"])
  if len(points) < cluster_number_points: return clusters
  point_pairs = []
  # Get distances - BOTTLENECK
  for i1, p1 in enumerate(points.to_dict("records")):
    if np.isnan(p1["lat"]): continue
    for i2, p2 in enumerate(points.to_dict("records")):
      if np.isnan(p2["lat"]): continue
      # Combination already tested or self
      if i1 >= i2: continue
      p1_coords = [p1["lat"], p1["lon"]]
      p2_coords = [p2["lat"], p2["lon"]]
      distance = haversine(p1_coords,p2_coords)
      # Out of range
      if np.isnan(distance) or distance > cluster_radius_miles: continue
      point_pairs.append([i1, i2, p1_coords, p2_coords, distance])
  
  # Check there are enough total points for clustering
  if len(point_pairs) < cluster_number_points: return clusters

  distances = pd.DataFrame(point_pairs, columns=["p1", "p2", "p1_coords", "p2_coords", "distance"])

  # Remove rows where point is not included in enough pairs to be part of a cluster
  potential_clusters = []
  for p in np.unique(distances[["p1", "p2"]].values):
    point_set = np.unique(distances[(distances["p1"] == p) | (distances["p2"] == p)][["p1", "p2"]].values)
    if len(point_set) >= cluster_number_points:
      potential_clusters.append(point_set)
  
  if len(potential_clusters) < 1: return clusters

  # Remove lists with items in other lists, favoring size
  def get_largest_sets(lst):
    # Test if lists have common items sequentially
    for x, c in enumerate(lst):
      common_items = [bool(set(c) & set(i)) if not x == x2 else False for x2, i in enumerate(lst)]
      # If so, start test over after removing
      if any(common_items):
        new_list = [item for x, item in enumerate(lst) if not common_items[x]]
        return get_largest_sets(new_list)
    return lst

  potential_clusters.sort(key = lambda x:-len(x))
  potential_clusters = [c.tolist() for c in potential_clusters]
  potential_clusters = get_largest_sets(potential_clusters)

  # Accepts [points (x,y)]
  def centeroid(arr):
    length = arr.shape[0]
    sum_x = np.sum(arr[:, 0])
    sum_y = np.sum(arr[:, 1])
    return sum_x/length, sum_y/length

  for cluster in potential_clusters:
    cluster_set = np.array([[points.iat[point, 0], points.iat[point, 1]] for point in cluster])
    clusters = clusters.append({"center":centeroid(cluster_set), "points":cluster_set}, ignore_index=True)

  return clusters

# takes dataframe[[lon,lat]]
def get_ward(points):
  geo_points = gpd.GeoDataFrame(points, geometry = gpd.points_from_xy(points["lon"].to_list(), points["lat"].to_list()))
  w_area = gpd.read_file(pkg_resources.resource_filename('dcgeotools', 'shapefiles/Wards_from_2022.shp'))
  w_results = gpd.sjoin(geo_points, w_area)[["geometry", "index_right"]].rename(columns={"index_right":"ward"})
  w_results["ward"] = w_results["ward"].replace([0,1,2,3,4,5,6,7],[8,6,7,2,1,5,3,4])
  w_results = w_results
  return w_results

# takes dataframe[[lon,lat]]
def get_nhood(points):
  geo_points = gpd.GeoDataFrame(points, geometry = gpd.points_from_xy(points["lon"].to_list(), points["lat"].to_list()))
  ordered_dc_neighborhoods = ["SHEPHERD PARK","BARNABY WOODS","BRIGHTWOOD","CHEVY CHASE","LAMOND RIGGS","TENLEYTOWN","FOREST HILLS","BRIGHTWOOD PARK","WOODRIDGE","MICHIGAN PARK","PETWORTH","CATHEDRAL HEIGHTS","DC MEDICAL CENTER","WOODLEY PARK","MOUNT PLEASANT","COLUMBIA HEIGHTS","FORT LINCOLN/GATEWAY","BRENTWOOD","U ST/PLEASANT","ADAMS MORGAN","BLOOMINGDALE","SOUTH COLUMBIA HEIGHTS","GEORGETOWN EAST","GEORGETOWN","TRINIDAD","LOGAN CIRCLE/SHAW","UNION STATION","GWU","CHINATOWN","NATIONAL MALL","KINGMAN PARK","STADIUM ARMORY","FORT DUPONT","HILL EAST","MARSHALL HEIGHTS","SW/WATERFRONT","TWINING","NAYLOR/HILLCREST","NAVAL STATION & AIR FORCE","HISTORIC ANACOSTIA","DOUGLASS","CONGRESS HEIGHTS/SHIPLEY","BELLEVUE","WASHINGTON HIGHLANDS","16th ST HEIGHTS","KENT/PALISADES","EDGEWOOD","EASTLAND GARDENS","LINCOLN HEIGHTS","CAPITOL HILL","SAINT ELIZABETHS"]
  n_area = gpd.read_file(pkg_resources.resource_filename('dcgeotools', 'shapefiles/DC_Health_Planning_Neighborhoods.shp'))
  n_results = gpd.sjoin(geo_points, n_area)[["geometry","index_right"]].rename(columns={"index_right":"nhood"})
  n_results["nhood"] = [ordered_dc_neighborhoods[i] for i in n_results["nhood"].to_list()]
  return n_results