import json
import folium
from folium.plugins import MousePosition
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Approved Projects Tracker",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CUSTOM CSS ---
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        min-width: 400px !important;
    }
    [data-testid="stSidebar"] p, 
    [data-testid="stSidebar"] li, 
    [data-testid="stSidebar"] div {
        font-size: 1.1rem !important;
        line-height: 1.6 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 1.1rem !important;
        font-weight: bold !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
    }
    button[title="View fullscreen"] {
        visibility: hidden !important;
        display: none !important;
    }
    div[data-testid="stImage"] img {
        pointer-events: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- 1. DATA LOADING FUNCTION WITH CACHING ---
@st.cache_data
def load_spatial_data():
    districts = gpd.GeoDataFrame()
    try:
        districts = gpd.read_file("data/malawi_districts.geojson")
        if districts.crs != "EPSG:4326":
            districts = districts.to_crs(epsg=4326)
    except Exception as e:
        st.sidebar.error(f"Districts load error: {e}")

    kbas = gpd.GeoDataFrame()
    try:
        kbas = gpd.read_file("data/key_biodiversity_areas.geojson")
        if kbas.crs != "EPSG:4326":
            kbas = kbas.to_crs(epsg=4326)
    except Exception as e:
        st.sidebar.error(f"KBAs load error: {e}")

    pa_gdf = gpd.GeoDataFrame()
    try:
        pa_gdf = gpd.read_file("data/Malawi_Protected_Areas.geojson")
        if pa_gdf.crs != "EPSG:4326":
            pa_gdf = pa_gdf.to_crs(epsg=4326)
    except Exception as e:
        st.sidebar.error(f"Protected Areas load error: {e}")

    wetlands = gpd.GeoDataFrame()
    try:
        wetlands = gpd.read_file("data/Wetlands.geojson")
        if wetlands.crs != "EPSG:4326":
            wetlands = wetlands.to_crs(epsg=4326)
    except Exception as e:
        st.sidebar.error(f"Wetlands load error: {e}")

    ecosystems = gpd.GeoDataFrame()
    try:
        ecosystems = gpd.read_file("https://github.com/giso265/ESIA-Tracker/releases/download/v1.0.0/malawi_ecosystems.geojson")
        if ecosystems.crs != "EPSG:4326":
            ecosystems = ecosystems.to_crs(epsg=4326)
    except Exception as e:
        st.sidebar.error(f"Ecosystems load error: {e}")

    projects = gpd.GeoDataFrame()
    raw_df = pd.DataFrame()
    try:
        projects = gpd.read_file("data/cleaned_projects.geojson")
        if projects.crs != "EPSG:4326":
            projects = projects.to_crs(epsg=4326)
        raw_df = pd.DataFrame(projects.drop(columns="geometry", errors="ignore"))
    except Exception as e:
        st.sidebar.error(f"Cleaned projects load error: {e}")

    return districts, kbas, pa_gdf, wetlands, ecosystems, projects, raw_df


districts_gdf, kba_gdf, pa_gdf, wetlands_gdf, ecosystems_gdf, projects_gdf, df_raw = (
    load_spatial_data()
)


# --- 2. ADVANCED SPATIAL INTERSECTIONS ---
def find_district_column(df):
    if df.empty:
        return None
    for col in df.columns:
        if (
            "district" in col.lower()
            or "name_dist" in col.lower()
            or "name_1" in col.lower()
        ):
            if col.lower() != "geometry":
                return col
    return None

dist_name_col_in_districts = find_district_column(districts_gdf) or "district_name"

if not projects_gdf.empty and not districts_gdf.empty:
    joined = gpd.sjoin(projects_gdf, districts_gdf, how="left", predicate="intersects")
    if dist_name_col_in_districts in joined.columns:
        district_aggs = (
            joined.groupby(joined.index)[dist_name_col_in_districts]
            .apply(lambda s: ", ".join(sorted(set(str(x) for x in s.dropna() if str(x).lower() not in ["nan", "none", ""]))))
            .to_dict()
        )
        projects_gdf["spatial_districts"] = projects_gdf.index.map(district_aggs)
    else:
        projects_gdf["spatial_districts"] = None

if not projects_gdf.empty and not kba_gdf.empty:
    kba_join = gpd.sjoin(projects_gdf, kba_gdf, how="left", predicate="intersects")
    kba_col = next((c for c in kba_join.columns if any(k in c.lower() for k in ["sitname", "natname", "kba", "siterecid"]) and not c.lower().startswith("index")), None)
    if kba_col:
        kba_aggs = (
            kba_join.groupby(kba_join.index)[kba_col]
            .apply(lambda s: ", ".join(sorted(set(str(x) for x in s.dropna() if str(x).lower() not in ["nan", "none", ""] and not str(x).isdigit()))))
            .to_dict()
        )
        projects_gdf["spatial_kbas"] = projects_gdf.index.map(kba_aggs)

if not projects_gdf.empty and not pa_gdf.empty:
    pa_join = gpd.sjoin(projects_gdf, pa_gdf, how="left", predicate="intersects")
    pa_col = None
    candidate_cols = [c for c in pa_join.columns if c in pa_gdf.columns]
    for priority in ["pa_name", "name", "title", "designatio", "type", "sitename"]:
        for col in candidate_cols:
            if priority in col.lower() and not col.lower().startswith("index"):
                pa_col = col
                break
        if pa_col:
            break

    if pa_col:
        pa_aggs = (
            pa_join.groupby(pa_join.index)[pa_col]
            .apply(lambda s: ", ".join(sorted(set(str(x) for x in s.dropna() if str(x).lower() not in ["nan", "none", ""] and not str(x).isdigit()))))
            .to_dict()
        )
        projects_gdf["spatial_pas"] = projects_gdf.index.map(pa_aggs)
    else:
        projects_gdf["spatial_pas"] = None

eco_name_col = None
if not ecosystems_gdf.empty:
    eco_name_col = next((c for c in ecosystems_gdf.columns if c.lower().strip() == "ecosystem"), None)
    if not eco_name_col:
        eco_name_col = next((c for c in ecosystems_gdf.columns if "eco" in c.lower() or "type" in c.lower() or "class" in c.lower()), None)

if not projects_gdf.empty and not ecosystems_gdf.empty and eco_name_col:
    eco_join = gpd.sjoin(projects_gdf, ecosystems_gdf, how="left", predicate="intersects")
    if eco_name_col in eco_join.columns:
        eco_aggs = (
            eco_join.groupby(eco_join.index)[eco_name_col]
            .apply(lambda s: ", ".join(sorted(set(str(x) for x in s.dropna() if str(x).lower() not in ["nan", "none", ""]))))
            .to_dict()
        )
        projects_gdf["spatial_ecosystems"] = projects_gdf.index.map(eco_aggs)


def find_sector_column(df):
    if df.empty:
        return None
    ignored_terms = ["geometry", "geom", "type", "index", "level", "shape"]
    for col in df.columns:
        col_clean = col.lower().replace("_", " ").strip()
        if "project sector" in col_clean or "sector" in col_clean:
            if not any(ig in col.lower() for ig in ignored_terms):
                return col
    return None

sector_col = find_sector_column(projects_gdf) or find_sector_column(df_raw)


# --- 3. LEFT SIDEBAR ---
with st.sidebar:
    logo_col1, logo_col2 = st.columns([1, 3], vertical_alignment="center")
    with logo_col1:
        try:
            st.image("data/mepa_logo.png", width=80)
        except Exception:
            st.markdown("### 🏛️")

    with logo_col2:
        st.markdown(
            "<h2 style='font-size: 1.6rem; font-weight: bold; margin-bottom: 0;'>Approved Projects Tracker</h2>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    st.markdown(
        """
        Pursuant to **Section 9** of the *Environment Management Act (No. 19 of 2017)*, the **Malawi Environment Protection Authority (MEPA)** is mandated as the principal agency to coordinate, review, and approve Environmental and Social Impact Assessments (ESIAs) and Environmental and Social Management Plans (ESMPs) across all development sectors in Malawi.
        """
    )

    st.markdown("---")

    total_projects = len(projects_gdf) if not projects_gdf.empty else len(df_raw)
    st.markdown(
        f"Since **January 2025 to date**, MEPA has reviewed and approved a total of **{total_projects} ESIA and ESMP project permits** across various national developments."
    )

    st.markdown("---")

    dist_count = 0
    if not projects_gdf.empty and "spatial_districts" in projects_gdf.columns:
        all_dists = set()
        for d_str in projects_gdf["spatial_districts"].dropna():
            for d in d_str.split(","):
                if d.strip():
                    all_dists.add(d.strip())
        dist_count = len(all_dists)

    kpi_col1, kpi_col2 = st.columns(2)
    with kpi_col1:
        st.metric("Total Permits", total_projects)
    with kpi_col2:
        st.metric("Districts Active", dist_count)

    st.markdown("---")

    active_df = projects_gdf if not projects_gdf.empty else df_raw

    if sector_col and not active_df.empty:
        sector_df = (
            active_df.groupby(sector_col)
            .size()
            .reset_index(name="Count")
        )

        fig_sector = px.pie(
            sector_df,
            values="Count",
            names=sector_col,
            title="Projects by Sector",
            hole=0,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )

        fig_sector.update_layout(
            margin=dict(l=10, r=10, t=50, b=10),
            title_font_size=18,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
                font=dict(size=12),
            ),
        )

        st.plotly_chart(fig_sector, use_container_width=True)

    if not projects_gdf.empty and "spatial_districts" in projects_gdf.columns:
        exploded_dists = (
            projects_gdf["spatial_districts"]
            .str.split(", ")
            .explode()
            .value_counts()
            .reset_index()
        )
        exploded_dists.columns = ["District", "Count"]
        dist_df = exploded_dists.head(8)

        fig_line = px.line(
            dist_df,
            x="District",
            y="Count",
            markers=True,
            title="Approved Projects per District",
            color_discrete_sequence=["#1b5e20"],
        )
        fig_line.update_traces(
            line=dict(width=3),
            marker=dict(size=8),
        )
        fig_line.update_layout(
            margin=dict(l=10, r=10, t=40, b=10),
            title_font_size=18,
            xaxis_title="District",
            yaxis_title="Projects",
            xaxis=dict(tickangle=-30, tickfont=dict(size=12)),
            yaxis=dict(tickfont=dict(size=12)),
        )
        st.plotly_chart(fig_line, use_container_width=True)


