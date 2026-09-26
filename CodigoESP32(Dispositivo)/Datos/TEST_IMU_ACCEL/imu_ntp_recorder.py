"""
SENTINELDRIVE - IMU NTP Recorder
================================
Conecta al ESP32, activa modo NTP y guarda CSV.

Uso:
  pip install pyserial
  python imu_ntp_recorder.py
"""

import serial
import serial.tools.list_ports
import time
import sys
import os
from datetime import datetime


def detectar_puertos():
    puertos = serial.tools.list_ports.comports()
    esp32 = []
    for p in puertos:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if any(kw in desc or kw in hwid for kw in ["ch340", "cp210", "ftdi", "usb-serial", "uart", "esp32"]):
            esp32.append(p)
    return esp32 if esp32 else puertos


def seleccionar_puerto():
    puertos = detectar_puertos()
    if not puertos:
        print("[ERROR] No se encontraron puertos COM")
        print("  Conecta el ESP32 y vuelve a intentar")
        sys.exit(1)

    print("\n--- Puertos COM detectados ---")
    for i, p in enumerate(puertos):
        print(f"  [{i+1}] {p.device} - {p.description}")
    print()

    while True:
        try:
            idx = int(input("Selecciona puerto (numero): ")) - 1
            if 0 <= idx < len(puertos):
                return puertos[idx].device
        except (ValueError, EOFError):
            pass
        print("  Intento invalido")


def generar_nombre_archivo():
    ahora = datetime.now()
    return ahora.strftime("imu_ntp_%Y-%m-%d_%H-%M-%S.csv")


def main():
    print("\n========================================")
    print("  SENTINELDRIVE - IMU NTP Recorder")
    print("========================================")
    print("  Columnas: Hora; Ax; Ay; Az; Gx; Gy; Gz; Pitch; Roll; LinX; LinY; LinZ")
    print("  Frecuencia: ~20Hz (cada 50ms)")
    print("  Ctrl+C para detener y guardar")
    print("  Formato: .csv (abre directo en Excel)")
    print("========================================\n")

    puerto = seleccionar_puerto()
    baud = 115200
    print(f"  Puerto: {puerto} @ {baud} baud\n")

    try:
        ser = serial.Serial(puerto, baud, timeout=2)
        time.sleep(2)
    except serial.SerialException as e:
        print(f"[ERROR] No se pudo abrir {puerto}: {e}")
        print("  Cierra el Monitor Serial de Arduino IDE si esta abierto")
        sys.exit(1)

    ser.reset_input_buffer()

    print("[ENV] Enviando comando: ntp")
    ser.write(b"ntp\r\n")
    time.sleep(1)

    resp = ser.readline().decode("utf-8", errors="replace").strip()
    if resp:
        print(f"[ESP32] {resp}")

    nombre_archivo = generar_nombre_archivo()
    archivo = open(nombre_archivo, "w", encoding="utf-8")
    archivo.write("Hora;Ax_mps2;Ay_mps2;Az_mps2;Gx_dps;Gy_dps;Gz_dps;Pitch_deg;Roll_deg;LinX_mps2;LinY_mps2;LinZ_mps2\n")
    archivo.flush()

    print(f"[GUARDANDO] {nombre_archivo}")
    print("[GRABANDO] Presiona Ctrl+C para detener\n")

    print(f"{'Lineas':>8}  {'Hora':^10}  {'Ax':>7}  {'Ay':>7}  {'Az':>7}  {'Gx':>7}  {'Gy':>7}  {'Gz':>7}  {'Pitch':>7}  {'Roll':>7}  {'LinX':>7}  {'LinY':>7}  {'LinZ':>7}")
    print("-" * 145)

    lineas = 0
    inicio = time.time()

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue

            linea = raw.decode("utf-8", errors="replace").strip()

            if not linea or linea.startswith("#") or linea.startswith("---"):
                if linea:
                    print(f"  [ESP32] {linea}")
                continue

            partes = linea.split(";")
            if len(partes) != 12:
                continue

            archivo.write(linea + "\n")
            archivo.flush()
            lineas += 1

            try:
                hora = partes[0]
                ax = float(partes[1].replace(",", "."))
                ay = float(partes[2].replace(",", "."))
                az = float(partes[3].replace(",", "."))
                gx = float(partes[4].replace(",", "."))
                gy = float(partes[5].replace(",", "."))
                gz = float(partes[6].replace(",", "."))
                pitch = float(partes[7].replace(",", "."))
                roll = float(partes[8].replace(",", "."))
                linx = float(partes[9].replace(",", "."))
                liny = float(partes[10].replace(",", "."))
                linz = float(partes[11].replace(",", "."))

                print(f"{lineas:>8}  {hora:^10}  {ax:>7.3f}  {ay:>7.3f}  {az:>7.3f}  {gx:>7.2f}  {gy:>7.2f}  {gz:>7.2f}  {pitch:>7.2f}  {roll:>7.2f}  {linx:>7.3f}  {liny:>7.3f}  {linz:>7.3f}", end="\r")
            except (ValueError, IndexError):
                pass

    except KeyboardInterrupt:
        pass
    finally:
        elapsed = time.time() - inicio
        archivo.close()
        ser.close()

        print("\n\n" + "=" * 55)
        print("  GRABACION FINALIZADA")
        print("=" * 55)
        print(f"  Archivo:  {os.path.abspath(nombre_archivo)}")
        print(f"  Lineas:   {lineas}")
        print(f"  Duracion: {elapsed:.1f} segundos")
        if elapsed > 0:
            print(f"  Promedio: {lineas/elapsed:.1f} lineas/seg")
        print("=" * 55)
        print("\n  Abre el archivo en Excel")
        print()


if __name__ == "__main__":
    main()
