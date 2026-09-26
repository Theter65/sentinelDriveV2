"""
SENTNLDRIVE - IMU 3D Viewer (VisPy GPU)
OpenGL real-time @ 100Hz - Ventana 10s - Labels & Stats
"""
import sys, serial, serial.tools.list_ports, threading, time, collections, math
import numpy as np
from vispy import scene, app
from vispy.visuals.transforms import MatrixTransform
from PyQt5 import QtCore, QtWidgets, QtGui

BAUD, NCOLS, BUFFER = 115200, 28, 2000
CR, CG, CB, CY = (0.91, 0.30, 0.24, 1), (0.18, 0.80, 0.44, 1), (0.20, 0.60, 0.86, 1), (0.95, 0.77, 0.06, 1)
CC = (0.6, 0.6, 0.6, 1)
BG = (0.059, 0.059, 0.137, 1)
WINDOW_SEC = 10.0
PANEL_BG = "#15182b"
PANEL_BORDER = "#2c3558"
TEXT_MAIN = "#e8ecff"
TEXT_MUTED = "#98a2c4"
TEXT_ACCENT = "#74c0fc"
TEXT_OK = "#34d399"
TEXT_WARN = "#f59e0b"
TEXT_BAD = "#ef4444"

PLOT_CFG = [
    {"title": "Aceleracion normal", "unit": "m/s2", "cols": (3, 4, 5), "names": ("ax", "ay", "az"), "ylim": (-15, 15), "yticks": (-10, 0, 10)},
    {"title": "Gravedad COMP", "unit": "m/s2", "cols": (9, 10, 11), "names": ("gX", "gY", "gZ"), "ylim": (-12, 12), "yticks": (-9.81, 0, 9.81)},
    {"title": "Acel. s/gravedad COMP", "unit": "m/s2", "cols": (6, 7, 8), "names": ("compX", "compY", "compZ"), "ylim": (-8, 8), "yticks": (-4, 0, 4)},
    {"title": "Gravedad MADG", "unit": "m/s2", "cols": (15, 16, 17), "names": ("gX", "gY", "gZ"), "ylim": (-12, 12), "yticks": (-9.81, 0, 9.81)},
    {"title": "Acel. s/gravedad MADG", "unit": "m/s2", "cols": (12, 13, 14), "names": ("madgX", "madgY", "madgZ"), "ylim": (-8, 8), "yticks": (-4, 0, 4)},
    {"title": "Giroscopio", "unit": "deg/s", "cols": (18, 19, 20), "names": ("gx", "gy", "gz"), "ylim": (-50, 50), "yticks": (-50, 0, 50)},
    {"title": "Pitch / Roll COMP", "unit": "deg", "cols": (24, 25), "names": ("Pitch", "Roll"), "ylim": (-60, 60), "yticks": (-50, 0, 50)},
    {"title": "Pitch / Roll MADG", "unit": "deg", "cols": (26, 27), "names": ("Pitch", "Roll"), "ylim": (-60, 60), "yticks": (-50, 0, 50)},
]
PLOT_COLORS = [CR, CG, CB]


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
            self._s = serial.Serial(port, BAUD, timeout=1, exclusive=True)
            time.sleep(2)
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

    def get_data(self):
        with self._lk:
            if not self.buf:
                return None, None, self.last
            vals = list(self.buf)
            ts = list(self.tbuf)
            last = self.last
        return vals, ts, last


