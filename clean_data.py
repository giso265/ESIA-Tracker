import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString, MultiPoint

# 1. Load your raw CSV file
# Make sure the path matches where your project points CSV is saved
file_path = "data/project_points.csv" 

print(f"Loading {file_path}...")
df = pd.read_csv(file_path)

# Clean column names (strip trailing spaces)
df.columns = df.columns.str.strip()

# 2. Automatically locate Latitude / Longitude columns
lat_col = next(c for c in df.columns if c.lower() in ["latitude", "lat", "y"])
lon_col = next(c for c in df.columns if c.lower() in ["longitude", "lon", "x"])

# Drop rows missing coordinates
df = df.dropna(subset=[lat_col, lon_col]).copy()

# 3. Create initial Point geometries
gdf_raw = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
    crs="EPSG:4326"
)

# 4. Group by 'ID' column
cleaned_features = []

for proj_id, group in gdf_raw.groupby("ID"):
    # Grab project details from the first record in the group
    feature_data = group.iloc[0].to_dict()
    point_count = len(group)
    
    if point_count == 1:
        # Single point project (e.g., ID 3 or ID 4)
        feature_data["geometry"] = group.geometry.iloc[0]
        feature_data["geometry_type"] = "Point"
        feature_data["vertex_count"] = 1
        
    elif point_count == 2:
        # 2 points form a Line
        feature_data["geometry"] = LineString(group.geometry.tolist())
        feature_data["geometry_type"] = "LineString"
        feature_data["vertex_count"] = 2
        
    else:
        # 3 or more points (e.g., ID 1 or ID 2) -> Group into Polygon boundary
        pts = group.geometry.tolist()
        poly = Polygon(pts)
        
        # Fallback if points are unordered/collinear
        if not poly.is_valid or poly.area == 0:
            poly = MultiPoint(pts).convex_hull
            
        feature_data["geometry"] = poly
        feature_data["geometry_type"] = poly.geom_type
        feature_data["vertex_count"] = point_count

    cleaned_features.append(feature_data)

# 5. Build final GeoDataFrame and save
cleaned_gdf = gpd.GeoDataFrame(cleaned_features, crs="EPSG:4326")

output_file = "data/cleaned_projects.geojson"
cleaned_gdf.to_file(output_file, driver="GeoJSON")

print(f"✅ Success! Saved {len(cleaned_gdf)} unique projects to '{output_file}'.")