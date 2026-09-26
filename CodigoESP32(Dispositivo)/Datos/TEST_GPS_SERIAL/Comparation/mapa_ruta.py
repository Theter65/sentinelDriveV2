"""
SENTINELDRIVE - Mapa de Ruta GPS
================================
Genera mapa HTML con la ruta del NEO-6M y Dimensity 7400.

Uso:
  pip install pandas folium
  python mapa_ruta.py
"""

import pandas as pd
import folium
import os


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_csv(filepath):
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(";")
            if len(parts) != 5:
                continue
            try:
                lat = float(parts[1].replace(",", "."))
                lon = float(parts[2].replace(",", "."))
                speed = float(parts[3].replace(",", "."))
                precision = float(parts[4].replace(",", "."))
                if lat != 0.0 and lon != 0.0:
                    rows.append({
                        "lat": lat,
                        "lon": lon,
                        "speed": speed,
                        "precision": precision,
                    })
            except (ValueError, IndexError):
                continue
    return pd.DataFrame(rows)


def main():
    android_file = None
    mpu_file = None
    for f in os.listdir(SCRIPT_DIR):
        if f.endswith(".csv"):
            if f.startswith("Android"):
                android_file = os.path.join(SCRIPT_DIR, f)
            elif f.startswith("Neo6m") or f.startswith("gps_"):
                mpu_file = os.path.join(SCRIPT_DIR, f)

    if not android_file or not mpu_file:
        print("[ERROR] Faltan CSVs en la carpeta")
        return

    print(f"[Dimensity 7400] {os.path.basename(android_file)}")
    df_and = parse_csv(android_file)
    print(f"  {len(df_and)} puntos validos")

    print(f"[NEO-6M] {os.path.basename(mpu_file)}")
    df_mpu = parse_csv(mpu_file)
    print(f"  {len(df_mpu)} puntos validos")

    # Centro del mapa
    center_lat = (df_and["lat"].mean() + df_mpu["lat"].mean()) / 2
    center_lon = (df_and["lon"].mean() + df_mpu["lon"].mean()) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=15,
                   tiles="CartoDB positron")

    # Ruta Dimensity 7400 (rojo)
    coords_and = list(zip(df_and["lat"], df_and["lon"]))
    folium.PolyLine(
        coords_and, color="red", weight=3, opacity=0.7,
        tooltip="Dimensity 7400"
    ).add_to(m)

    # Ruta NEO-6M (azul)
    coords_mpu = list(zip(df_mpu["lat"], df_mpu["lon"]))
    folium.PolyLine(
        coords_mpu, color="blue", weight=3, opacity=0.7,
        tooltip="NEO-6M"
    ).add_to(m)

    # Punto inicio
    folium.Marker(
        coords_and[0], popup="Inicio Dimensity 7400",
        icon=folium.Icon(color="red", icon="play")
    ).add_to(m)

    folium.Marker(
        coords_mpu[0], popup="Inicio NEO-6M",
        icon=folium.Icon(color="blue", icon="play")
    ).add_to(m)

    # Punto fin
    folium.Marker(
        coords_and[-1], popup="Fin Dimensity 7400",
        icon=folium.Icon(color="red", icon="stop")
    ).add_to(m)

    folium.Marker(
        coords_mpu[-1], popup="Fin NEO-6M",
        icon=folium.Icon(color="blue", icon="stop")
    ).add_to(m)

    # Guardar
    output = os.path.join(SCRIPT_DIR, "mapa_ruta_gps.html")
    m.save(output)
    print(f"\n[GUARDADO] {output}")
    print("  Abre el archivo HTML en un navegador para ver el mapa")


if __name__ == "__main__":
    main()