# --- 4. MAP CANVAS SETUP WITH BASEMAPS ---
m = folium.Map(
    location=[-13.2543, 34.3015],
    zoom_start=7,
    tiles=None,
    control_scale=True,
)

custom_map_styles = """
<svg height="0" width="0" style="position: absolute;">
  <defs>
    <pattern id="kba-mesh" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="8" stroke="#004d40" stroke-width="1.8" />
      <line x1="0" y1="0" x2="8" y2="0" stroke="#004d40" stroke-width="1.8" />
    </pattern>
    <pattern id="proj-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="6" stroke="#ff9800" stroke-width="2.0" />
    </pattern>
  </defs>
</svg>
<style>
.leaflet-bottom.leaflet-left {
    margin-bottom: 40px !important;
}

.leaflet-control-layers,
.leaflet-control-layers-expanded,
.leaflet-control-layers-overlays,
.leaflet-control-layers-list {
    max-height: none !important;
    height: auto !important;
    overflow: visible !important;
    overflow-y: visible !important;
    scrollbar-width: none !important;
    -ms-overflow-style: none !important;
}

.leaflet-control-layers-overlays::-webkit-scrollbar,
.leaflet-control-layers-list::-webkit-scrollbar,
.leaflet-control-layers-expanded::-webkit-scrollbar {
    display: none !important;
    width: 0px !important;
    height: 0px !important;
    background: transparent !important;
}

.leaflet-control-layers-expanded {
    background: rgba(255, 255, 255, 0.85) !important;
    backdrop-filter: blur(8px);
    border: 1px solid rgba(0, 0, 0, 0.1) !important;
    border-radius: 8px !important;
    padding: 8px 12px !important;
    font-family: Arial, sans-serif !important;
    font-size: 13px !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.08) !important;
}

.leaflet-control-layers-overlays label {
    display: flex !important;
    align-items: center !important;
    margin-bottom: 5px !important;
    cursor: pointer !important;
    font-weight: 500 !important;
}

.leaflet-control-layers-base {
    display: none !important;
}

.legend-swatch {
    display: inline-block;
    width: 18px;
    height: 14px;
    margin-left: 5px;
    margin-right: 8px;
    border-radius: 2px;
    vertical-align: middle;
}
</style>
"""
m.get_root().html.add_child(folium.Element(custom_map_styles))

