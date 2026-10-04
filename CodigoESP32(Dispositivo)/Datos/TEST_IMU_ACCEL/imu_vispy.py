"""SENTINELDRIVE IMU monitor: Matplotlib charts and a VisPy 3D viewer."""
import sys, serial, serial.tools.list_ports, threading, time, collections, math
import numpy as np
from vispy import scene, app
from vispy.visuals.transforms import MatrixTransform
from PyQt5 import QtCore, QtWidgets, QtGui
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

BAUD, NCOLS, BUFFER = 115200, 28, 2000
CR, CG, CB, CY = (220/255, 53/255, 69/255, 1), (197/255, 146/255, 0, 1), (40/255, 116/255, 199/255, 1), (0.95, 0.77, 0.06, 1)
CC = (0.6, 0.6, 0.6, 1)
BG = (0.059, 0.059, 0.137, 1)
WINDOW_SEC = 10.0
RAW_ACCEL_VECTOR_SCALE = 1.5
PANEL_BG = "#15182b"
PANEL_BORDER = "#2c3558"
TEXT_MAIN = "#e8ecff"
TEXT_MUTED = "#98a2c4"
TEXT_ACCENT = "#74c0fc"
TEXT_OK = "#34d399"
TEXT_WARN = "#f59e0b"
TEXT_BAD = "#ef4444"

PLOT_CFG = [
    {"title": "Aceleración RAW · sin filtrar", "unit": "m/s²", "cols": (0, 1, 2), "names": ("X · longitudinal · frente", "Y · transversal · izquierda", "Z · vertical · arriba"), "ylim": (-20, 20)},
    {"title": "Aceleración filtrada · con gravedad", "unit": "m/s²", "cols": (3, 4, 5), "names": ("X · longitudinal · frente", "Y · transversal · izquierda", "Z · vertical · arriba"), "ylim": (-20, 20)},
    {"title": "Gravedad · Complementario", "unit": "m/s²", "cols": (9, 10, 11), "names": ("X", "Y", "Z"), "ylim": (-12, 12)},
    {"title": "Aceleración lineal · Complementario", "unit": "m/s²", "cols": (6, 7, 8), "names": ("X", "Y", "Z"), "ylim": (-10, 10)},
    {"title": "Gravedad · Madgwick", "unit": "m/s²", "cols": (15, 16, 17), "names": ("X", "Y", "Z"), "ylim": (-12, 12)},
    {"title": "Aceleración lineal · Madgwick", "unit": "m/s²", "cols": (12, 13, 14), "names": ("X", "Y", "Z"), "ylim": (-10, 10)},
    {"title": "Giroscopio · RAW y filtrado", "unit": "°/s", "cols": (18, 19, 20, 21, 22, 23), "names": ("RAW X", "RAW Y", "RAW Z", "Filtrado X", "Filtrado Y", "Filtrado Z"), "ylim": (-100, 100)},
    {"title": "Orientación · Complementario", "unit": "°", "cols": (24, 25), "names": ("Pitch", "Roll"), "ylim": (-90, 90)},
    {"title": "Orientación · Madgwick", "unit": "°", "cols": (26, 27), "names": ("Pitch", "Roll"), "ylim": (-90, 90)},
]
CHART_COLORS = ["#dc3545", "#c59200", "#2874c7"]
PLOT_GROUPS = [
    ("Aceleración", (0, 1, 3, 5)),
    ("Gravedad", (2, 4)),
    ("Giroscopio", (6,)),
    ("Orientación", (7, 8)),
]
PLOT_COLORS = [CR, CG, CB]


def demo_orientation_matrix(pitch_deg, roll_deg):
    """Convert IMU angles to the VisPy scene convention for display only.

    The IMU uses Z-down coordinates while the scene uses Z-up. This maps a
    positive pitch to a rising +X front, and a positive roll to a rising -Y
    side. The sensor and filter outputs themselves are not modified.
    """
    pitch = math.radians(-float(pitch_deg))
    roll = math.radians(-float(roll_deg))
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    return np.array([
        [cp, 0, sp, 0], [sr * sp, cr, -sr * cp, 0],
        [-cr * sp, sr, cr * cp, 0], [0, 0, 0, 1]
    ], dtype=np.float32)


