"""
SENTINELDRIVE - Comparacion GPS: NEO-6M vs Dimensity 7400
=========================================================
3 graficas: Coordenadas, Velocidad, Precision
Dimensity 7400 = referencia.

Uso:
  pip install pandas matplotlib
  python comparar_gps.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


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
                h, m, s = parts[0].split(":")
                t_sec = int(h) * 3600 + int(m) * 60 + int(s)
                rows.append({
                    "t_sec": t_sec,
                    "lat": float(parts[1].replace(",", ".")),
                    "lon": float(parts[2].replace(",", ".")),
                    "speed": float(parts[3].replace(",", ".")),
                    "precision": float(parts[4].replace(",", ".")),
                })
            except (ValueError, IndexError):
                continue

    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df

    expanded = []
    counters = {}
    for _, row in df.iterrows():
        ts = row["t_sec"]
        if ts not in counters:
            counters[ts] = 0
        counters[ts] += 1
        frac = (counters[ts] - 1) * 0.05
        r = row.to_dict()
        r["time"] = ts + frac
        expanded.append(r)
    return pd.DataFrame(expanded)


def calc_stats(ref, meas):
    diff = meas - ref
    return {
        "MAE": np.mean(np.abs(diff)),
        "RMSE": np.sqrt(np.mean(diff ** 2)),
        "Bias": np.mean(diff),
    }


def resample(df_and, df_mpu, cols):
    t_end = min(df_and["time"].max(), df_mpu["time"].max())
    t_start = max(df_and["time"].min(), df_mpu["time"].min())
    common = np.arange(t_start, t_end, 0.05)
    result_and = {"time": common}
    result_mpu = {"time": common}
    for c in cols:
        result_and[c] = np.interp(common, df_and["time"], df_and[c])
        result_mpu[c] = np.interp(common, df_mpu["time"], df_mpu[c])
    return pd.DataFrame(result_and), pd.DataFrame(result_mpu), t_end - t_start


def plot_coordenadas(df_and, df_mpu, filename):
    and_r, mpu_r, duration = resample(df_and, df_mpu, ["lat", "lon"])

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("seaborn-whitegrid")

    fig, axes = plt.subplots(2, 1, figsize=(14, 6), sharex=True)
    fig.suptitle("Comparacion GPS: NEO-6M vs Dimensity 7400 (Referencia)",
                 fontsize=13, fontweight="bold", y=0.98)

    axes[0].plot(and_r["time"], and_r["lat"], label="Dimensity 7400 (ref)",
                 color="#e74c3c", linewidth=1.2, alpha=0.7, zorder=1)
    axes[0].plot(mpu_r["time"], mpu_r["lat"], label="NEO-6M",
                 color="#2c3e50", linewidth=1.0, alpha=0.85, zorder=2)
    s_lat = calc_stats(and_r["lat"].values, mpu_r["lat"].values)
    axes[0].set_ylabel("Latitud (deg)", fontsize=11)
    axes[0].legend(loc="upper right", fontsize=10, framealpha=0.9)
    axes[0].tick_params(labelsize=10)
    txt = f"MAE={s_lat['MAE']:.6f}  RMSE={s_lat['RMSE']:.6f}  Bias={s_lat['Bias']:.6f}"
    axes[0].text(0.01, 0.95, txt, transform=axes[0].transAxes, fontsize=10,
                 verticalalignment="top", fontfamily="monospace",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    axes[1].plot(and_r["time"], and_r["lon"], label="Dimensity 7400 (ref)",
                 color="#2ecc71", linewidth=1.2, alpha=0.7, zorder=1)
    axes[1].plot(mpu_r["time"], mpu_r["lon"], label="NEO-6M",
                 color="#2c3e50", linewidth=1.0, alpha=0.85, zorder=2)
    s_lon = calc_stats(and_r["lon"].values, mpu_r["lon"].values)
    axes[1].set_ylabel("Longitud (deg)", fontsize=11)
    axes[1].set_xlabel("Tiempo (segundos)", fontsize=10)
    axes[1].legend(loc="upper right", fontsize=10, framealpha=0.9)
    axes[1].tick_params(labelsize=10)
    txt = f"MAE={s_lon['MAE']:.6f}  RMSE={s_lon['RMSE']:.6f}  Bias={s_lon['Bias']:.6f}"
    axes[1].text(0.01, 0.95, txt, transform=axes[1].transAxes, fontsize=10,
                 verticalalignment="top", fontfamily="monospace",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    output = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    print(f"  [GUARDADO] {filename}")
    plt.close()

    print(f"\n  {'Eje':<10} {'MAE':>12} {'RMSE':>12} {'Bias':>12}")
    print("  " + "-" * 52)
    for titulo, s in [("Latitud", s_lat), ("Longitud", s_lon)]:
        print(f"  {titulo:<10} {s['MAE']:>12.6f} {s['RMSE']:>12.6f} {s['Bias']:>12.6f}")


def plot_haversine(df_and, df_mpu, filename):
    t_start = max(df_and["time"].min(), df_mpu["time"].min())
    t_end = min(df_and["time"].max(), df_mpu["time"].max())
    common = np.arange(t_start, t_end, 1.0)

    lat_and = np.interp(common, df_and["time"], df_and["lat"])
    lon_and = np.interp(common, df_and["time"], df_and["lon"])
    lat_mpu = np.interp(common, df_mpu["time"], df_mpu["lat"])
    lon_mpu = np.interp(common, df_mpu["time"], df_mpu["lon"])

    distancias = haversine(lat_and, lon_and, lat_mpu, lon_mpu)

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("seaborn-whitegrid")

    fig, ax = plt.subplots(figsize=(14, 4))
    fig.suptitle("Distancia Haversine: NEO-6M vs Dimensity 7400",
                 fontsize=13, fontweight="bold", y=0.98)

    ax.plot(common - t_start, distancias, color="#9b59b6", linewidth=1.0, alpha=0.8)
    ax.axhline(y=np.mean(distancias), color="#e74c3c", linestyle="--", linewidth=1.5,
               label=f"Promedio: {np.mean(distancias):.2f} m")
    ax.axhline(y=np.max(distancias), color="#e67e22", linestyle=":", linewidth=1.5,
               label=f"Maxima: {np.max(distancias):.2f} m")
    ax.axhline(y=np.min(distancias), color="#2ecc71", linestyle=":", linewidth=1.5,
               label=f"Minima: {np.min(distancias):.2f} m")

    ax.set_ylabel("Distancia (m)", fontsize=11)
    ax.set_xlabel("Tiempo (segundos)", fontsize=10)
    ax.legend(loc="upper right", fontsize=10, framealpha=0.9)
    ax.tick_params(labelsize=10)

    stats_text = f"Min={np.min(distancias):.2f} m   Prom={np.mean(distancias):.2f} m   Max={np.max(distancias):.2f} m   Std={np.std(distancias):.2f} m"
    ax.text(0.01, 0.95, stats_text, transform=ax.transAxes, fontsize=10,
            verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    output = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    print(f"  [GUARDADO] {filename}")
    plt.close()

    print(f"\n  Haversine:")
    print(f"    Minima:   {np.min(distancias):.2f} m")
    print(f"    Promedio: {np.mean(distancias):.2f} m")
    print(f"    Maxima:   {np.max(distancias):.2f} m")
    print(f"    Std:      {np.std(distancias):.2f} m")


def plot_velocidad_precision(df_and, df_mpu, filename):
    and_r, mpu_r, duration = resample(df_and, df_mpu, ["speed", "precision"])

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("seaborn-whitegrid")

    fig, axes = plt.subplots(2, 1, figsize=(14, 6), sharex=True)
    fig.suptitle("Velocidad y Precision: NEO-6M vs Dimensity 7400",
                 fontsize=13, fontweight="bold", y=0.98)

    axes[0].plot(and_r["time"], and_r["speed"], label="Dimensity 7400 (ref)",
                 color="#e74c3c", linewidth=1.2, alpha=0.7, zorder=1)
    axes[0].plot(mpu_r["time"], mpu_r["speed"], label="NEO-6M",
                 color="#2c3e50", linewidth=1.0, alpha=0.85, zorder=2)
    s_spd = calc_stats(and_r["speed"].values, mpu_r["speed"].values)
    axes[0].set_ylabel("Velocidad (km/h)", fontsize=11)
    axes[0].legend(loc="upper right", fontsize=10, framealpha=0.9)
    axes[0].tick_params(labelsize=10)
    txt = f"MAE={s_spd['MAE']:.3f}  RMSE={s_spd['RMSE']:.3f}  Bias={s_spd['Bias']:.3f}"
    axes[0].text(0.01, 0.95, txt, transform=axes[0].transAxes, fontsize=10,
                 verticalalignment="top", fontfamily="monospace",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    axes[1].plot(and_r["time"], and_r["precision"], label="Dimensity 7400 (ref)",
                 color="#2ecc71", linewidth=1.2, alpha=0.7, zorder=1)
    axes[1].plot(mpu_r["time"], mpu_r["precision"], label="NEO-6M",
                 color="#2c3e50", linewidth=1.0, alpha=0.85, zorder=2)
    s_prec = calc_stats(and_r["precision"].values, mpu_r["precision"].values)
    axes[1].set_ylabel("Precision (m)", fontsize=11)
    axes[1].set_xlabel("Tiempo (segundos)", fontsize=10)
    axes[1].legend(loc="upper right", fontsize=10, framealpha=0.9)
    axes[1].tick_params(labelsize=10)
    txt = f"MAE={s_prec['MAE']:.3f}  RMSE={s_prec['RMSE']:.3f}  Bias={s_prec['Bias']:.3f}"
    axes[1].text(0.01, 0.95, txt, transform=axes[1].transAxes, fontsize=10,
                 verticalalignment="top", fontfamily="monospace",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    output = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    print(f"  [GUARDADO] {filename}")
    plt.close()

    print(f"\n  {'Metrica':<12} {'MAE':>8} {'RMSE':>8} {'Bias':>8}")
    print("  " + "-" * 40)
    for titulo, s in [("Velocidad", s_spd), ("Precision", s_prec)]:
        print(f"  {titulo:<12} {s['MAE']:>8.3f} {s['RMSE']:>8.3f} {s['Bias']:>8.3f}")


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
        print("[ERROR] Faltan CSVs en la carpeta Comparation")
        print("  Necesita: Android_gps_*.csv y Neo6m_gps_*.csv")
        return

    print(f"[Android] {os.path.basename(android_file)}")
    df_and = parse_csv(android_file)
    print(f"  {len(df_and)} muestras")

    print(f"[NEO-6M] {os.path.basename(mpu_file)}")
    df_mpu = parse_csv(mpu_file)
    print(f"  {len(df_mpu)} muestras")

    df_and["time"] = df_and["time"] - df_and["time"].iloc[0]
    df_mpu["time"] = df_mpu["time"] - df_mpu["time"].iloc[0]

    print("\n" + "=" * 55)
    print("  1. COORDENADAS (Latitud, Longitud)")
    print("=" * 55)
    plot_coordenadas(df_and, df_mpu, "comparacion_coordenadas.png")

    print("\n" + "=" * 55)
    print("  2. DISTANCIA HAVERSINE")
    print("=" * 55)
    plot_haversine(df_and, df_mpu, "comparacion_haversine.png")

    print("\n" + "=" * 55)
    print("  3. VELOCIDAD Y PRECISION")
    print("=" * 55)
    plot_velocidad_precision(df_and, df_mpu, "comparacion_velocidad_precision.png")

    print("\n" + "=" * 55)
    print("  LISTO - 3 graficas generadas")
    print("=" * 55)


if __name__ == "__main__":
    main()