MousePosition(
    position="bottomright",
    separator=" | Long: ",
    empty_string="Unavailable",
    lng_first=False,
    num_digits=5,
    prefix="Lat: ",
).add_to(m)

# BASEMAPS
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    attr="Esri World Topo Map",
    name="Esri Topographic",
    max_zoom=19,
    show=True,
).add_to(m)

folium.TileLayer(
    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr='&copy; OpenStreetMap contributors',
    name="OpenStreetMap Standard",
    subdomains="abc",
    max_zoom=19,
    show=False,
).add_to(m)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri World Imagery",
    name="Esri Satellite Imagery",
    max_zoom=18,
    show=False,
).add_to(m)


# OVERLAY FEATURE GROUPS
label_projects = '<span class="legend-swatch" style="background: repeating-linear-gradient(45deg, #ff9800 0, #ff9800 2px, transparent 0, transparent 4px); border: 1.5px solid #e65100;"></span> Approved Projects'
label_pa = '<span class="legend-swatch" style="background: rgba(46, 125, 50, 0.5); border: 1.5px solid #1b5e20;"></span> Protected Areas'
label_kba = '<span class="legend-swatch" style="background: repeating-linear-gradient(45deg, #004d40 0, #004d40 2px, transparent 0, transparent 4px); border: 1.5px solid #004d40;"></span> Key Biodiversity Areas'
label_wetlands = '<span class="legend-swatch" style="background: rgba(0, 176, 255, 0.6); border: 1.5px solid #0288d1;"></span> Wetlands'
label_districts = '<span class="legend-swatch" style="background: rgba(245, 245, 245, 0.3); border: 1.5px dashed #757575;"></span> District Boundaries'
label_ecosystems = '<span class="legend-swatch" style="background: linear-gradient(to right, #66c2a5, #fc8d62, #8da0cb, #e78ac3); border: 1px solid #558b2f;"></span> Ecosystem Types'