class SerialReader:
    def __init__(self):
        self.buf = collections.deque(maxlen=BUFFER)
        self.tbuf = collections.deque(maxlen=BUFFER)
        self.on = False
        self._s = None
        self._t = None
        self._stop = threading.Event()
        self._lk = threading.Lock()
        self.last = None
        self.frame_count = 0
        self.fps_count = 0
        self.fps = 0.0
        self._fps_t = time.time()

    def ports(self):
        return [p.device for p in sorted(serial.tools.list_ports.comports())]

    def connect(self, port):
        self.disconnect()
        try:
            # Keep connection setup responsive; boot text is ignored by _rd
            # until valid CSV samples arrive.
            self._s = serial.Serial(port, BAUD, timeout=0.1, exclusive=True)
            self._s.reset_input_buffer()
            self._s.reset_output_buffer()
            self._stop.clear()
            self._t = threading.Thread(target=self._rd, daemon=True)
            self._t.start()
            self.on = True
            return True, f"Conectado a {port}"
        except Exception as e:
            return False, str(e)

    def disconnect(self):
        self._stop.set()
        if self._t:
            self._t.join(timeout=2)
        if self._s and self._s.is_open:
            try:
                self._s.write(b"pause\n")
                time.sleep(0.05)
            except:
                pass
            self._s.close()
        self.on = False
        with self._lk:
            self.buf.clear()
            self.tbuf.clear()

    def send(self, cmd):
        if self._s and self._s.is_open:
            try:
                self._s.write((cmd + "\n").encode())
                return True
            except:
                pass
        return False

    def _rd(self):
        errs = 0
        while not self._stop.is_set():
            try:
                if not self._s or not self._s.is_open:
                    break
                raw = self._s.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("#"):
                    print(f"[ESP] {line[:80]}")
                    continue
                parts = line.split(",")
                if len(parts) == NCOLS:
                    try:
                        vals = [float(x) for x in parts]
                        t = time.time()
                    except ValueError:
                        continue
                elif len(parts) == NCOLS + 1 and "T" in parts[0]:
                    try:
                        vals = [float(x) for x in parts[1:]]
                        t = time.time()
                    except ValueError:
                        continue
                else:
                    if errs < 5:
                        print(f"[SKIP] cols={len(parts)} NCOLS={NCOLS} line={line[:80]}")
                        errs += 1
                    continue
                with self._lk:
                    self.buf.append(vals)
                    self.tbuf.append(t)
                    self.last = vals
                    self.frame_count += 1
                    self.fps_count += 1
                    now = time.time()
                    if now - self._fps_t >= 1.0:
                        self.fps = self.fps_count / (now - self._fps_t)
                        self.fps_count = 0
                        self._fps_t = now
                    if self.frame_count == 1:
                        print(f"[OK] Primera linea OK: {vals[:4]}... (cols={len(vals)})")
            except Exception as e:
                if errs < 3:
                    print(f"[ERR] Reader: {e}")
                    errs += 1
        self.on = False

    def get_data(self, since_frame=-1):
        with self._lk:
            frame_count = self.frame_count
            fps = self.fps
            if not self.buf or frame_count == since_frame:
                return None, None, self.last, frame_count, fps
            vals = list(self.buf)
            ts = list(self.tbuf)
            last = self.last
        return vals, ts, last, frame_count, fps


