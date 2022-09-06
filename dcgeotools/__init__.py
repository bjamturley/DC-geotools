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
      addresses.loc[len(addresses)] = {"lat":address_result["Latitude"], "lon":address_result["Longitude"], "type":address_result["ResidenceType"] if "ResidenceType" in address_result else "INTERSECTION"}
    # When something breaks, test each individually
    except Exception as e:
      for addy in addys:
        try: 
          address_result = get_geodata(addy, apikey)
          addresses.loc[len(addresses)] = {"lat":address_result["Latitude"], "lon":address_result["Longitude"], "type":address_result["ResidenceType"] if "ResidenceType" in address_result else "INTERSECTION"}
        except Exception as e2:
          print(e2)
          addresses.loc[len(addresses)] = {"lat":np.nan, "lon":np.nan, "type":np.nan}
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
  # w_area = gpd.read_file(pkg_resources.resource_filename('dcgeotools', 'shapefiles/Wards_from_2022.shp'))
  w_area = gpd.read_file('shapefiles/Wards_from_2022.shp')
  w_results = gpd.sjoin(geo_points, w_area)[["geometry", "index_right"]].rename(columns={"index_right":"ward"})
  w_results["ward"] = w_results["ward"].replace([0,1,2,3,4,5,6,7],[8,6,7,2,1,5,3,4])
  return w_results

# takes dataframe[[lon,lat]]
def get_nhood(points):
  geo_points = gpd.GeoDataFrame(points, geometry = gpd.points_from_xy(points["lon"].to_list(), points["lat"].to_list()))
  ordered_dc_neighborhoods = ["SHEPHERD PARK","BARNABY WOODS","BRIGHTWOOD","CHEVY CHASE","LAMOND RIGGS","TENLEYTOWN","FOREST HILLS","BRIGHTWOOD PARK","WOODRIDGE","MICHIGAN PARK","PETWORTH","CATHEDRAL HEIGHTS","DC MEDICAL CENTER","WOODLEY PARK","MOUNT PLEASANT","COLUMBIA HEIGHTS","FORT LINCOLN/GATEWAY","BRENTWOOD","U ST/PLEASANT","ADAMS MORGAN","BLOOMINGDALE","SOUTH COLUMBIA HEIGHTS","GEORGETOWN EAST","GEORGETOWN","TRINIDAD","LOGAN CIRCLE/SHAW","UNION STATION","GWU","CHINATOWN","NATIONAL MALL","KINGMAN PARK","STADIUM ARMORY","FORT DUPONT","HILL EAST","MARSHALL HEIGHTS","SW/WATERFRONT","TWINING","NAYLOR/HILLCREST","NAVAL STATION & AIR FORCE","HISTORIC ANACOSTIA","DOUGLASS","CONGRESS HEIGHTS/SHIPLEY","BELLEVUE","WASHINGTON HIGHLANDS","16th ST HEIGHTS","KENT/PALISADES","EDGEWOOD","EASTLAND GARDENS","LINCOLN HEIGHTS","CAPITOL HILL","SAINT ELIZABETHS"]
  n_area = gpd.read_file(pkg_resources.resource_filename('dcgeotools', 'shapefiles/DC_Health_Planning_Neighborhoods.shp'))
  n_results = gpd.sjoin(geo_points, n_area)[["geometry","index_right"]].rename(columns={"index_right":"nhood"})
  n_results["nhood"] = [ordered_dc_neighborhoods[i] for i in n_results["nhood"].to_list()]
  return n_results

# takes dataframe[[lon,lat]]
def get_zipcode(points):
  geo_points = gpd.GeoDataFrame(points, geometry = gpd.points_from_xy(points["lon"].to_list(), points["lat"].to_list()))
  z_area = gpd.read_file(pkg_resources.resource_filename('dcgeotools', 'shapefiles/Zip_Codes.shp'))
  z_results = gpd.sjoin(geo_points, z_area)[["geometry", "index_right"]].rename(columns={"index_right":"zipcode"})
  zipcodes = [20012,20015,20306,20011,20040,20039,20008,20016,20017,20018,20317,20542,20528,20064,20010,20009,20422,20001,20007,20059,20002,20392,20441,20260,20060,20019,20056,20242,20036,20005,20057,20037,20440,20419,20581,20071,20223,20524,20526,20507,20043,20570,20006,20437,20572,20427,20433,20268,20426,20052,20420,20571,20536,20062,20530,20211,20573,20527,20431,20401,20506,20404,20402,20503,20439,20403,20577,20560,20548,20529,20220,20314,20004,20013,20229,20444,20535,20552,20425,20212,20500,20549,20508,20509,20501,20502,20222,20405,20505,20045,20429,20208,20566,20544,20221,20463,20226,20239,20049,20442,20217,20372,20415,20240,20451,20520,20534,20460,20510,20523,20522,20224,20230,20521,20408,20551,20418,20210,20003,20580,20245,20213,20215,20216,20565,20543,20515,20024,20540,20250,20591,20597,20201,20237,20202,20585,20594,20553,20319,20557,20559,20228,20547,20472,20407,20410,20227,20416,20026,20261,20423,20554,20412,20411,20546,20436,20254,20020,20390,20374,20590,20376,20398,20388,20373,20593,20030,20032,20340,20375]
  z_results["zipcode"] = z_results["zipcode"].apply(lambda x: zipcodes[x])
  return z_results

