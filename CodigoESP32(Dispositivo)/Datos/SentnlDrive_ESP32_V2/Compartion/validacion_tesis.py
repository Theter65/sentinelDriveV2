"""
SENTNLDRIVE - Validacion de deteccion de eventos para tesis
===========================================================
Genera graficas y tablas comparativas entre Dispositivo y Aplicacion.
Viaje Loja→Alamor = ida (datos confiables)
Viaje Alamor→Loja = vuelta (dispositivo tuvo reinicios)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILES = {
    "ida": os.path.join(SCRIPT_DIR, "APP y Dispositivo_LojaAlamor.csv.xlsx"),
    "vuelta": os.path.join(SCRIPT_DIR, "APP y Dispositivo_AlamorLoja.xlsx"),
}

plt.rcParams.update({"figure.facecolor":"white","axes.facecolor":"#f8f9fa","axes.grid":True,"grid.alpha":0.3})
C_DISP = "#2c3e50"
C_APP = "#e74c3c"
CE = {"Curva peligrosa":"#f39c12","Frenado brusco":"#e74c3c","Exceso de velocidad":"#9b59b6"}

def auto_scale_lat(val):
    """Escala automatica para latitud (-4.2 a -3.7 en Ecuador)."""
    if pd.isna(val): return val
    for s in [1e7, 1e6, 1e5, 1e4, 1e3]:
        scaled = val / s
        if -4.2 <= scaled <= -3.7:
            return scaled
    return val / 1e7  # fallback

def auto_scale_lon(val):
    """Escala automatica para longitud (-80.3 a -79.1 en Ecuador)."""
    if pd.isna(val): return val
    for s in [1e7, 1e6, 1e5, 1e4, 1e3]:
        scaled = val / s
        if -80.3 <= scaled <= -79.1:
            return scaled
    return val / 1e7  # fallback

def parse_xlsx(filepath):
    df = pd.read_excel(filepath, header=None)
    tables = {}
    for i in range(len(df)):
        v = str(df.iloc[i,0]).strip()
        if v.startswith("Tabla"):
            tables[v.replace("Tabla:","").replace("Tabla","").strip()] = i
    result = {}
    if "EVENT" in tables and "LOCATION" in tables:
        ev = df.iloc[tables["EVENT"]+3:tables["LOCATION"]].dropna(how="all").reset_index(drop=True)
        ev.columns = ["ID","BusID","Tipo","Value","Value1","Value2","Timestamp","Lat","Lon","Desc"]
        ev = ev.drop(columns=["Desc"])
        for c in ["ID","BusID","Value"]:
            ev[c] = pd.to_numeric(ev[c], errors="coerce")
        ev["Lat"] = pd.to_numeric(ev["Lat"], errors="coerce").apply(auto_scale_lat)
        ev["Lon"] = pd.to_numeric(ev["Lon"], errors="coerce").apply(auto_scale_lon)
        result["events"] = ev
    if "LOCATION" in tables:
        loc = df.iloc[tables["LOCATION"]+3:].dropna(how="all").reset_index(drop=True)
        loc = loc.iloc[:,:6]
        loc.columns = ["ID","BusID","Lat","Lon","Speed","Timestamp"]
        for c in ["ID","BusID","Speed"]:
            loc[c] = pd.to_numeric(loc[c], errors="coerce")
        loc["Lat"] = pd.to_numeric(loc["Lat"], errors="coerce").apply(auto_scale_lat)
        loc["Lon"] = pd.to_numeric(loc["Lon"], errors="coerce").apply(auto_scale_lon)
        loc["Timestamp"] = pd.to_datetime(loc["Timestamp"], errors="coerce", utc=True)
        result["locations"] = loc
    return result

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return R * 2 * np.arcsin(np.sqrt(a))

def emparejar_gps(disp, app, max_dt_s=10):
    """Empareja puntos GPS por tiempo, max_dt_s de diferencia."""
    paired = []
    j = 0
    for i in range(len(disp)):
        t_disp = disp.iloc[i]["Timestamp"]
        best = None
        best_dt = max_dt_s + 1
        while j < len(app):
            t_app = app.iloc[j]["Timestamp"]
            dt = abs((t_disp - t_app).total_seconds())
            if dt < best_dt:
                best_dt = dt
                best = j
            if t_app > t_disp:
                break
            j += 1
        if best is not None and best_dt <= max_dt_s:
            d = disp.iloc[i]; a = app.iloc[best]
            paired.append({
                "t_disp": d["Timestamp"], "t_app": a["Timestamp"],
                "lat_disp": d["Lat"], "lon_disp": d["Lon"], "spd_disp": d["Speed"],
                "lat_app": a["Lat"], "lon_app": a["Lon"], "spd_app": a["Speed"],
                "dt_s": best_dt,
            })
    return paired

def emparejar_eventos(df_ev):
    paired = []
    dev = df_ev[df_ev["BusID"]==10]
    app = df_ev[df_ev["BusID"]==11]
    for _, d in dev.iterrows():
        best = None; best_dt = 999
        for _, a in app.iterrows():
            if d["Tipo"] != a["Tipo"]: continue
            try:
                dt = abs(pd.Timestamp(d["Timestamp"]) - pd.Timestamp(a["Timestamp"]))
                if dt.total_seconds() < best_dt:
                    best_dt = dt.total_seconds(); best = a
            except: continue
        if best is not None and best_dt < 5:
            paired.append({"tipo":d["Tipo"],"ts":d["Timestamp"],"disp":d["Value"],"app":best["Value"],"diff_s":best_dt})
    return paired

def plot_ruta_gps(paired, title, filename):
    fig, ax = plt.subplots(figsize=(12, 7))
    # Plot matched route
    lat_d = [p["lat_disp"] for p in paired]
    lon_d = [p["lon_disp"] for p in paired]
    lat_a = [p["lat_app"] for p in paired]
    lon_a = [p["lon_app"] for p in paired]
    ax.plot(lon_d, lat_d, color=C_DISP, linewidth=1.8, alpha=0.8, label="Dispositivo")
    ax.plot(lon_a, lat_a, color=C_APP, linewidth=1.5, alpha=0.7, linestyle="--", label="Aplicacion")
    # Distance
    dists = [haversine(p["lat_disp"],p["lon_disp"],p["lat_app"],p["lon_app"]) for p in paired]
    txt = f"Muestras pareadas: {len(paired)}\nDistancia Haversine: media={np.mean(dists):.1f}m max={np.max(dists):.1f}m"
    ax.text(0.02, 0.98, txt, transform=ax.transAxes, fontsize=10, verticalalignment="top",
            fontfamily="monospace", bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.8))
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=200, bbox_inches="tight")
    print(f"  [OK] {filename}")
    plt.close()

def plot_mapa_ruta(paired, title, filename):
    import contextily as ctx
    fig, ax = plt.subplots(figsize=(14, 10))
    lat_d = [p["lat_disp"] for p in paired]; lon_d = [p["lon_disp"] for p in paired]
    lat_a = [p["lat_app"] for p in paired]; lon_a = [p["lon_app"] for p in paired]
    ax.plot(lon_d, lat_d, color=C_DISP, linewidth=1.5, alpha=0.85, label="Dispositivo")
    ax.plot(lon_a, lat_a, color=C_APP, linewidth=1.5, alpha=0.85, linestyle="--", label="Aplicacion")
    ax.scatter(lon_d[0], lat_d[0], color="green", s=80, zorder=5, label="Inicio")
    ax.scatter(lon_d[-1], lat_d[-1], color="red", s=80, zorder=5, label="Fin")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
    ctx.add_basemap(ax, crs="EPSG:4326", source=ctx.providers.OpenStreetMap.Mapnik)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=200, bbox_inches="tight")
    print(f"  [OK] {filename}")
    plt.close()

def plot_comparacion_gps(paired, filename):
    fig, axes = plt.subplots(3, 1, figsize=(14, 9))
    fig.suptitle("Comparacion GPS: Dispositivo vs Aplicacion", fontsize=13, fontweight="bold", y=0.99)
    t = np.arange(len(paired)) / 3600  # hours
    # Latitud
    axes[0].plot(t, [p["lat_disp"] for p in paired], color=C_DISP, linewidth=1.2, alpha=0.8, label="Dispositivo")
    axes[0].plot(t, [p["lat_app"] for p in paired], color=C_APP, linewidth=1.2, alpha=0.8, label="Aplicacion")
    axes[0].set_ylabel("Latitud"); axes[0].legend(fontsize=9); axes[0].set_title("Latitud vs Tiempo", fontsize=11)
    # Longitud
    axes[1].plot(t, [p["lon_disp"] for p in paired], color=C_DISP, linewidth=1.2, alpha=0.8, label="Dispositivo")
    axes[1].plot(t, [p["lon_app"] for p in paired], color=C_APP, linewidth=1.2, alpha=0.8, label="Aplicacion")
    axes[1].set_ylabel("Longitud"); axes[1].legend(fontsize=9); axes[1].set_title("Longitud vs Tiempo", fontsize=11)
    # Velocidad
    axes[2].plot(t, [p["spd_disp"] for p in paired], color=C_DISP, linewidth=1.2, alpha=0.8, label="Dispositivo")
    axes[2].plot(t, [p["spd_app"] for p in paired], color=C_APP, linewidth=1.2, alpha=0.8, label="Aplicacion")
    axes[2].set_xlabel("Tiempo (horas)"); axes[2].set_ylabel("Velocidad (km/h)")
    axes[2].legend(fontsize=9); axes[2].set_title("Velocidad vs Tiempo", fontsize=11)
    # Stats
    diffs_spd = [abs(p["spd_disp"]-p["spd_app"]) for p in paired if not (np.isnan(p["spd_disp"]) or np.isnan(p["spd_app"]))]
    if diffs_spd:
        txt = f"MAE={np.mean(diffs_spd):.2f} km/h  RMSE={np.sqrt(np.mean([d**2 for d in diffs_spd])):.2f}"
    else:
        txt = "MAE=—  RMSE=—"
    axes[2].text(0.98, 0.95, txt,
                 transform=axes[2].transAxes, fontsize=9, ha="right", va="top",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=200, bbox_inches="tight")
    print(f"  [OK] {filename}")
    plt.close()

def plot_velocidad_barras(paired, filename):
    fig, ax = plt.subplots(figsize=(12, 4))
    t_h = np.arange(len(paired)) / 3600
    ax.plot(t_h, [p["spd_disp"] for p in paired], color=C_DISP, linewidth=1.2, alpha=0.85, label="Dispositivo")
    ax.plot(t_h, [p["spd_app"] for p in paired], color=C_APP, linewidth=1.2, alpha=0.85, label="Aplicacion")
    ax.fill_between(t_h, [p["spd_disp"] for p in paired], [p["spd_app"] for p in paired], alpha=0.1, color="#7f8c8d")
    ax.set_xlabel("Tiempo (horas)"); ax.set_ylabel("Velocidad (km/h)")
    ax.set_title("Velocidad durante el recorrido - Dispositivo vs Aplicacion", fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    spd_d = [p["spd_disp"] for p in paired]; spd_a = [p["spd_app"] for p in paired]
    diffs = [abs(d-a) for d,a in zip(spd_d, spd_a) if not (np.isnan(d) or np.isnan(a))]
    if diffs:
        max_d = np.nanmax(spd_d) if any(np.isnan(x) for x in spd_d) else max(spd_d)
        max_a = np.nanmax(spd_a) if any(np.isnan(x) for x in spd_a) else max(spd_a)
        txt = f"MAE={np.mean(diffs):.2f} km/h | max Disp={max_d:.1f} max App={max_a:.1f}"
    else:
        txt = "MAE=—  (sin datos)"
    ax.text(0.98, 0.95, txt, transform=ax.transAxes, fontsize=9, ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=200, bbox_inches="tight")
    print(f"  [OK] {filename}")
    plt.close()

def plot_haversine(paired, filename):
    dists = [haversine(p["lat_disp"],p["lon_disp"],p["lat_app"],p["lon_app"]) for p in paired]
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.plot(np.arange(len(dists))/3600, dists, color="#9b59b6", linewidth=1.0, alpha=0.7)
    ax.axhline(y=np.mean(dists), color=C_APP, linestyle="--", linewidth=1.5, label=f"Media: {np.mean(dists):.1f}m")
    ax.set_xlabel("Tiempo (horas)"); ax.set_ylabel("Distancia (m)")
    ax.set_title("Distancia Haversine entre posiciones Dispositivo y Aplicacion", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    txt = f"Min={np.min(dists):.1f}m  Max={np.max(dists):.1f}m  Media={np.mean(dists):.1f}m  Std={np.std(dists):.1f}m"
    ax.text(0.98, 0.95, txt, transform=ax.transAxes, fontsize=9, ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=200, bbox_inches="tight")
    print(f"  [OK] {filename}")
    plt.close()

def plot_eventos(paired, title, filename):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle(title, fontsize=13, fontweight="bold", y=1.02)
    for ax, tipo in zip(axes, ["Curva peligrosa","Frenado brusco","Exceso de velocidad"]):
        p = [x for x in paired if x["tipo"]==tipo]
        if not p:
            ax.text(0.5, 0.5, f"Sin eventos\n{tipo}", ha="center", va="center", transform=ax.transAxes, fontsize=11, color="gray")
            ax.set_title(tipo, fontsize=12); continue
        x = np.arange(len(p))
        dv = [x["disp"] for x in p]; av = [x["app"] for x in p]
        ax.bar(x-0.175, dv, 0.35, label="Dispositivo", color=C_DISP, alpha=0.85)
        ax.bar(x+0.175, av, 0.35, label="Aplicacion", color=C_APP, alpha=0.85)
        diffs = [abs(d-a) for d,a in zip(dv,av)]
        ax.set_xticks(x); ax.set_xticklabels([f"#{i+1}" for i in range(len(p))], fontsize=9)
        ax.set_title(f"{tipo}\nMAE={np.mean(diffs):.3f}  RMSE={np.sqrt(np.mean([d**2 for d in diffs])):.3f}", fontsize=10)
        ax.legend(fontsize=9); ax.set_ylabel("Valor detectado")
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=200, bbox_inches="tight")
    print(f"  [OK] {filename}")
    plt.close()

def plot_evento_individual(paired, tipo, filename):
    fig, ax = plt.subplots(figsize=(6, 4.5))
    p = [x for x in paired if x["tipo"]==tipo]
    if not p:
        ax.text(0.5, 0.5, f"Sin eventos: {tipo}", ha="center", va="center", transform=ax.transAxes, fontsize=12, color="gray")
        ax.set_title(tipo, fontsize=12)
    else:
        x = np.arange(len(p))
        dv = [x["disp"] for x in p]; av = [x["app"] for x in p]
        maxv = max(max(dv), max(av)) * 1.2
        ax.bar(x-0.175, dv, 0.35, label="Dispositivo", color=C_DISP, alpha=0.85)
        ax.bar(x+0.175, av, 0.35, label="Aplicacion", color=C_APP, alpha=0.85)
        ax.set_xticks(x)
        labels = []
        for ev in p:
            ts = str(ev["ts"])
            labels.append(ts[11:19] if len(ts)>=19 else ts)
        ax.set_xticklabels(labels, fontsize=9, rotation=20)
        ax.set_ylim(0, maxv)
        diffs = [abs(d-a) for d,a in zip(dv,av)]
        ax.text(0.5, 0.92, f"MAE={np.mean(diffs):.3f}", ha="center", va="center",
                transform=ax.transAxes, fontsize=10,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
        ax.legend(fontsize=9); ax.set_ylabel("Valor detectado")
    ax.set_title(tipo, fontsize=12, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=200, bbox_inches="tight")
    print(f"  [OK] {filename}")
    plt.close()

def gen_tabla_eventos(paired, viaje):
    lines = [r"\begin{table}[H]", r"\centering",
             r"\caption{Comparación de eventos detectados: " + viaje + r"}",
             r"\label{tab:eventos_" + viaje.lower().replace(" ","_") + r"}",
             r"\begin{tabular}{|c|c|c|c|c|c|}", r"\hline",
             r"Tipo & Hora & Dispositivo & Aplicación & Diferencia & \% Error \\", r"\hline"]
    for p in paired:
        diff = abs(p["disp"] - p["app"])
        pct = diff / max(abs(p["app"]), 0.001) * 100
        lines.append(f"  {p['tipo']} & {p['ts']} & {p['disp']:.3f} & {p['app']:.3f} & {diff:.3f} & {pct:.1f}\\% \\\\ \\hline")
    lines += [r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)

def gen_tabla_gps(paired):
    diffs_lat = [abs(p["lat_disp"]-p["lat_app"]) for p in paired]
    diffs_lon = [abs(p["lon_disp"]-p["lon_app"]) for p in paired]
    diffs_spd = [abs(p["spd_disp"]-p["spd_app"]) for p in paired if not (np.isnan(p["spd_disp"]) or np.isnan(p["spd_app"]))]
    if not diffs_spd: diffs_spd = [0.0]
    dists = [haversine(p["lat_disp"],p["lon_disp"],p["lat_app"],p["lon_app"]) for p in paired]
    def rmse(arr): return np.sqrt(np.mean([d**2 for d in arr]))
    lines = [r"\begin{table}[H]", r"\centering",
             r"\caption{Métricas de error GPS: Dispositivo vs Aplicación}",
             r"\label{tab:metricas_gps}",
             r"\begin{tabular}{|c|c|c|c|}",
             r"\hline", r"Métrica & MAE & RMSE & Máximo \\", r"\hline",
             f"  Latitud (°) & {np.mean(diffs_lat):.6f} & {rmse(diffs_lat):.6f} & {np.max(diffs_lat):.6f} \\\\ \\hline",
             f"  Longitud (°) & {np.mean(diffs_lon):.6f} & {rmse(diffs_lon):.6f} & {np.max(diffs_lon):.6f} \\\\ \\hline",
             f"  Velocidad (km/h) & {np.mean(diffs_spd):.2f} & {rmse(diffs_spd):.2f} & {np.max(diffs_spd):.2f} \\\\ \\hline",
             f"  Distancia (m) & {np.mean(dists):.1f} & {rmse(dists):.1f} & {np.max(dists):.1f} \\\\ \\hline",
             r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)

def gen_resumen(paired_ev, df_ev, viaje):
    lines = [f"=== VIAJE {viaje.upper()} ===",
             f"Total eventos detectados: {len(df_ev)} (Dispositivo: {len(df_ev[df_ev['BusID']==10])}, Aplicacion: {len(df_ev[df_ev['BusID']==11])})"]
    for t, c in df_ev["Tipo"].value_counts().items(): lines.append(f"  {t}: {c}")
    if paired_ev:
        lines.append(""); lines.append("Eventos pareados (ambos dispositivos):")
        for p in paired_ev:
            diff = abs(p["disp"]-p["app"])
            pct = diff/max(abs(p["app"]),0.001)*100
            lines.append(f"  {p['tipo']}: Dispositivo={p['disp']:.3f} Aplicacion={p['app']:.3f} | diff={diff:.3f} ({pct:.1f}%)")
        diffs = [abs(p["disp"]-p["app"]) for p in paired_ev]
        lines.append(f"  MAE general: {np.mean(diffs):.3f}")
        lines.append(f"  RMSE general: {np.sqrt(np.mean([d**2 for d in diffs])):.3f}")
    return "\n".join(lines)

def main():
    print("="*60)
    print("  SENTNLDRIVE - Validacion de eventos y GPS para tesis")
    print("="*60)
    
    for name, filepath in FILES.items():
        if not os.path.exists(filepath): continue
        print(f"\n>>> Viaje {name}")
        data = parse_xlsx(filepath)
        df_ev = data.get("events"); df_loc = data.get("locations")
        if df_ev is not None and len(df_ev) > 0:
            pe = emparejar_eventos(df_ev)
            print(f"  Eventos: {len(df_ev)} | Pareados: {len(pe)}")
            if pe:
                route_label = {"ida": "Loja--Alamor", "vuelta": "Alamor--Loja"}.get(name, name)
                plot_eventos(pe, f"Eventos {route_label} - Dispositivo vs Aplicacion", f"eventos_{name}.png")
                for tipo in ["Exceso de velocidad", "Frenado brusco", "Curva peligrosa"]:
                    if any(x["tipo"]==tipo for x in pe):
                        safe_name = tipo.lower().replace(" ","_")
                        plot_evento_individual(pe, tipo, f"evento_{safe_name}_{name}.png")
                with open(os.path.join(SCRIPT_DIR, f"tabla_eventos_{name}.tex"), "w") as f:
                    f.write(gen_tabla_eventos(pe, route_label))
            with open(os.path.join(SCRIPT_DIR, f"resumen_{name}.txt"), "w") as f:
                f.write(gen_resumen(pe, df_ev, name))
            print(f"  [OK] tablas de eventos")
        
        # GPS solo para ida (Loja→Alamor) - datos confiables
        if name == "ida" and df_loc is not None:
            disp = df_loc[df_loc["BusID"] == 10].sort_values("Timestamp").reset_index(drop=True)
            app = df_loc[df_loc["BusID"] == 11].sort_values("Timestamp").reset_index(drop=True)
            print(f"  GPS: Dispositivo={len(disp)} Aplicacion={len(app)}")
            paired = emparejar_gps(disp, app, max_dt_s=10)
            print(f"  Puntos GPS pareados: {len(paired)}")
            if len(paired) > 0:
                plot_ruta_gps(paired, "Ruta Loja→Alamor - Dispositivo vs Aplicacion", "ruta_gps_ida.png")
                plot_mapa_ruta(paired, "Mapa de ruta Loja→Alamor", "mapa_ruta_ida.png")
                plot_comparacion_gps(paired, "comparacion_gps_ida.png")
                plot_velocidad_barras(paired, "velocidad_comparacion_ida.png")
                plot_haversine(paired, "haversine_ida.png")
                with open(os.path.join(SCRIPT_DIR, "tabla_metricas_gps.tex"), "w") as f:
                    f.write(gen_tabla_gps(paired))
                print(f"  [OK] graficas GPS generadas")
    
    print(f"\n{'='*60}\n  COMPLETADO\n  {SCRIPT_DIR}\n{'='*60}")

if __name__ == "__main__":
    main()