fg_districts = folium.FeatureGroup(name=label_districts, show=True)
fg_ecosystems = folium.FeatureGroup(name=label_ecosystems, show=False)
fg_pa = folium.FeatureGroup(name=label_pa, show=True)
fg_kba = folium.FeatureGroup(name=label_kba, show=True)
fg_wetlands = folium.FeatureGroup(name=label_wetlands, show=True)
fg_projects = folium.FeatureGroup(name=label_projects, show=True)


# BUILD OVERLAY LAYERS
if not districts_gdf.empty:
    for _, row in districts_gdf.iterrows():
        dist_name = row.get(dist_name_col_in_districts, "District")
        p_count = projects_gdf.geometry.intersects(row["geometry"]).sum() if not projects_gdf.empty else 0

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 13px; width: 170px;">
            <b style="color: #2c3e50; font-size: 14px;">{dist_name} District</b><hr style="margin: 4px 0;">
            <b>Total Approved Projects:</b> {p_count}
        </div>
        """

        folium.GeoJson(
            row["geometry"],
            style_function=lambda x: {
                "fillColor": "#000000",
                "color": "#616161",
                "weight": 1.2,
                "dashArray": "4, 4",
                "fillOpacity": 0.0,
                "pointerEvents": "none",
            },
            highlight_function=lambda x: {
                "weight": 2.5,
                "color": "#212121",
                "fillOpacity": 0.1,
            },
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(fg_districts)

if not ecosystems_gdf.empty and eco_name_col:
    unique_ecosystems = sorted(
        [
            str(x)
            for x in ecosystems_gdf[eco_name_col].dropna().unique()
            if str(x).strip() != ""
        ]
    )

    palette = px.colors.qualitative.Set2 + px.colors.qualitative.Set3
    eco_color_map = {
        eco_type: palette[i % len(palette)]
        for i, eco_type in enumerate(unique_ecosystems)
    }

    def style_eco(feature):
        val = str(feature["properties"].get(eco_name_col, "")).strip()
        color = eco_color_map.get(val, "#9e9e9e")
        return {
            "fillColor": color,
            "color": color,
            "weight": 1.2,
            "fillOpacity": 0.45,
        }

    folium.GeoJson(
        ecosystems_gdf,
        style_function=style_eco,
        popup=folium.GeoJsonPopup(
            fields=[eco_name_col], aliases=["Ecosystem Type:"]
        ),
    ).add_to(fg_ecosystems)

if not pa_gdf.empty:
    pa_name_col = next(
        (
            c
            for c in pa_gdf.columns
            if "name" in c.lower() or "pa" in c.lower() or "title" in c.lower()
        ),
        None,
    )

    for _, row in pa_gdf.iterrows():
        pa_name = (
            row.get(pa_name_col)
            if pa_name_col and pd.notnull(row.get(pa_name_col))
            else "Area"
        )

        pa_popup = f"""
        <div style="font-family: Arial, sans-serif; font-size: 13px; width: 200px;">
            <b style="color: #1b5e20; font-size: 14px;">Protected Area: {pa_name}</b>
        </div>
        """

        folium.GeoJson(
            row["geometry"],
            style_function=lambda x: {
                "fillColor": "#2e7d32",
                "color": "#1b5e20",
                "weight": 1.5,
                "fillOpacity": 0.45,
            },
            popup=folium.Popup(pa_popup, max_width=250),
        ).add_to(fg_pa)

if not kba_gdf.empty:
    for _, row in kba_gdf.iterrows():
        kba_name = (
            row.get("SitName")
            or row.get("NatName")
            or row.get("kba_name")
            or row.get("SiteName")
            or row.get("Name")
            or "Area"
        )

        kba_popup = f"""
        <div style="font-family: Arial, sans-serif; font-size: 13px; width: 200px;">
            <b style="color: #004d40; font-size: 14px;">KBA: {kba_name}</b>
        </div>
        """

        folium.GeoJson(
            row["geometry"],
            style_function=lambda x: {
                "fillColor": "url(#kba-mesh)",
                "color": "#004d40",
                "weight": 1.8,
                "fillOpacity": 0.8,
            },
            popup=folium.Popup(kba_popup, max_width=250),
        ).add_to(fg_kba)

if not wetlands_gdf.empty:
    for _, row in wetlands_gdf.iterrows():
        wet_popup = """
        <div style="font-family: Arial, sans-serif; font-size: 13px; width: 120px;">
            <b style="color: #01579b; font-size: 14px;">Wetland</b>
        </div>
        """

        folium.GeoJson(
            row["geometry"],
            style_function=lambda x: {
                "fillColor": "#00b0ff",
                "color": "#0288d1",
                "weight": 1.8,
                "fillOpacity": 0.60,
            },
            popup=folium.Popup(wet_popup, max_width=200),
        ).add_to(fg_wetlands)

if not projects_gdf.empty:
    name_col = next(
        (
            c
            for c in projects_gdf.columns
            if "project" in c.lower()
            or "name" in c.lower()
            or "title" in c.lower()
        ),
        None,
    )

    def clean_val(val):
        if pd.notnull(val) and str(val).strip().lower() not in [
            "nan",
            "none",
            "",
        ]:
            s_val = str(val).strip()
            if not s_val.isdigit():
                return s_val
        return None

    for _, row in projects_gdf.iterrows():
        proj_id = row.get("ID", "")
        proj_name = (
            row.get(name_col)
            if name_col and pd.notnull(row.get(name_col))
            else f"Approved Project #{proj_id}"
        )
        sector_val = (
            row.get(sector_col)
            if sector_col and pd.notnull(row.get(sector_col))
            else "N/A"
        )

        d_name = clean_val(row.get("spatial_districts")) or clean_val(row.get("District"))
        kba_name = clean_val(row.get("spatial_kbas"))
        pa_intersect_name = clean_val(row.get("spatial_pas"))
        eco_type = clean_val(row.get("spatial_ecosystems")) or "Unclassified"

        pa_list = [x.strip() for x in (pa_intersect_name or "").split(",") if x.strip()]
        kba_list = [x.strip() for x in (kba_name or "").split(",") if x.strip()]

        unique_kbas = [
            k for k in kba_list 
            if not any(k.lower() in p.lower() or p.lower() in k.lower() for p in pa_list)
        ]

        eco_style = "color: #757575;" if eco_type == "Unclassified" else "color: #2e7d32; font-weight: bold;"

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 13px; width: 250px;">
            <b style="color: #0d47a1; font-size: 15px;">📍 {proj_name}</b><br>
            <hr style="margin: 6px 0; border: 0; border-top: 1px solid #ccc;">
            <b>Sector:</b> {sector_val}<br>
            <b>Ecosystem:</b> <span style="{eco_style}">{eco_type}</span><br>
        """
        if d_name:
            popup_html += f"<b>District:</b> {d_name}<br>"

        if pa_list:
            pa_display = ", ".join(pa_list)
            popup_html += f"""
            <div style='margin-top: 6px; padding: 6px 8px; background-color: #e8f5e9; border-left: 3px solid #1b5e20; border-radius: 4px;'>
                <b style='color: #1b5e20; font-size: 12px;'>Designated Protected Area / KBA:</b><br>
                <span style='color: #2e7d32; font-weight: 500;'>{pa_display}</span>
            </div>
            """

        if unique_kbas:
            kba_display = ", ".join(unique_kbas)
            popup_html += f"""
            <div style='margin-top: 6px; padding: 6px 8px; background-color: #e0f2f1; border-left: 3px solid #004d40; border-radius: 4px;'>
                <b style='color: #004d40; font-size: 12px;'>Additional KBA Overlap:</b><br>
                <span style='color: #004d40; font-weight: 500;'>{kba_display}</span>
            </div>
            """

        popup_html += "</div>"

        geom_type = row.geometry.geom_type

        if geom_type in ["Point", "MultiPoint"]:
            folium.CircleMarker(
                location=[row.geometry.y, row.geometry.x],
                radius=4,
                color="#e65100",
                fill=True,
                fill_color="#ff9800",
                fill_opacity=0.9,
                popup=folium.Popup(popup_html, max_width=300),
            ).add_to(fg_projects)
        else:
            folium.GeoJson(
                row["geometry"],
                style_function=lambda x: {
                    "fillColor": "url(#proj-hatch)",
                    "color": "#e65100",
                    "weight": 2.0,
                    "fillOpacity": 0.85,
                },
                popup=folium.Popup(popup_html, max_width=300),
            ).add_to(fg_projects)