# takes dataframe[[lon,lat]]
def get_census(points):
  geo_points = gpd.GeoDataFrame(points, geometry = gpd.points_from_xy(points["lon"].to_list(), points["lat"].to_list()))
  c_area = gpd.read_file(pkg_resources.resource_filename('dcgeotools', 'shapefiles/Census_Block_Groups_in_2020.shp'))
  c_results = gpd.sjoin(geo_points, c_area)[["geometry", "index_right"]].rename(columns={"index_right":"census"})
  census = [202,202,202,202,300,300,300,300,400,400,501,501,501,502,502,600,600,600,600,702,702,702,703,703,704,704,802,802,803,803,803,804,804,101,102,102,102,1500,201,201,1200,1301,1301,1301,1301,1303,1303,1303,1303,1304,1304,1304,1304,1401,1401,1402,1402,1402,804,902,902,9902,903,903,9811,904,9901,9901,904,1002,9902,1002,1002,1002,1003,1003,1003,1004,1004,1004,1100,1100,1100,1100,1200,1200,1200,2101,2102,2102,2102,2102,2102,2102,2201,2201,2201,2202,2202,2202,2301,2301,1500,1500,9903,1500,1500,1600,1600,1600,1600,1702,1702,1803,1803,1803,1804,1804,1804,1901,1901,1901,1901,1902,1902,2001,2001,2002,2002,2002,2101,2101,2101,2101,3200,3200,3200,3200,3301,3301,3301,3302,3302,3400,3400,3400,3400,3400,3500,2302,2302,2302,2400,2400,2400,2400,2501,2501,2503,2503,2504,2504,2600,2600,2702,2702,2702,2702,2703,2703,2704,2704,2801,2801,2802,2802,2802,2900,2900,3000,3000,3100,3100,4300,4300,4300,4300,4401,4401,4401,4402,4402,4600,4600,4702,4702,4702,4702,4702,4703,4703,4703,4703,4704,3500,3500,3600,3600,3600,3701,3701,3702,3702,3801,3801,3802,3802,3802,3901,3901,3902,3902,4001,4001,4001,4001,4002,4002,4002,4100,4100,4100,4201,4201,4201,4202,4202,5601,5602,5602,5602,5801,5801,5802,5802,5802,5802,5802,5900,5900,6400,6400,6500,4704,4801,4801,4801,9903,4802,4802,4901,4901,4901,4902,4902,4902,5001,5001,5003,5003,5004,5004,5004,5202,5202,5202,5203,5203,5203,5302,5302,5302,5303,5303,5303,5501,5501,5502,5502,5502,5503,5503,5601,5601,7401,7401,7403,7403,7404,7404,7404,7406,7406,11001,7407,7407,11001,6500,6600,6600,6700,6700,6700,6801,6801,6802,6802,6804,6900,6900,7000,10900,10900,7000,7100,7100,7100,7201,7201,7201,7201,7202,7202,7202,7203,7203,7203,7203,7301,7301,7301,7304,7304,7304,7304,7604,7604,9301,7604,7604,7605,7605,7605,7605,9000,7703,7703,7703,7703,7407,7408,9102,7408,7409,7409,7409,7502,7502,7502,7503,9302,7503,7504,8702,7504,7601,7601,9201,7601,7601,7601,7603,7603,8702,7603,7603,7708,7709,7901,7901,7901,7709,7803,7803,7901,7903,8001,8001,7803,7803,7804,8702,8001,8002,8002,8100,7804,7804,8100,8100,8200,8200,7806,7806,8200,8200,8301,8301,7807,7807,8302,8302,8302,8402,7808,7808,7707,7707,7808,7809,7809,7707,7708,8402,8410,8701,8701,9000,9102,9400,9400,8802,8802,8802,8802,9102,9102,9400,9400,8803,8803,9201,9203,9602,9503,9503,8804,8804,8903,8903,11002,9203,9204,9204,9503,9504,9504,8903,8904,8904,9802,11001,9301,9301,9301,9505,9505,9508,8904,9000,9803,9803,9810,9810,11002,9508,9509,9602,9602,9603,9803,9804,9811,9811,9509,9509,9603,9603,9604,9604,9804,9807,9505,9507,9510,9510,9700,9700,9700,9807,9807,9508,9508,9510,9511,9601,9801,9802,10601,10601,10602,10602,10602,10602,10603,10603,10603,10700,10700,10800,10800,10800,10800,10800,10800,9904,9904,9904,9905,9905,9905,9906,9907,9907,10100,10100,10100,10201,10201,10201,10202,10202,10202,10202,10202,10202,10300,10300,10300,10400,10400,10400,10500,10500,10500,10500,10500,11100,11100,11100,980000]
  c_results["census"] = c_results["census"].apply(lambda x: census[x])
  return c_results
  