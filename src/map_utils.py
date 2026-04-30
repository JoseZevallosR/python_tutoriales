import pandas as pd
import geopandas as gpd
import folium
import re
import unicodedata
import branca.colormap as cm
from folium.features import GeoJsonTooltip, GeoJsonPopup

class MapFactory:
    def __init__(self, shp_path, id_col="UBIGEO"):
        self.gdf = gpd.read_file(shp_path)
        self.id_col = id_col
        # Estandarizar ID
        if id_col == "UBIGEO":
            self.gdf[self.id_col] = self.gdf[self.id_col].astype(str).str.strip().str.zfill(6)
        if id_col == 'DEPARTAMEN':
            # Disolver por departamento
            gdf_dep = self.gdf.dissolve(by="DEPARTAMEN")

            # Resetear índice si quieres columna normal
            gdf_dep = gdf_dep.reset_index()

            self.gdf = gdf_dep

            self.gdf["DEPARTAMEN"] = self.gdf["DEPARTAMEN"].apply(clean_dep)
        
    @staticmethod
    def norm_text(s):
        if not isinstance(s, str): return ""
        s = s.strip().upper()
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^A-Z0-9 ]", "", s)
        return " ".join(s.split())

    def prepare_geo_data(self, df_data, data_id_col):
        """Une el dataframe de datos con el GeoDataFrame."""
        #df_data[data_id_col] = df_data[data_id_col].astype(str).str.strip().str.zfill(6)
        return self.gdf.merge(df_data, left_on=self.id_col, right_on=data_id_col, how="left")

    def get_gdf(self):
        return self.gdf

    def create_interactive_map(self, geo_df, layers_config, output_html, title_fields):
        """
        layers_config: lista de dicts con {column, name, colors, vmin, vmax}
        """
        # Reproyectar para Folium
        geo_html = geo_df.to_crs(epsg=4326)
        centroid = geo_html.geometry.unary_union.centroid
        fmap = folium.Map(location=[centroid.y, centroid.x], zoom_start=6, tiles="CartoDB positron")

        for layer in layers_config:
            col = layer['column']
            # Crear escala de color dinámica
            vmin = layer.get('vmin', geo_html[col].min())
            vmax = layer.get('vmax', geo_html[col].max())
            colors = layer.get('colors', ['white', 'red'])
            
            colormap = cm.LinearColormap(colors=colors, vmin=vmin, vmax=vmax, caption=layer['name'])
            
            def style_fn(feature, col=col, colormap=colormap):
                val = feature['properties'].get(col)
                return {
                    "fillColor": colormap(val) if val is not None else "grey",
                    "color": "black", "weight": 0.5, "fillOpacity": 0.7
                }

            folium.GeoJson(
                geo_html,
                name=layer['name'],
                style_function=style_fn,
                tooltip=GeoJsonTooltip(fields=title_fields),
                popup=GeoJsonPopup(fields=title_fields + [col]),
                show=layer.get('default', False)
            ).add_to(fmap)
            
            colormap.add_to(fmap)

        folium.LayerControl(collapsed=False).add_to(fmap)
        fmap.save(output_html)
        return fmap

# ============================================================
# 1) LECTURA ROBUSTA CSV (encoding + separador)
# ============================================================
def read_csv_robust(path, dtype=None):
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin1"]
    seps = [",", ";", "\t", "|"]
    last_err = None

    for enc in encodings:
        for sep in seps:
            try:
                df_ = pd.read_csv(path, encoding=enc, sep=sep, dtype=dtype, low_memory=False)
                # Heurística: si el separador está mal, suele quedar 1-2 columnas
                if df_.shape[1] <= 2:
                    continue
                print(f"[OK] CSV leído con encoding={enc}, sep='{sep}', shape={df_.shape}")
                return df_, enc, sep
            except Exception as e:
                last_err = e
    raise last_err

# ============================================================
# 2) NORMALIZACIÓN DE TEXTO PARA MATCH POR NOMBRES
# ============================================================
def fix_mojibake(s):
    """Corrige casos típicos: 'BREÃA' -> 'BREÑA'."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    s = str(s)
    if "Ã" in s or "Â" in s or "�" in s:
        try:
            return s.encode("latin1").decode("utf-8")
        except Exception:
            return s
    return s

def norm_text(s):
    """
    Normaliza para cruces por nombres:
    - mayúsculas
    - elimina paréntesis y contenido
    - unifica guiones/underscores
    - elimina tildes/diacríticos
    - quita signos
    - colapsa espacios
    """
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    s = fix_mojibake(s)
    s = str(s).strip().upper()

    s = re.sub(r"\(.*?\)", "", s)     # quita (....)
    s = s.replace("_", " ")
    s = re.sub(r"[-/]", " ", s)

    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))

    s = re.sub(r"[.,;:()]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def clean_dep(s):
    s = MapFactory.norm_text(s)
    s = re.sub(r"^[0]+", "", s)  # quitar ceros al inicio
    return s