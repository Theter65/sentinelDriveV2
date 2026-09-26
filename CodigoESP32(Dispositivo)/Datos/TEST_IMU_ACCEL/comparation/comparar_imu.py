"""
SENTINELDRIVE - Comparacion IMU: MPU6050 vs LSM6DSO
====================================================
4 graficas: Aceleracion, Pitch/Roll, Aceleracion Lineal, Giroscopio
LSM6DSO = referencia.

Uso:
  pip install pandas matplotlib
  python comparar_imu.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os


def parse_csv(filepath):
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(";")
            if len(parts) != 12:
                continue
            try:
                h, m, s = parts[0].split(":")
                t_sec = int(h) * 3600 + int(m) * 60 + int(s)
                rows.append({
                    "t_sec": t_sec,
                    "ax": float(parts[1].replace(",", ".")),
                    "ay": float(parts[2].replace(",", ".")),
                    "az": float(parts[3].replace(",", ".")),
                    "gx": float(parts[4].replace(",", ".")),
                    "gy": float(parts[5].replace(",", ".")),
                    "gz": float(parts[6].replace(",", ".")),
                    "pitch": float(parts[7].replace(",", ".")),
                    "roll": float(parts[8].replace(",", ".")),
                    "linx": float(parts[9].replace(",", ".")),
                    "liny": float(parts[10].replace(",", ".")),
                    "linz": float(parts[11].replace(",", ".")),
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


def parse_csv_android(filepath):
    df = parse_csv(filepath)
    if len(df) == 0:
        return df
    df["gx"] = df["gx"] * (180.0 / np.pi)
    df["gy"] = df["gy"] * (180.0 / np.pi)
    df["gz"] = df["gz"] * (180.0 / np.pi)
    return df


def calc_stats(ref, meas):
    diff = meas - ref
    return {
        "MAE": np.mean(np.abs(diff)),
        "RMSE": np.sqrt(np.mean(diff ** 2)),
        "Bias": np.mean(diff),
        "Corr": np.corrcoef(ref, meas)[0, 1] if len(ref) > 1 else 0,
    }


def resample(df_and, df_mpu, cols):
    t_end = min(df_and["time"].max(), df_mpu["time"].max())
    common = np.arange(0, t_end, 0.05)
    result_and = {"time": common}
    result_mpu = {"time": common}
    for c in cols:
        result_and[c] = np.interp(common, df_and["time"], df_and[c])
        result_mpu[c] = np.interp(common, df_mpu["time"], df_mpu[c])
    return pd.DataFrame(result_and), pd.DataFrame(result_mpu), t_end


def plot_comparacion(df_and, df_mpu, cols, titles, ylabel, filename):
    and_r, mpu_r, t_end = resample(df_and, df_mpu, cols)

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("seaborn-whitegrid")

    n = len(cols)
    fig, axes = plt.subplots(n, 1, figsize=(14, 3 * n + 1), sharex=True)
    if n == 1:
        axes = [axes]

    fig.suptitle("Comparacion: MPU6050 vs LSM6DSO (Referencia)",
                 fontsize=13, fontweight="bold", y=0.98)

    colores = ["#e74c3c", "#2ecc71", "#3498db", "#9b59b6"]
    for i, (ax, col, titulo) in enumerate(zip(axes, cols, titles)):
        ax.plot(and_r["time"], and_r[col],
                label="LSM6DSO (ref)", color=colores[i % len(colores)],
                linewidth=1.2, alpha=0.7, zorder=1)
        ax.plot(mpu_r["time"], mpu_r[col],
                label="MPU6050", color="#2c3e50",
                linewidth=1.0, alpha=0.85, zorder=2)
        s = calc_stats(and_r[col].values, mpu_r[col].values)
        ax.set_ylabel(titulo, fontsize=11)
        ax.legend(loc="upper right", fontsize=10, framealpha=0.9)
        ax.tick_params(labelsize=10)
        txt = f"MAE={s['MAE']:.3f}  RMSE={s['RMSE']:.3f}  Bias={s['Bias']:.3f}"
        ax.text(0.01, 0.95, txt, transform=ax.transAxes, fontsize=10,
                verticalalignment="top", fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    axes[-1].set_xlabel("Tiempo (segundos)", fontsize=10)
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    output = os.path.join(SCRIPT_DIR, filename)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    print(f"  [GUARDADO] {filename}")
    plt.close()

    print(f"\n  {'Eje':<8} {'MAE':>8} {'RMSE':>8} {'Bias':>8}")
    print("  " + "-" * 40)
    for col, titulo in zip(cols, titles):
        s = calc_stats(and_r[col].values, mpu_r[col].values)
        print(f"  {titulo:<8} {s['MAE']:>8.4f} {s['RMSE']:>8.4f} {s['Bias']:>8.4f}")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    android_file = None
    mpu_file = None
    for f in os.listdir(SCRIPT_DIR):
        if f.endswith(".csv"):
            if f.startswith("Android"):
                android_file = os.path.join(SCRIPT_DIR, f)
            elif f.startswith("imu_"):
                mpu_file = os.path.join(SCRIPT_DIR, f)

    if not android_file or not mpu_file:
        print("[ERROR] Faltan CSVs en la carpeta comparation")
        return

    print(f"[LSM6DSO] {os.path.basename(android_file)}")
    df_and = parse_csv_android(android_file)
    print(f"  {len(df_and)} muestras (gyro rad->deg convertido)")

    print(f"[MPU6050] {os.path.basename(mpu_file)}")
    df_mpu = parse_csv(mpu_file)
    print(f"  {len(df_mpu)} muestras")

    # Normalizar: ambos empiezan en t=0
    df_and["time"] = df_and["time"] - df_and["time"].iloc[0]
    df_mpu["time"] = df_mpu["time"] - df_mpu["time"].iloc[0]

    # Sin offset por ahora
    print("\n[OFFSET] Sin ajuste temporal")

    print("\n" + "=" * 55)
    print("  1. ACELERACION (Ax, Ay, Az)")
    print("=" * 55)
    plot_comparacion(
        df_and, df_mpu,
        cols=["ax", "ay", "az"],
        titles=["Ax (m/s2)", "Ay (m/s2)", "Az (m/s2)"],
        ylabel="Aceleracion",
        filename="comparacion_aceleracion.png",
    )

    print("\n" + "=" * 55)
    print("  2. PITCH Y ROLL")
    print("=" * 55)
    plot_comparacion(
        df_and, df_mpu,
        cols=["pitch", "roll"],
        titles=["Pitch (deg)", "Roll (deg)"],
        ylabel="Angulos",
        filename="comparacion_pitch_roll.png",
    )

    print("\n" + "=" * 55)
    print("  3. ACELERACION LINEAL (LinX, LinY, LinZ)")
    print("=" * 55)
    plot_comparacion(
        df_and, df_mpu,
        cols=["linx", "liny", "linz"],
        titles=["LinX (m/s2)", "LinY (m/s2)", "LinZ (m/s2)"],
        ylabel="Acc Lineal",
        filename="comparacion_lineal.png",
    )

    print("\n" + "=" * 55)
    print("  4. GIROSCOPIO (Gx, Gy, Gz)")
    print("=" * 55)
    plot_comparacion(
        df_and, df_mpu,
        cols=["gx", "gy", "gz"],
        titles=["Gx (deg/s)", "Gy (deg/s)", "Gz (deg/s)"],
        ylabel="Giroscopio",
        filename="comparacion_giroscopio.png",
    )

    print("\n" + "=" * 55)
    print("  LISTO - 4 graficas generadas")
    print("=" * 55)


if __name__ == "__main__":
    main()
