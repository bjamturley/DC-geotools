import math, base64, json, urllib.request, re
import geopandas as gpd
import pandas as pd
import numpy as np

import base64

def address_to_MAR(address):
  if type(address) is float or not " " in address:
    address = "nan"
  
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

# NOTE: Doesn't return Haversine distances and therefore will be inaccurate with point on a sphere (e.g. the Earth)
# Accepts dataframe [[lat, lon]]
# Returns dataframe [[cluster center (x,y), [points (x,y)]]]
def get_clusters(points, cluster_radius_miles=0.5, cluster_number_points=5):
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
      distance = math.sqrt(((int(p1_coords[0])-int(p2_coords[0]))**2)+((int(p1_coords[1])-int(p2_coords[1]))**2))
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
  w_area = gpd.read_file("../shapefiles/Wards_from_2022.shp")
  w_results = gpd.sjoin(geo_points, w_area)
  w_results["index_right"] = w_results["index_right"].replace([0,1,2,3,4,5,6,7],[8,6,7,2,1,5,3,4])
  return w_results

# takes dataframe[[lon,lat]]
def get_nhood(points, truncate=True):
  geo_points = gpd.GeoDataFrame(points, geometry = gpd.points_from_xy(points["lon"].to_list(), points["lat"].to_list()))
  ordered_dc_neighborhoods = ["Colonial Village, Shepherd Park, North Portal Estates", "Rock Creek Park", "Hawthorne, Barnaby Woods, Chevy Chase", "Takoma, Brightwood, Manor Park", "Walter Reed", "Lamont Riggs, Queens Chapel, Fort Totten, Pleasant Hill", "Friendship Heights, American University Park, Tenleytown", "Brightwood Park, Crestwood, Petworth", "North Cleveland Park, Forest Hills, Van Ness", "Fairfax Village, Naylor Gardens, Hillcrest, Summit Park", "Woodland/Fort Stanton, Garfield Heights, Knox Hill", "Saint Elizabeths", "Douglas, Shipley Terrace", "Congress Heights, Bellevue, Washington Highlands", "North Michigan Park, Michigan Park, University Heights", "Spring Valley, Palisades, Wesley Heights, Foxhall Crescent, Foxhall Village, Georgetown Reservoir", "Edgewood, Bloomingdale, Truxton Circle, Eckington", "Cathedral Heights, McLean Gardens, Glover Park", "Cleveland Park, Woodley Park, Massachusetts Avenue Heights, Woodland-Normanstone Terrace", "Woodridge, Fort Lincoln, Gateway", "Brookland, Brentwood, Langdon", "Columbia Heights, Mt. Pleasant, Pleasant Plains, Park View", "National Mall, Potomac River", "Howard University, Le Droit Park, Cardozo/Shaw", "Kalorama Heights, Adams Morgan, Lanier Heights", "Observatory Circle", "Dupont Circle, Connecticut Avenue/K Street", "Arboretum, Anacostia River", "Georgetown, Burleith/Hillandale", "Eastland Gardens, Kenilworth", "Ivy City, Arboretum, Trinidad, Carver Langston", "Shaw, Logan Circle", "Deanwood, Burrville, Grant Park, Lincoln Heights, Fairmont Heights", "Mayfair, Hillbrook, Mahaning Heights", "West End, Foggy Bottom, GWU", "Union Station, Stanton Park, Kingman Park", "Downtown, Chinatown, Penn Quarters, Mount Vernon Square, North Capitol Street", "River Terrace, Benning, Greenway, Dupont Park", "Capitol View, Marshall Heights, Benning Heights", "Capitol Hill, Lincoln Park", "Southwest Employment Area, Southwest/Waterfront, Fort McNair, Buzzard Point", "Twining, Fairlawn, Randle Highlands, Penn Branch, Fort Davis Park, Fort Dupont", "Near Southeast, Navy Yard", "Sheridan, Barry Farm, Buena Vista", "Historic Anacostia", "Joint Base Anacostia-Bolling"]
  if truncate: ordered_dc_neighborhoods = [n[:n.find(",")] for n in ordered_dc_neighborhoods]
  n_area = gpd.read_file('../shapefiles/Neighborhood_Clusters.shp')
  n_results = gpd.sjoin(geo_points, n_area)[["lat","lon","index_right"]]
  n_results["index_right"] = [ordered_dc_neighborhoods[i] for i in n_results["index_right"].to_list()]
  return n_results