# ADD OVERLAY LAYERS TO MAP
fg_districts.add_to(m)
fg_ecosystems.add_to(m)
fg_pa.add_to(m)
fg_kba.add_to(m)
fg_wetlands.add_to(m)
fg_projects.add_to(m)

folium.LayerControl(position="bottomleft", collapsed=False).add_to(m)


# --- 5. SEARCH CONTROL INJECTED NEXT TO ZOOM BUTTONS ---
search_js = """
<script>
(function attachSearchControl() {
    var attempts = 0;
    var timer = setInterval(function() {
        attempts++;
        var mapContainer = document.querySelector('.folium-map');
        
        if (mapContainer && window[mapContainer.id]) {
            var map = window[mapContainer.id];
            
            // Target Leaflet's top-left container housing the zoom buttons (+ / -)
            var zoomContainer = mapContainer.querySelector('.leaflet-top.leaflet-left');
            
            if (zoomContainer) {
                clearInterval(timer);
                
                // Prevent duplicate elements on map rerenders
                if (document.getElementById('mepa-search-wrapper')) return;

                var searchDiv = document.createElement('div');
                searchDiv.id = 'mepa-search-wrapper';
                searchDiv.className = 'leaflet-control map-search-panel';
                searchDiv.style.cssText = 'margin-top: 10px; clear: both; display: flex; align-items: center; gap: 4px; background: white; padding: 4px 6px; border-radius: 4px; border: 2px solid rgba(0,0,0,0.2); box-shadow: 0 2px 5px rgba(0,0,0,0.2);';
                
                searchDiv.innerHTML = `
                    <input id="mapSearchInput" type="text" 
                           placeholder="Search place or Lat, Lon..." 
                           style="width: 170px; padding: 4px 6px; border: 1px solid #ccc; border-radius: 3px; font-size: 12px; outline: none;" />
                    <button id="mapSearchBtn" style="background: #1b5e20; color: white; border: none; padding: 5px 8px; border-radius: 3px; cursor: pointer; font-size: 12px; font-weight: bold;">🔍</button>
                    <button id="mapClearBtn" style="background: #c62828; color: white; border: none; padding: 5px 7px; border-radius: 3px; cursor: pointer; font-size: 12px; font-weight: bold;">❌</button>
                `;

                // Prevent map interactions from leaking through the search UI
                L.DomEvent.disableClickPropagation(searchDiv);
                L.DomEvent.disableScrollPropagation(searchDiv);

                // Append search box below the zoom controls
                zoomContainer.appendChild(searchDiv);

                var searchGroup = L.layerGroup().addTo(map);

                function runSearch() {
                    var inputVal = document.getElementById('mapSearchInput').value.trim();
                    if (!inputVal) return;

                    searchGroup.clearLayers();

                    // 1. Direct Lat, Lon Parsing
                    var coords = inputVal.split(',');
                    if (coords.length === 2) {
                        var lat = parseFloat(coords[0]);
                        var lon = parseFloat(coords[1]);
                        if (!isNaN(lat) && !isNaN(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
                            var marker = L.marker([lat, lon], {
                                icon: L.icon({
                                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
                                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                                    iconSize: [25, 41],
                                    iconAnchor: [12, 41],
                                    popupAnchor: [1, -34],
                                    shadowSize: [41, 41]
                                })
                            }).bindPopup("<b>📍 Coordinates:</b><br>" + lat + ", " + lon).openPopup();
                            
                            searchGroup.addLayer(marker);
                            map.setView([lat, lon], 14);
                            return;
                        }
                    }

                    // 2. Nominatim OpenStreetMap Search API
                    fetch('https://nominatim.openstreetmap.org/search?format=json&q=' + encodeURIComponent(inputVal))
                        .then(function(res) { return res.json(); })
                        .then(function(data) {
                            if (data && data.length > 0) {
                                var lat = parseFloat(data[0].lat);
                                var lon = parseFloat(data[0].lon);
                                var marker = L.marker([lat, lon], {
                                    icon: L.icon({
                                        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
                                        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                                        iconSize: [25, 41],
                                        iconAnchor: [12, 41],
                                        popupAnchor: [1, -34],
                                        shadowSize: [41, 41]
                                    })
                                }).bindPopup("<b>📍 " + data[0].display_name + "</b>").openPopup();

                                searchGroup.addLayer(marker);
                                map.setView([lat, lon], 12);
                            } else {
                                alert("Location not found. Try entering coordinates (e.g., -13.98, 33.78)");
                            }
                        })
                        .catch(function() {
                            alert("Error looking up location. Please check your connection.");
                        });
                }

                document.getElementById('mapSearchBtn').onclick = runSearch;
                document.getElementById('mapClearBtn').onclick = function() {
                    searchGroup.clearLayers();
                    document.getElementById('mapSearchInput').value = '';
                };
                document.getElementById('mapSearchInput').onkeypress = function(e) {
                    if (e.key === 'Enter') runSearch();
                };
            }
        }
        
        if (attempts > 100) clearInterval(timer);
    }, 100);
})();
</script>
"""

m.get_root().html.add_child(folium.Element(search_js))

# RENDER MAP CANVAS
st_folium(m, use_container_width=True, height=800)