class Viewer3D(QtWidgets.QMainWindow):
    """Ventana con las dos cajas 3D (COMP y MADG) + panel de metricas debajo."""

    def __init__(self, reader):
        super().__init__()
        self.R = reader
        self.metric_labels = {}
        self.setWindowTitle("SENTNLDRIVE - 3D + Metricas")
        self.resize(1100, 680)
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

        # --- Canvas con vistas 3D ---
        self.canvas = scene.SceneCanvas(keys="interactive", bgcolor=BG)
        self.canvas.native.setMinimumHeight(360)
        lay.addWidget(self.canvas.native, 3)

        g = self.canvas.central_widget.add_grid(spacing=8, margin=4)

        self.v3_comp = g.add_view(row=0, col=0)
        self.v3_comp.camera = "turntable"
        self.v3_comp.camera.fov = 32
        self.v3_comp.camera.distance = 55
        self.v3_comp.camera.elevation = 20
        self.v3_comp.camera.azimuth = -45
        self.v3_comp.border_color = (0.2, 0.7, 0.2, 0.6)
        self.rot_comp = self._setup_3d(self.v3_comp, (0.15, 0.8, 0.15, 0.35))

        self.v3_madg = g.add_view(row=0, col=1)
        self.v3_madg.camera = "turntable"
        self.v3_madg.camera.fov = 32
        self.v3_madg.camera.distance = 55
        self.v3_madg.camera.elevation = 20
        self.v3_madg.camera.azimuth = -45
        self.v3_madg.border_color = (0.2, 0.4, 0.8, 0.6)
        self.rot_madg = self._setup_3d(self.v3_madg, (0.15, 0.5, 1.0, 0.35))

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
        stats_hint = QtWidgets.QLabel("28 col: RAW | Filt | LinCOMP | GravCOMP | LinMADG | GravMADG | GyroRAW | GyroFilt | COMP_PR | MADG_PR")
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

    def _fmt(self, value):
        return f"{value:+.3f}"

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
        l, w, h = 5, 10, 2
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
        scene.visuals.Line(pos=ev, color=edge_color, width=1, parent=parent_view.scene)

        rot = scene.Node(parent=parent_view.scene)
        box_mesh.parent = rot
        scene.visuals.Line(pos=ev, color=edge_color, width=1, parent=rot)
        md = 10
        for pts, cl, lb in [([0, 0, 0, md, 0, 0], CR, "X"), ([0, 0, 0, 0, md, 0], CG, "Y"),
                            ([0, 0, 0, 0, 0, -md], CB, "Z")]:
            pa = np.array(pts, dtype=np.float32).reshape(2, 3)
            scene.visuals.Line(pos=pa, color=cl, width=3, parent=rot)
            scene.visuals.Text(lb, pos=pa[1], color=cl, font_size=14, parent=rot)
        scene.visuals.Markers(pos=np.zeros((1, 3)), size=6, face_color=(1, 0.75, 0, 1),
                              parent=parent_view.scene)
        rot.transform = MatrixTransform()
        return rot


class IMUWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.R = SerialReader()
        self.live_labels = {}
        self.viewer3d = Viewer3D(self.R)
        self._setup_ui()
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._update)
        self._timer.start(16)

    def closeEvent(self, event):
        # Cerrar tambien la ventana 3D cuando se cierra la principal
        self.viewer3d.close()
        super().closeEvent(event)

    def _setup_ui(self):
        self.setWindowTitle("SENTNLDRIVE - IMU Viewer (VisPy OpenGL)")
        self.resize(1900, 1000)
        self.setStyleSheet("""
            QMainWindow {background: #0f0f23;}
            QToolBar {
                background: #14192d;
                spacing: 6px;
                padding: 6px;
                border-bottom: 1px solid #2a2f4a;
            }
            QPushButton {
                padding: 6px 14px;
                border: none;
                border-radius: 5px;
                font-weight: 700;
                color: white;
            }
            QComboBox {
                background: #1a1f36;
                color: #f1f5ff;
                padding: 5px 10px;
                border: 1px solid #2c3558;
                border-radius: 4px;
            }
            QLabel {color: #aab3d1; font-size: 12px;}
            QFrame#InfoCard, QFrame#StatsCard {
                background: #15182b;
                border: 1px solid #2c3558;
                border-radius: 10px;
            }
        """)
        tb = self.addToolBar("Control")
        tb.setMovable(False)
        tb.addWidget(QtWidgets.QLabel("  Puerto:"))
        self.cb_p = QtWidgets.QComboBox()
        self.cb_p.setMinimumWidth(130)
        tb.addWidget(self.cb_p)
        self.b_ref = QtWidgets.QPushButton("Refrescar")
        self.b_ref.setStyleSheet("background:#7f8c8d;")
        tb.addWidget(self.b_ref)
        self.b_con = QtWidgets.QPushButton("Conectar")
        self.b_con.setStyleSheet("background:#27ae60;")
        tb.addWidget(self.b_con)
        self.b_plot = QtWidgets.QPushButton("Start Plot")
        self.b_plot.setStyleSheet("background:#2980b9;")
        tb.addWidget(self.b_plot)
        self.b_stop = QtWidgets.QPushButton("Stop")
        self.b_stop.setStyleSheet("background:#8e44ad;")
        tb.addWidget(self.b_stop)
        self.lbl_s = QtWidgets.QLabel("  Desconectado")
        tb.addWidget(self.lbl_s)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        lay = QtWidgets.QVBoxLayout(central)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        self.info_card = QtWidgets.QFrame()
        self.info_card.setObjectName("InfoCard")
        info_layout = QtWidgets.QHBoxLayout(self.info_card)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(18)

        title_box = QtWidgets.QVBoxLayout()
        self.lbl_title = QtWidgets.QLabel("SENTNLDRIVE - IMU Viewer")
        self.lbl_title.setStyleSheet("color: #f4f7ff; font-size: 18px; font-weight: 800;")
        self.lbl_subtitle = QtWidgets.QLabel("VisPy + PyQt5 | tiempo real por serial")
        self.lbl_subtitle.setStyleSheet("color: #93a0c7; font-size: 12px;")
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_subtitle)
        info_layout.addLayout(title_box, 2)

        self.live_labels["connection"] = QtWidgets.QLabel("Desconectado")
        self.live_labels["connection"].setStyleSheet(
            "color: #f8fafc; background: #7f1d1d; padding: 5px 10px; border-radius: 10px; font-weight: 700;"
        )
        self.live_labels["angles"] = QtWidgets.QLabel("COMP P --.- R --.- | MADG P --.- R --.-")
        self.live_labels["angles"].setStyleSheet("color: #dbe4ff; font-size: 13px; font-weight: 600;")
        self.live_labels["perf"] = QtWidgets.QLabel("FPS -- | Frames -- | Buffer --")
        self.live_labels["perf"].setStyleSheet("color: #a5b4fc; font-size: 12px;")

        meta_box = QtWidgets.QVBoxLayout()
        meta_box.addWidget(self.live_labels["connection"])
        meta_box.addWidget(self.live_labels["angles"])
        meta_box.addWidget(self.live_labels["perf"])
        info_layout.addLayout(meta_box, 2)
        lay.addWidget(self.info_card)

        self.canvas = scene.SceneCanvas(keys="interactive", bgcolor=BG)
        self.canvas.native.setMinimumHeight(760)
        lay.addWidget(self.canvas.native, 1)

        g = self.canvas.central_widget.add_grid(spacing=10, margin=6)

        n_plots = len(PLOT_CFG)
        PLOT_COLS = 2                                  # 2 columnas de graficas
        plot_rows = math.ceil(n_plots / PLOT_COLS)     # -> 4 filas para 7 graficas

        self.v2 = []
        self.lns = []
        self._zero_lines = []
        self._ytick_lines = []
        self.plot_headers = []
        self.plot_axes = []

        for i, cfg in enumerate(PLOT_CFG):
            prow, pcol = divmod(i, PLOT_COLS)          # fila/columna dentro de la grilla 2x4 de graficas
            sub = g.add_grid(row=prow, col=pcol, spacing=3, margin=2)
            header = scene.widgets.Label(
                f"{cfg['title']}  ({cfg['unit']})",
                color=(0.95, 0.97, 1.0, 1),
                font_size=11,
            )
            header.stretch = (24, 0.6)                  # un poco mas de alto reservado para el titulo
            sub.add_widget(header, row=0, col=0, col_span=2)
            self.plot_headers.append(header)

            left_axis = scene.widgets.AxisWidget(
                orientation="left",
                axis_color=(0.55, 0.62, 0.9, 1),
                tick_color=(0.55, 0.62, 0.9, 1),
                text_color=(0.9, 0.93, 1.0, 1),
                axis_label="",
                axis_font_size=9,
                tick_font_size=9,
                tick_label_margin=8,
                axis_label_margin=0,
                tick_width=1.4,
                axis_width=2,
            )
            left_axis.stretch = (0.42, 20)
            sub.add_widget(left_axis, row=1, col=0)

            bottom_axis = scene.widgets.AxisWidget(
                orientation="bottom",
                axis_color=(0.55, 0.62, 0.9, 1),
                tick_color=(0.55, 0.62, 0.9, 1),
                text_color=(0.9, 0.93, 1.0, 1),
                axis_label="t [s]",
                axis_font_size=9,
                tick_font_size=9,
                tick_label_margin=6,
                axis_label_margin=8,
                tick_width=1.4,
                axis_width=2,
            )
            bottom_axis.stretch = (24, 0.55)

            vb = sub.add_view(row=1, col=1)
            sub.add_widget(bottom_axis, row=2, col=1)
            vb.stretch = (24, 20)
            vb.camera = "panzoom"
            ymin, ymax = cfg["ylim"]
            vb.camera.rect = (0, ymin, 5, ymax - ymin)
            vb.border_color = (0.3, 0.3, 0.5, 0.4)
            self.v2.append(vb)
            left_axis.link_view(vb)
            bottom_axis.link_view(vb)
            self.plot_axes.append((left_axis, bottom_axis))

            nc = len(cfg["names"])
            colors = PLOT_COLORS[:nc] if nc == 3 else [CR, CB]
            ls = []
            for j in range(nc):
                ln = scene.visuals.Line(pos=np.zeros((1, 2)), color=colors[j], width=2.0, parent=vb.scene)
                ls.append(ln)
            self.lns.append(ls)

            zero = scene.visuals.Line(
                pos=np.array([[-100, 0], [200, 0]], dtype=np.float32),
                color=(0.4, 0.4, 0.4, 0.5), width=1, parent=vb.scene)
            self._zero_lines.append(zero)

            tick_lines = []
            for tick in cfg.get("yticks", ()):
                line = scene.visuals.Line(
                    pos=np.array([[-100, tick], [200, tick]], dtype=np.float32),
                    color=(0.22, 0.24, 0.38, 0.45),
                    width=1,
                    parent=vb.scene,
                )
                tick_lines.append(line)
            self._ytick_lines.append(tick_lines)

        self.b_ref.clicked.connect(self._ref)
        self.b_con.clicked.connect(self._con)
        self.b_plot.clicked.connect(self._do_plot)
        self.b_stop.clicked.connect(lambda: self.R.send("pause"))
        self._ref()

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
                "color: #052e16; background: #86efac; padding: 5px 10px; border-radius: 10px; font-weight: 800;"
            )
            self.lbl_s.setText(message)
        else:
            self.live_labels["connection"].setText("Desconectado")
            self.live_labels["connection"].setStyleSheet(
                "color: #fff1f2; background: #7f1d1d; padding: 5px 10px; border-radius: 10px; font-weight: 700;"
            )

    def _update(self):
        vals, ts, last = self.R.get_data()
        if not vals or last is None:
            # print("[DBG] _update: sin datos")  # descomenta para debug
            return
        if self.R.frame_count == 1:
            print(f"[_update] Primer frame con {len(vals)} muestras, last={last[:4]}")

        p, r = last[24], last[25]
        pr, rr = math.radians(p), math.radians(r)
        cp, sp = math.cos(pr), math.sin(pr)
        cr, sr = math.cos(rr), math.sin(rr)
        mat_comp = np.array([
            [cp, 0, sp, 0], [sr * sp, cr, -sr * cp, 0],
            [-cr * sp, sr, cr * cp, 0], [0, 0, 0, 1]
        ], dtype=np.float32)
        self.viewer3d.rot_comp.transform.matrix = mat_comp

        mp, mr = last[26], last[27]
        mpr, mrr = math.radians(mp), math.radians(mr)
        mcp, msp = math.cos(mpr), math.sin(mpr)
        mcr, msr = math.cos(mrr), math.sin(mrr)
        mat_madg = np.array([
            [mcp, 0, msp, 0], [msr * msp, mcr, -msr * mcp, 0],
            [-mcr * msp, msr, mcr * mcp, 0], [0, 0, 0, 1]
        ], dtype=np.float32)
        self.viewer3d.rot_madg.transform.matrix = mat_madg

        a = np.array(vals)
        t0 = ts[0]
        tx = np.array(ts) - t0

        if len(tx) > 1 and (tx[-1] - tx[0]) > WINDOW_SEC:
            cutoff = tx[-1] - WINDOW_SEC
            mask = tx >= cutoff
            tx = tx[mask]
            a = a[mask]

        for i, cfg in enumerate(PLOT_CFG):
            series = a[:, cfg["cols"]]
            nc = series.shape[1]
            for j in range(nc):
                self.lns[i][j].set_data(pos=np.column_stack([tx, series[:, j]]))

        if len(tx) > 1:
            x0 = tx[0]
            spn = max(tx[-1] - x0, 2) * 1.05
            for i, vb in enumerate(self.v2):
                cfg = PLOT_CFG[i]
                ymin, ymax = cfg["ylim"]
                vb.camera.rect = (x0, ymin, spn, ymax - ymin)

            for i, vb in enumerate(self.v2):
                ymin, ymax = PLOT_CFG[i]["ylim"]
                self._zero_lines[i].set_data(pos=np.array([[-100, 0], [x0 + spn * 2, 0]], dtype=np.float32))
                for line, tick in zip(
                    self._ytick_lines[i],
                    PLOT_CFG[i].get("yticks", ()),
                ):
                    line.set_data(pos=np.array([[x0, tick], [x0 + spn, tick]], dtype=np.float32))

        lx, ly, lz = last[6], last[7], last[8]
        gx, gy, gz = last[21], last[22], last[23]

        self.live_labels["angles"].setText(f"COMP P {p:+6.2f} R {r:+6.2f}  |  MADG P {mp:+6.2f} R {mr:+6.2f}")
        self.live_labels["perf"].setText(
            f"FPS {self.R.fps:4.0f} | Frames {self.R.frame_count:5d} | Buffer {len(vals):4d} | Window {WINDOW_SEC:.0f}s"
        )
        self.viewer3d.update_metrics(last)

        self.canvas.update()
        self.viewer3d.canvas.update()


def main():
    app.use_app("pyqt5")
    qa = QtWidgets.QApplication(sys.argv)
    w = IMUWindow()
    w.show()
    qa.processEvents()                    # Forzar layout antes de medir geometria

    # Ubicar la ventana 3D a la derecha de la principal
    screen = qa.primaryScreen().availableGeometry()
    mg = w.frameGeometry()
    v3d = w.viewer3d

    x = mg.x() + mg.width() + 10
    y = mg.y()

    # Si no cabe a la derecha, poner debajo
    if x + v3d.width() > screen.x() + screen.width():
        x = mg.x()
        y = mg.y() + mg.height() + 10

    # Asegurar que entra en pantalla
    if x + v3d.width() > screen.x() + screen.width():
        x = screen.x() + screen.width() - v3d.width()
    if y + v3d.height() > screen.y() + screen.height():
        y = screen.y() + screen.height() - v3d.height()
    if x < screen.x(): x = screen.x()
    if y < screen.y(): y = screen.y()

    v3d.move(x, y)
    v3d.show()
    sys.exit(qa.exec_())


if __name__ == "__main__":
    main()