class Viewer3D(QtWidgets.QMainWindow):
    """Ventana de modelos cúbicos (COMP y MADG) con métricas de señales."""

    def __init__(self, reader):
        super().__init__()
        self.R = reader
        self.metric_labels = {}
        self.setWindowTitle("SENTINELDRIVE | VisPy 3D · Demo corregida")
        self.resize(1320, 900)
        self.setStyleSheet("""
            QMainWindow {background: #0f0f23;}
            QFrame#StatsCard {
                background: #15182b;
                border: 1px solid #2c3558;
                border-radius: 10px;
            }
        """)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        lay = QtWidgets.QVBoxLayout(central)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("+X longitudinal al frente · +Y transversal a la izquierda · +Z vertical hacia arriba"))
        controls.addStretch(1)
        self.reset_view_button = QtWidgets.QPushButton("Restablecer vista")
        self.reset_view_button.setToolTip("Recuperar el ángulo y el zoom iniciales")
        self.reset_view_button.setStyleSheet("background:#16834f; color:white; padding:8px 14px; border:0; border-radius:6px; font-weight:700;")
        controls.addWidget(self.reset_view_button)
        self.auto_rotate_button = QtWidgets.QPushButton("Rotación automática")
        self.auto_rotate_button.setCheckable(True)
        self.auto_rotate_button.setStyleSheet("background:#315f49; color:white; padding:8px 14px; border:0; border-radius:6px; font-weight:700;")
        controls.addWidget(self.auto_rotate_button)
        lay.addLayout(controls)

        # --- Canvas con vistas 3D ---
        self.canvas = scene.SceneCanvas(keys="interactive", bgcolor=BG)
        self.canvas.native.setMinimumHeight(360)
        lay.addWidget(self.canvas.native, 3)

        g = self.canvas.central_widget.add_grid(spacing=8, margin=4)

        self.v3_comp = g.add_view(row=0, col=0)
        self.v3_comp.camera = "turntable"
        self.v3_comp.camera.fov = 32
        self.v3_comp.camera.distance = 32
        self.v3_comp.camera.elevation = 20
        self.v3_comp.camera.azimuth = -45
        self.v3_comp.border_color = (0.2, 0.7, 0.2, 0.6)
        self.rot_comp, self.accel_comp = self._setup_3d(self.v3_comp, (0.15, 0.8, 0.15, 0.35))

        self.v3_madg = g.add_view(row=0, col=1)
        self.v3_madg.camera = "turntable"
        self.v3_madg.camera.fov = 32
        self.v3_madg.camera.distance = 32
        self.v3_madg.camera.elevation = 20
        self.v3_madg.camera.azimuth = -45
        self.v3_madg.border_color = (0.2, 0.4, 0.8, 0.6)
        self.rot_madg, self.accel_madg = self._setup_3d(self.v3_madg, (0.15, 0.5, 1.0, 0.35))

        self.reset_view_button.clicked.connect(self.reset_cameras)
        self._spin_timer = QtCore.QTimer(self)
        self._spin_timer.setInterval(33)
        self._spin_timer.timeout.connect(self._spin_cameras)
        self.auto_rotate_button.toggled.connect(self._toggle_auto_rotate)

        label_comp = scene.widgets.Label("COMPLEMENTARY", color=(0.6, 1.0, 0.6, 1), font_size=11)
        label_comp.stretch = (1, 0.12)
        g.add_widget(label_comp, row=1, col=0)
        label_madg = scene.widgets.Label("MADGWICK", color=(0.6, 0.8, 1.0, 1), font_size=11)
        label_madg.stretch = (1, 0.12)
        g.add_widget(label_madg, row=1, col=1)

        # --- Panel de metricas ---
        stats_card = QtWidgets.QFrame()
        stats_card.setObjectName("StatsCard")
        stats_layout = QtWidgets.QVBoxLayout(stats_card)
        stats_layout.setContentsMargins(16, 10, 16, 10)
        stats_layout.setSpacing(6)

        stats_head = QtWidgets.QHBoxLayout()
        stats_title = QtWidgets.QLabel("Resumen de señales")
        stats_title.setStyleSheet("color: #f4f7ff; font-size: 14px; font-weight: 700;")
        stats_hint = QtWidgets.QLabel("Aceleración RAW en amarillo · Valores instantáneos por eje")
        stats_hint.setStyleSheet("color: #8f9cc7; font-size: 11px;")
        stats_head.addWidget(stats_title)
        stats_head.addStretch(1)
        stats_head.addWidget(stats_hint)
        stats_layout.addLayout(stats_head)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        headers = ["Eje", "RAW", "Filtrado", "Lineal COMP", "Grav COMP", "Lineal MADG", "Grav MADG", "Gyro RAW", "Gyro Filt"]
        for col, header in enumerate(headers):
            lbl = QtWidgets.QLabel(header)
            lbl.setStyleSheet("color: #8f9cc7; font-size: 11px; font-weight: 700;")
            lbl.setAlignment(QtCore.Qt.AlignCenter if col > 0 else QtCore.Qt.AlignLeft)
            grid.addWidget(lbl, 0, col)

        axes = ["X", "Y", "Z"]
        metric_keys = ["raw", "filtered", "linear", "grav_comp", "linear_madg", "grav_madg", "gyro_raw", "gyro_filt"]
        for row, axis in enumerate(axes, start=1):
            axis_lbl = QtWidgets.QLabel(axis)
            axis_lbl.setStyleSheet("color: #f4f7ff; font-size: 13px; font-weight: 700;")
            axis_lbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            grid.addWidget(axis_lbl, row, 0)
            self.metric_labels[axis] = {}
            for col, key in enumerate(metric_keys, start=1):
                val_lbl = QtWidgets.QLabel("--.--")
                val_lbl.setAlignment(QtCore.Qt.AlignCenter)
                val_lbl.setStyleSheet(
                    "color: #dbe4ff; font-family: Consolas, monospace; font-size: 13px; "
                    "padding: 6px 8px; background: #101425; border: 1px solid #27304f; border-radius: 6px;"
                )
                grid.addWidget(val_lbl, row, col)
                self.metric_labels[axis][key] = val_lbl

        pitch_rows = [("COMP P/R", "comp_pr"), ("MADG P/R", "madg_pr")]
        for row_offset, (label, key) in enumerate(pitch_rows, start=len(axes) + 1):
            axis_lbl = QtWidgets.QLabel(label)
            axis_lbl.setStyleSheet("color: #f4f7ff; font-size: 13px; font-weight: 700;")
            axis_lbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            grid.addWidget(axis_lbl, row_offset, 0)
            self.metric_labels[key] = {}
            for col, col_label in enumerate(["Pitch", "Roll"], start=1):
                val_lbl = QtWidgets.QLabel("--.--")
                val_lbl.setAlignment(QtCore.Qt.AlignCenter)
                val_lbl.setStyleSheet(
                    "color: #dbe4ff; font-family: Consolas, monospace; font-size: 13px; "
                    "padding: 6px 8px; background: #101425; border: 1px solid #27304f; border-radius: 6px;"
                )
                grid.addWidget(val_lbl, row_offset, col)
                self.metric_labels[key][col_label] = val_lbl
        stats_layout.addLayout(grid)
        lay.addWidget(stats_card, 1)

    def closeEvent(self, event):
        self._spin_timer.stop()
        self.auto_rotate_button.blockSignals(True)
        self.auto_rotate_button.setChecked(False)
        self.auto_rotate_button.setText("Rotación automática")
        self.auto_rotate_button.blockSignals(False)
        super().closeEvent(event)

    def _fmt(self, value):
        return f"{value:+.3f}"

    def reset_cameras(self):
        for view in (self.v3_comp, self.v3_madg):
            view.camera.azimuth = -45
            view.camera.elevation = 20
            view.camera.distance = 32
            view.camera.center = (0, 0, 0)

    def _toggle_auto_rotate(self, enabled):
        self.auto_rotate_button.setText("Pausar rotación" if enabled else "Rotación automática")
        if enabled:
            self._spin_timer.start()
        else:
            self._spin_timer.stop()

    def _spin_cameras(self):
        for view in (self.v3_comp, self.v3_madg):
            view.camera.azimuth = (view.camera.azimuth + 0.6) % 360

    def update_metrics(self, last):
        """Called by IMUWindow._update() to refresh the metrics panel."""
        mapping = {
            "X": {"raw": last[0], "filtered": last[3], "linear": last[6],
                  "grav_comp": last[9], "linear_madg": last[12],
                  "grav_madg": last[15], "gyro_raw": last[18], "gyro_filt": last[21]},
            "Y": {"raw": last[1], "filtered": last[4], "linear": last[7],
                  "grav_comp": last[10], "linear_madg": last[13],
                  "grav_madg": last[16], "gyro_raw": last[19], "gyro_filt": last[22]},
            "Z": {"raw": last[2], "filtered": last[5], "linear": last[8],
                  "grav_comp": last[11], "linear_madg": last[14],
                  "grav_madg": last[17], "gyro_raw": last[20], "gyro_filt": last[23]},
        }
        for axis, values in mapping.items():
            for key, value in values.items():
                self.metric_labels[axis][key].setText(self._fmt(value))
        self.metric_labels["comp_pr"]["Pitch"].setText(f"{last[24]:+.3f}")
        self.metric_labels["comp_pr"]["Roll"].setText(f"{last[25]:+.3f}")
        self.metric_labels["madg_pr"]["Pitch"].setText(f"{last[26]:+.3f}")
        self.metric_labels["madg_pr"]["Roll"].setText(f"{last[27]:+.3f}")

    def _setup_3d(self, parent_view, box_color):
        l = w = h = 3
        verts = np.array([
            [-l, -w, -h], [l, -w, -h], [l, w, -h], [-l, w, -h],
            [-l, -w, h], [l, -w, h], [l, w, h], [-l, w, h]
        ], dtype=np.float32)
        faces = np.array([
            [0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
            [0, 3, 7], [0, 7, 4], [1, 2, 6], [1, 6, 5]
        ], dtype=np.uint32)
        box_mesh = scene.visuals.Mesh(verts, faces, color=box_color,
                                      shading="flat", parent=parent_view.scene)
        edge_color = tuple(min(1.0, c * 1.2) for c in box_color[:3]) + (0.7,)
        edg = np.array([[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4],
                        [0, 4], [1, 5], [2, 6], [3, 7]])
        ev = verts[edg].reshape(-1, 3)
        rot = scene.Node(parent=parent_view.scene)
        box_mesh.parent = rot
        scene.visuals.Line(pos=ev, color=edge_color, width=1, parent=rot)
        md = 8
        # VisPy usa Z hacia arriba; el Z positivo del IMU apunta hacia abajo,
        # por eso su eje se dibuja hacia -Z en coordenadas de la escena.
        for pts, cl, lb in [([0, 0, 0, md, 0, 0], CR, "X+ · LONGITUDINAL · FRENTE"), ([0, 0, 0, 0, md, 0], CG, "Y+ · TRANSVERSAL · IZQUIERDA"),
                            ([0, 0, 0, 0, 0, -md], CB, "Z+ · VERTICAL · ARRIBA")]:
            pa = np.array(pts, dtype=np.float32).reshape(2, 3)
            scene.visuals.Line(pos=pa, color=cl, width=3, parent=rot)
            scene.visuals.Text(lb, pos=pa[1], color=cl, font_size=14, parent=rot)
        scene.visuals.Text("FRENTE (+X)", pos=(md + 0.5, 0, 0), color=CR, font_size=14, parent=rot)
        scene.visuals.Text("ATRÁS (−X)", pos=(-md - 0.5, 0, 0), color=CR, font_size=14, parent=rot)
        scene.visuals.Markers(pos=np.zeros((1, 3)), size=6, face_color=(1, 0.75, 0, 1),
                              parent=parent_view.scene)
        rot.transform = MatrixTransform()
        # Vector de aceleración leída directamente del acelerómetro (columnas 0-2).
        # Se dibuja en el marco del sensor y rota junto con la caja.
        vector = scene.visuals.Line(
            pos=np.array([[0, 0, 0], [0, 0, 0]], dtype=np.float32),
            color=CY, width=4, parent=rot,
        )
        endpoint = scene.visuals.Markers(
            pos=np.zeros((1, 3), dtype=np.float32), size=10,
            face_color=CY, edge_color=(1, 1, 1, 0.9), parent=rot,
        )
        vector_label = scene.visuals.Text(
            "Aceleración RAW", pos=(0, 0, 0), color=CY,
            font_size=10, parent=rot,
        )
        return rot, (vector, endpoint, vector_label)

    @staticmethod
    def _update_accel_vector(visuals, values):
        vector, endpoint, label = visuals
        xyz = np.array(values, dtype=np.float32, copy=True)
        # Llevar Z positivo hacia abajo del marco del sensor a la escena Z-up.
        xyz[2] *= -1.0
        magnitude = float(np.linalg.norm(xyz))
        # Normalizar mantiene visible la dirección incluso durante impactos;
        # la magnitud se muestra en la etiqueta para conservar la escala física.
        length = min(magnitude * RAW_ACCEL_VECTOR_SCALE, 22.0)
        tip = xyz / magnitude * length if magnitude > 1e-6 else np.zeros(3, dtype=np.float32)
        vector.set_data(pos=np.array([[0, 0, 0], tip], dtype=np.float32))
        endpoint.set_data(pos=tip.reshape(1, 3))
        label.pos = tip + np.array([0.7, 0.7, 0.7], dtype=np.float32)
        label.text = f"RAW {magnitude:.2f} m/s²"


class IMUWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.R = SerialReader()
        self.live_labels = {}
        self.viewer3d = Viewer3D(self.R)
        self._last_frame_seen = -1
        self._latest_data = None
        self._latest_times = None
        self._latest_last = None
        self._setup_ui()
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._update)
        # Serial commonly arrives at 20–200 Hz; repainting faster than 30 Hz
        # does not add useful information and starves Qt/VisPy on slower PCs.
        self._timer.start(33)

    def closeEvent(self, event):
        # Cerrar tambien la ventana 3D cuando se cierra la principal
        self.viewer3d.close()
        super().closeEvent(event)

    def _setup_ui(self):
        self.setWindowTitle("SENTINELDRIVE | Monitor de sensores IMU")
        self.resize(1480, 940)
        self.setStyleSheet("""
            QMainWindow, QWidget {background:#f1f6f2; color:#19352a;}
            QLabel {background:transparent; color:#456052; font-size:12px;}
            QToolBar {background:#ffffff; spacing:8px; padding:9px 12px; border-bottom:1px solid #dbe7de;}
            QPushButton {padding:8px 16px; border:0; border-radius:7px; font-weight:700; color:white;}
            QComboBox {background:#f8fbf8; color:#19352a; padding:7px 10px; border:1px solid #cbdccf; border-radius:6px;}
            QFrame#InfoCard {background:#ffffff; border:1px solid #dbe7de; border-radius:12px;}
            QTabWidget::pane {background:#ffffff; border:1px solid #dbe7de; border-radius:10px; top:-1px;}
            QTabBar::tab {background:#e7f0e9; color:#456052; min-width:110px; padding:10px 16px; margin-right:5px; border-top-left-radius:7px; border-top-right-radius:7px; font-weight:700;}
            QTabBar::tab:selected {background:#19734b; color:#ffffff;}
            QCheckBox {color:#28553e;}
        """)
        toolbar = self.addToolBar("Conexión y controles")
        toolbar.setMovable(False)
        toolbar.addWidget(QtWidgets.QLabel("  Puerto:"))
        self.cb_p = QtWidgets.QComboBox()
        self.cb_p.setMinimumWidth(125)
        toolbar.addWidget(self.cb_p)
        self.b_ref = QtWidgets.QPushButton("Refrescar")
        self.b_ref.setStyleSheet("background:#64796c;")
        toolbar.addWidget(self.b_ref)
        self.b_con = QtWidgets.QPushButton("Conectar")
        self.b_con.setStyleSheet("background:#16834f;")
        toolbar.addWidget(self.b_con)
        self.b_plot = QtWidgets.QPushButton("Graficar")
        self.b_plot.setStyleSheet("background:#2e8b57;")
        toolbar.addWidget(self.b_plot)
        self.b_stop = QtWidgets.QPushButton("Pausar")
        self.b_stop.setStyleSheet("background:#a45d48;")
        toolbar.addWidget(self.b_stop)
        self.b_3d = QtWidgets.QPushButton("Vista 3D")
        self.b_3d.setStyleSheet("background:#315f49;")
        toolbar.addWidget(self.b_3d)
        self.lbl_s = QtWidgets.QLabel("  Desconectado")
        toolbar.addWidget(self.lbl_s)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.info_card = QtWidgets.QFrame()
        self.info_card.setObjectName("InfoCard")
        info_layout = QtWidgets.QHBoxLayout(self.info_card)
        info_layout.setContentsMargins(20, 16, 20, 16)
        info_layout.setSpacing(24)
        title_box = QtWidgets.QVBoxLayout()
        self.lbl_title = QtWidgets.QLabel("SENTINELDRIVE")
        self.lbl_title.setStyleSheet("color:#164b35; font-size:21px; font-weight:800;")
        self.lbl_subtitle = QtWidgets.QLabel("Monitor de aceleración, orientación y giroscopio · tiempo real")
        self.lbl_subtitle.setStyleSheet("color:#698174; font-size:12px;")
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_subtitle)
        info_layout.addLayout(title_box, 2)

        details = QtWidgets.QVBoxLayout()
        self.live_labels["connection"] = QtWidgets.QLabel("Desconectado")
        self.live_labels["connection"].setStyleSheet("color:#7d3b31; background:#f7e5df; padding:7px 12px; border-radius:9px; font-weight:800;")
        self.live_labels["angles"] = QtWidgets.QLabel("COMPLEMENTARIO  Pitch --.-°  Roll --.-°   |   MADGWICK  Pitch --.-°  Roll --.-°")
        self.live_labels["angles"].setStyleSheet("color:#1d5038; font-size:13px; font-weight:700;")
        self.live_labels["perf"] = QtWidgets.QLabel("Entrada -- Hz  ·  Muestras --  ·  Buffer --  ·  Ventana 10 s")
        self.live_labels["perf"].setStyleSheet("color:#718577; font-size:11px;")
        details.addWidget(self.live_labels["connection"])
        details.addWidget(self.live_labels["angles"])
        details.addWidget(self.live_labels["perf"])
        info_layout.addLayout(details, 3)
        layout.addWidget(self.info_card)

        heading = QtWidgets.QHBoxLayout()
        heading_label = QtWidgets.QLabel("SEÑALES EN TIEMPO REAL")
        heading_label.setStyleSheet("color:#28553e; font-size:12px; font-weight:800; letter-spacing:1px;")
        heading.addWidget(heading_label)
        heading.addStretch(1)
        for label, color in (("X · longitudinal · frente", CHART_COLORS[0]), ("Y · transversal · izquierda", CHART_COLORS[1]), ("Z · vertical · arriba", CHART_COLORS[2])):
            axis_key = QtWidgets.QLabel(f"●  {label}")
            axis_key.setStyleSheet(f"color:{color}; font-size:11px; font-weight:700; padding:2px 8px;")
            heading.addWidget(axis_key)
        layout.addLayout(heading)

        self.plot_tabs = QtWidgets.QTabWidget()
        self.plot_tabs.setDocumentMode(True)
        self.plot_tabs.setMovable(False)
        self.plot_canvases = []
        self.plot_artists = {}
        self._plot_backgrounds = {}
        self._last_plot_draw = 0.0
        for tab_title, plot_indexes in PLOT_GROUPS:
            page = QtWidgets.QWidget()
            page_layout = QtWidgets.QVBoxLayout(page)
            page_layout.setContentsMargins(14, 14, 14, 14)
            count = len(plot_indexes)
            rows, cols = (2, 2) if count > 2 else ((1, 2) if count == 2 else (1, 1))
            figure = Figure(figsize=(12, 7), facecolor="#ffffff")
            axes = figure.subplots(rows, cols, squeeze=False).ravel()
            figure.subplots_adjust(left=0.075, right=0.985, top=0.93, bottom=0.105, hspace=0.40, wspace=0.24)
            canvas = FigureCanvas(figure)
            canvas.setMinimumHeight(590)
            page_layout.addWidget(canvas)
            self.plot_canvases.append(canvas)

            for slot, plot_index in enumerate(plot_indexes):
                cfg = PLOT_CFG[plot_index]
                ax = axes[slot]
                ax.set_facecolor("#fbfdfb")
                ax.set_title(cfg["title"], loc="left", color="#184b35", fontsize=11, fontweight="bold", pad=13)
                ax.set_ylabel(cfg["unit"], color="#496452", fontsize=9, labelpad=8)
                ax.set_xlabel("Ventana reciente (s)", color="#496452", fontsize=9, labelpad=7)
                ax.set_ylim(*cfg["ylim"])
                ax.set_xlim(0, WINDOW_SEC)
                ax.grid(True, color="#dce9df", linewidth=0.8)
                ax.axhline(0, color="#94a89a", linewidth=0.9, alpha=0.8)
                ax.tick_params(colors="#587263", labelsize=9, pad=4)
                for spine in ax.spines.values():
                    spine.set_color("#cadacf")

                lines = []
                for j, name in enumerate(cfg["names"]):
                    color = CHART_COLORS[j % 3]
                    filtered_gyro = cfg["title"].startswith("Giroscopio") and j >= 3
                    line, = ax.plot([], [], color=color,
                                    linestyle="--" if filtered_gyro else "-",
                                    linewidth=1.8 if not filtered_gyro else 1.5,
                                    alpha=0.76 if filtered_gyro else 1.0,
                                    label=name)
                    line.set_animated(True)
                    lines.append(line)
                ax.legend(loc="upper right", ncol=3 if len(lines) > 3 else len(lines),
                          fontsize=8, frameon=True, facecolor="#ffffff", edgecolor="#dbe7de",
                          framealpha=0.96, borderpad=0.6, handlelength=2.0)
                self.plot_artists[plot_index] = (ax, lines, canvas)
            for unused_axis in axes[count:]:
                figure.delaxes(unused_axis)
            self.plot_tabs.addTab(page, tab_title)
            canvas.mpl_connect(
                "draw_event",
                lambda event, indexes=plot_indexes: self._cache_plot_backgrounds(event, indexes),
            )
        layout.addWidget(self.plot_tabs, 1)

        self.b_ref.clicked.connect(self._ref)
        self.b_con.clicked.connect(self._con)
        self.b_plot.clicked.connect(self._do_plot)
        self.b_stop.clicked.connect(lambda: self.R.send("pause"))
        self.b_3d.clicked.connect(self._show_3d)
        self.plot_tabs.currentChanged.connect(self._draw_active_plot)
        self._ref()

    def _show_3d(self):
        self.viewer3d.show()
        self.viewer3d.raise_()
        self.viewer3d.activateWindow()
        if self._latest_last is not None:
            self._update_3d(self._latest_last)

    def _draw_active_plot(self, *_):
        self._refresh_active_plot(force=True)

    def _cache_plot_backgrounds(self, event, plot_indexes):
        canvas = event.canvas
        for plot_index in plot_indexes:
            ax, lines, _canvas = self.plot_artists[plot_index]
            self._plot_backgrounds[plot_index] = canvas.copy_from_bbox(ax.bbox)
        QtCore.QTimer.singleShot(0, lambda indexes=plot_indexes: self._paint_plot_lines(indexes))

    def _paint_plot_lines(self, plot_indexes):
        active_indexes = PLOT_GROUPS[self.plot_tabs.currentIndex()][1]
        if not all(index in active_indexes and index in self._plot_backgrounds for index in plot_indexes):
            return
        canvas = self.plot_canvases[self.plot_tabs.currentIndex()]
        for plot_index in plot_indexes:
            ax, lines, _canvas = self.plot_artists[plot_index]
            canvas.restore_region(self._plot_backgrounds[plot_index])
            for line in lines:
                ax.draw_artist(line)
        canvas.blit()

    @staticmethod
    def _decimate_for_display(x, values, max_points=600):
        """Keep each channel's local minima and maxima within a point budget."""
        count, channels = values.shape
        if count <= max_points or channels == 0:
            return x, values
        target_bins = max(1, max_points // (2 * channels))
        chunk = int(math.ceil(count / target_bins))
        bins = int(math.ceil(count / chunk))
        padded_count = bins * chunk
        padded = np.full((padded_count, channels), np.nan, dtype=np.float32)
        padded[:count] = values
        blocks = padded.reshape(bins, chunk, channels)
        low = np.nanargmin(blocks, axis=1)
        high = np.nanargmax(blocks, axis=1)
        offsets = np.arange(bins, dtype=np.int64)[:, None] * chunk
        indices = np.unique(np.concatenate((
            (offsets + low).ravel(), (offsets + high).ravel()
        )))
        indices = indices[indices < count]
        return x[indices], values[indices]

    def _refresh_active_plot(self, force=False):
        if self._latest_data is None or self._latest_times is None:
            return
        now = time.monotonic()
        if not force and now - self._last_plot_draw < 1 / 20:
            return
        active_indexes = PLOT_GROUPS[self.plot_tabs.currentIndex()][1]
        for plot_index in active_indexes:
            ax, lines, _canvas = self.plot_artists[plot_index]
            cfg = PLOT_CFG[plot_index]
            values = self._latest_data[:, cfg["cols"]]
            x_plot, values_plot = self._decimate_for_display(self._latest_times, values)
            for j, line in enumerate(lines):
                line.set_data(x_plot, values_plot[:, j])
        canvas = self.plot_canvases[self.plot_tabs.currentIndex()]
        can_blit = canvas.supports_blit and all(
            plot_index in self._plot_backgrounds for plot_index in active_indexes
        )
        if can_blit and not force:
            for plot_index in active_indexes:
                ax, lines, _canvas = self.plot_artists[plot_index]
                canvas.restore_region(self._plot_backgrounds[plot_index])
                for line in lines:
                    ax.draw_artist(line)
            canvas.blit()
        else:
            canvas.draw_idle()
        self._last_plot_draw = now

    def _update_3d(self, last):
        p, r = last[24], last[25]
        self.viewer3d.rot_comp.transform.matrix = demo_orientation_matrix(p, r)
        self.viewer3d._update_accel_vector(self.viewer3d.accel_comp, last[0:3])
        mp, mr = last[26], last[27]
        self.viewer3d.rot_madg.transform.matrix = demo_orientation_matrix(mp, mr)
        self.viewer3d._update_accel_vector(self.viewer3d.accel_madg, last[0:3])
        self.viewer3d.update_metrics(last)
        self.viewer3d.canvas.update()

    def _do_plot(self):
        self.R.send("plot")
        QtCore.QTimer.singleShot(100, lambda: self.R.send("run"))

    def _ref(self):
        self.cb_p.clear()
        for p in self.R.ports():
            self.cb_p.addItem(p)

    def _con(self):
        if not self.R.on:
            port = self.cb_p.currentText()
            if not port:
                return
            ok, msg = self.R.connect(port)
            self.lbl_s.setText(msg)
            self._set_connection_ui(ok, msg)
            if ok:
                self.b_con.setText("Desconectar")
                self.b_con.setStyleSheet("background:#c0392b;")
        else:
            self.R.disconnect()
            self.lbl_s.setText("Desconectado")
            self._set_connection_ui(False, "Desconectado")
            self.b_con.setText("Conectar")
            self.b_con.setStyleSheet("background:#27ae60;")

    def _set_connection_ui(self, connected, message):
        if connected:
            self.live_labels["connection"].setText("Conectado")
            self.live_labels["connection"].setStyleSheet(
                "color:#124b31; background:#bde8ce; padding:7px 12px; border-radius:9px; font-weight:800;"
            )
            self.lbl_s.setText(message)
        else:
            self.live_labels["connection"].setText("Desconectado")
            self.live_labels["connection"].setStyleSheet(
                "color:#7d3b31; background:#f7e5df; padding:7px 12px; border-radius:9px; font-weight:700;"
            )

    def _update(self):
        vals, ts, last, frame_count, fps = self.R.get_data(self._last_frame_seen)
        if not vals or last is None:
            return
        self._last_frame_seen = frame_count
        if frame_count == 1:
            print(f"[_update] Primer frame con {len(vals)} muestras, last={last[:4]}")

        p, r = last[24], last[25]
        mp, mr = last[26], last[27]

        a = np.asarray(vals, dtype=np.float32)
        tx = np.asarray(ts, dtype=np.float64) - float(ts[-1]) + WINDOW_SEC

        if len(tx) > 1 and tx[0] < 0:
            mask = tx >= 0
            tx = tx[mask]
            a = a[mask]

        self._latest_data = a
        self._latest_times = tx
        self._latest_last = last
        self._refresh_active_plot()

        self.live_labels["angles"].setText(
            f"COMPLEMENTARIO  Pitch {p:+.2f}°  Roll {r:+.2f}°   |   "
            f"MADGWICK  Pitch {mp:+.2f}°  Roll {mr:+.2f}°"
        )
        self.live_labels["perf"].setText(
            f"Entrada {fps:4.0f} Hz  ·  Muestras {frame_count:5d}  ·  "
            f"Buffer {len(vals):4d}  ·  Ventana {WINDOW_SEC:.0f} s"
        )
        if self.viewer3d.isVisible():
            self._update_3d(last)


def main():
    app.use_app("pyqt5")
    qa = QtWidgets.QApplication(sys.argv)
    w = IMUWindow()
    w.showMaximized()
    sys.exit(qa.exec_())


if __name__ == "__main__":
    main()
