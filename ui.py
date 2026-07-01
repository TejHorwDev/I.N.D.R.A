from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import uuid
import requests
import time
import winreg
import hashlib
from pathlib import Path

import mss
import cv2
import numpy as np
import psutil
from PyQt6.QtCore import (QPropertyAnimation, QEasingCurve, QMimeData, QMetaObject, Q_ARG, QObject, QPointF, QPoint, QRectF, QRect,
                          QSize, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot, QParallelAnimationGroup, QThread)
from PyQt6.QtGui import (QBrush, QColor, QDragEnterEvent, QDropEvent, QFont,
                         QFontDatabase, QKeySequence, QLinearGradient,
                         QPainter, QPainterPath, QPen, QPixmap,
                         QRadialGradient, QShortcut, QImage, QIcon, QAction)
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QMainWindow, QProgressBar,
                             QPushButton, QScrollArea, QSizePolicy, QTextEdit,
                             QVBoxLayout, QWidget, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
                             QSystemTrayIcon, QMenu, QTextBrowser)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

def _base_dir() -> Path:
    """Read-only bundled assets directory."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _user_data_dir() -> Path:
    """Writable persistent user-data directory."""
    if getattr(sys, "frozen", False):
        appdata = Path(os.environ.get("APPDATA", Path.home()))
        user_dir = appdata / "INDRA"
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
USER_DIR = _user_data_dir()
CONFIG_DIR = USER_DIR / "config"
API_FILE = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W, _MIN_H = 820, 580
_LEFT_W = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG = "#0A0A0A"          # Deep obsidian background
    PANEL = "#111111"       # Slightly lighter for panels
    PANEL2 = "#1A1A1A"      # For hover/active states
    BORDER = "#2A2A2A"      # Subtle grey borders
    BORDER_B = "#333333"
    BORDER_A = "#404040"
    PRI = "#6366F1"         # Premium indigo accent
    PRI_DIM = "#4338CA"
    PRI_GHO = "#1E1B4B"
    ACC = "#3B82F6"         # Premium blue accent
    ACC2 = "#8B5CF6"        # Premium violet accent
    GREEN = "#10B981"       # Emerald green
    GREEN_D = "#059669"
    RED = "#EF4444"
    MUTED_C = "#6B7280"
    TEXT = "#F9FAFB"        # Crisp white text
    TEXT_DIM = "#6B7280"    # Muted grey text
    TEXT_MED = "#9CA3AF"    # Medium grey text
    WHITE = "#FFFFFF"
    DARK = "#050505"
    BAR_BG = "#1F2937"      # Progress bar background


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(a)
    return c


class _SysMetrics:
    def __init__(self):
        self.cpu = 0.0
        self.mem = 0.0
        self.net = 0.0
        self.gpu = -1.0
        self.tmp = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc = psutil.net_io_counters()
        now = time.time()
        dt = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if r.returncode == 0:
                vals = [
                    float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()
                ]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux)
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            # Intel GPU (Linux)
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re

                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # macOS — powermetrics (GPU Engine)
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    [
                        "sudo",
                        "-n",
                        "powermetrics",
                        "-n",
                        "1",
                        "-i",
                        "500",
                        "--samplers",
                        "gpu_power",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re

                    m = re.search(r"GPU\s+Active:\s+([\d.]+)%", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = [
                "coretemp",
                "k10temp",
                "cpu_thermal",
                "acpitz",
                "cpu-thermal",
                "zenpower",
                "it8688",
            ]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re

                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()


class HudCanvas(QWidget):
    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted = False
        self.speaking = False
        self.state = "INITIALISING"

        self._tick = 0
        self._scale = 1.0
        self._tgt_scale = 1.0
        self._halo = 55.0
        self._tgt_halo = 55.0
        self._last_t = time.time()
        self._scan = 0.0
        self._scan2 = 180.0
        self._rings = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def _load_face(self, path: str):
        try:
            import io

            from PIL import Image, ImageDraw

            img = Image.open(path).convert("RGBA")
            sz = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()
        if now - self._last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = random.uniform(0.998, 1.002)
                self._tgt_halo = random.uniform(15, 28)
            else:
                self._tgt_scale = random.uniform(1.001, 1.008)
                self._tgt_halo = random.uniform(48, 68)
            self._last_t = now

        sp = 0.38 if self.speaking else 0.15
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo += (self._tgt_halo - self._halo) * sp

        speeds = [1.3, -0.9, 2.0] if self.speaking else [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan = (self._scan + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        fw = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 3 and random.random() < (
            0.07 if self.speaking else 0.025
        ):
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append(
                [
                    cx + math.cos(ang) * r_s,
                    cy + math.sin(ang) * r_s,
                    math.cos(ang) * random.uniform(0.9, 2.4),
                    math.sin(ang) * random.uniform(0.9, 2.4) - 0.4,
                    1.0,
                ]
            )
        self._particles = [
            [p[0] + p[2], p[1] + p[3], p[2] * 0.97, p[3] * 0.97, p[4] - 0.028]
            for p in self._particles
            if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # grid dots
        p.setPen(QPen(qcol(C.PRI_GHO), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                p.drawPoint(x, y)

        r_face = fw * 0.31

        # halo glow
        for i in range(10):
            r = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a = max(0, min(255, int(self._halo * 0.085 * frc)))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # pulse rings
        for pr in self._pulses:
            a = max(0, int(230 * (1.0 - pr / (fw * 0.74))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a)
            p.setPen(QPen(col, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings
        for idx, (r_frac, w_r, arc_l, gap) in enumerate(
            [(0.48, 3, 115, 78), (0.40, 2, 78, 55), (0.32, 1, 56, 40)]
        ):
            ring_r = fw * r_frac
            base = self._rings[idx]
            a_val = max(0, min(255, int(self._halo * (1.0 - idx * 0.18))))
            col = qcol(C.MUTED_C if self.muted else C.PRI, a_val)
            p.setPen(QPen(col, w_r))
            p.setBrush(Qt.BrushStyle.NoBrush)
            angle = base
            rect = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            while angle < base + 360:
                p.drawArc(rect, int(angle * 16), int(arc_l * 16))
                angle += arc_l + gap

        # scanners
        sr = fw * 0.50
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if self.speaking else 44
        p.setPen(QPen(qcol(C.MUTED_C if self.muted else C.PRI, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        # tick marks
        t_out, t_in = fw * 0.497, fw * 0.474
        p.setPen(QPen(qcol(C.PRI, 140), 1))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn * math.cos(rad), cy - inn * math.sin(rad)),
            )

        # crosshair
        ch_r, gap_h = fw * 0.51, fw * 0.16
        p.setPen(QPen(qcol(C.PRI, int(self._halo * 0.5)), 1))
        p.drawLine(QPointF(cx - ch_r, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch_r, cy))
        p.drawLine(QPointF(cx, cy - ch_r), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch_r))

        # corner brackets
        bl = 24
        bc = qcol(C.PRI, 210)
        hl, hr = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(bc, 2))
        for bx, by, dx, dy in [
            (hl, ht, 1, 1),
            (hr, ht, -1, 1),
            (hl, hb, 1, -1),
            (hr, hb, -1, -1),
        ]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # face
        if self._face_px:
            fsz = int(fw * 0.62 * self._scale)
            scaled = self._face_px.scaled(
                fsz,
                fsz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(cx - fsz / 2), int(cy - fsz / 2), scaled)
        else:
            orb_r = int(fw * 0.27 * self._scale)
            oc = (200, 0, 50) if self.muted else (0, 60, 110)
            for i in range(8, 0, -1):
                r2 = int(orb_r * i / 8)
                frc = i / 8
                a = max(0, min(255, int(self._halo * 1.1 * frc)))
                p.setBrush(
                    QBrush(
                        QColor(int(oc[0] * frc), int(oc[1] * frc), int(oc[2] * frc), a)
                    )
                )
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2))
            p.setPen(QPen(qcol(C.PRI, min(255, int(self._halo * 2))), 1))
            p.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
            p.drawText(
                QRectF(cx - 80, cy - 14, 160, 28),
                Qt.AlignmentFlag.AlignCenter,
                "I.N.D.R.A",
            )

        # particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # status text
        sy = cy + fw * 0.40
        if self.muted:
            txt, col = "⊘  MUTED", qcol(C.MUTED_C)
        elif self.speaking:
            txt, col = "●  SPEAKING", qcol(C.ACC)
        elif self.state == "THINKING":
            sym = "◈" if self._blink else "◇"
            txt, col = f"{sym}  THINKING", qcol(C.ACC2)
        elif self.state == "PROCESSING":
            sym = "▷" if self._blink else "▶"
            txt, col = f"{sym}  PROCESSING", qcol(C.ACC2)
        elif self.state == "LISTENING":
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  LISTENING", qcol(C.GREEN)
        else:
            sym = "●" if self._blink else "○"
            txt, col = f"{sym}  {self.state}", qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        # waveform
        wy = sy + 30
        N, bw = 36, 8
        wx0 = (W - N * bw) / 2
        for i in range(N):
            if self.muted:
                hgt, cl = 2, qcol(C.MUTED_C)
            elif self.speaking:
                hgt = random.randint(3, 20)
                cl = qcol(C.PRI) if hgt > 12 else qcol(C.PRI_DIM)
            else:
                hgt = int(3 + 2 * math.sin(self._tick * 0.09 + i * 0.6))
                cl = qcol(C.BORDER_B)
            p.fillRect(QRectF(wx0 + i * bw, wy + 20 - hgt, bw - 1, hgt), cl)


class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0  # 0–100
        self._text = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h = 4
        bar_y = H - bar_h - 5
        bar_w = W - 12
        bar_x = 6
        fill_w = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(
            QRectF(8, 5, 50, 14),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._label,
        )

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(
            QRectF(0, 4, W - 6, 16),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._text,
        )


class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing = False
        self._text = ""
        self._pos = 0
        self._tag = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text = self._queue.pop(0)
        self._pos = 0
        tl = self._text.lower()
        if tl.startswith("you:"):
            self._tag = "you"
        elif tl.startswith("INDRA:"):
            self._tag = "ai"
        elif tl.startswith("file:"):
            self._tag = "file"
        elif "err" in tl:
            self._tag = "err"
        else:
            self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you": qcol(C.WHITE),
                "ai": qcol(C.PRI),
                "err": qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys": qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)


_FILE_ICONS = {
    "image": ("🖼", "#00d4ff"),
    "video": ("🎬", "#ff6b00"),
    "audio": ("🎵", "#cc44ff"),
    "pdf": ("📄", "#ff4444"),
    "word": ("📝", "#4488ff"),
    "excel": ("📊", "#44bb44"),
    "code": ("💻", "#ffcc00"),
    "archive": ("📦", "#ff8844"),
    "pptx": ("📊", "#ff6622"),
    "text": ("📃", "#aaaaaa"),
    "data": ("🔧", "#88ddff"),
    "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(
        ["jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "svg", "ico"], "image"
    ),
    **dict.fromkeys(["mp4", "avi", "mov", "mkv", "wmv", "flv", "webm", "m4v"], "video"),
    **dict.fromkeys(
        ["mp3", "wav", "ogg", "m4a", "aac", "flac", "wma", "opus"], "audio"
    ),
    **dict.fromkeys(["pdf"], "pdf"),
    **dict.fromkeys(["doc", "docx"], "word"),
    **dict.fromkeys(["xls", "xlsx", "ods"], "excel"),
    **dict.fromkeys(["ppt", "pptx"], "pptx"),
    **dict.fromkeys(
        [
            "py",
            "js",
            "ts",
            "jsx",
            "tsx",
            "html",
            "css",
            "java",
            "c",
            "cpp",
            "cs",
            "go",
            "rs",
            "rb",
            "php",
            "swift",
            "kt",
            "sh",
            "sql",
            "lua",
        ],
        "code",
    ),
    **dict.fromkeys(["zip", "rar", "tar", "gz", "7z", "bz2", "xz"], "archive"),
    **dict.fromkeys(["txt", "md", "rst", "log"], "text"),
    **dict.fromkeys(["csv", "tsv", "json", "xml"], "data"),
}


def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024**2:
        return f"{size/1024:.1f} KB"
    elif size < 1024**3:
        return f"{size/1024**2:.1f} MB"
    else:
        return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True
            self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False
        self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True
        self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False
        self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file for INDRA",
            str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z = self._z
        W, H = self.width(), self.height()
        pad = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol(
            "#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL)
        )
        p.setBrush(QBrush(bg_col))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:
            border_col = qcol(C.GREEN, 200)
        elif z._drag_over:
            border_col = qcol(C.PRI, 230)
        elif z._hovering:
            border_col = qcol(C.BORDER_B, 200)
        else:
            border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:
            self._paint_file(p, W, H)
        elif z._drag_over:
            self._paint_drag_over(p, W, H)
        else:
            self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(
            QRectF(0, cy + 8, W, 16),
            Qt.AlignmentFlag.AlignCenter,
            "Drop file here  or  Click to Browse",
        )
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(
            QRectF(0, cy + 24, W, 14),
            Qt.AlignmentFlag.AlignCenter,
            "Images · Video · Audio · PDF · Docs · Code · Data",
        )

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(
            QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load"
        )

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(
            QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22)
        )
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(
            QRectF(tx, H * 0.18, tw, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(
            QRectF(tx, H * 0.18 + 18, tw, 14),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{ext_str}  ·  {size_str}",
        )

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42:
            par = "…" + par[-41:]
        p.drawText(
            QRectF(tx, H * 0.18 + 34, tw, 12),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            par,
        )

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)

def get_hwid() -> str:
    raw = f"{platform.node()}-{platform.machine()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest().upper()[:8]

def validate_license_key(key: str) -> bool:
    if not key: return False
    
    # Load config
    try:
        with open("firebase_config.json", "r") as f:
            config = json.load(f)
            db_url = config.get("FIREBASE_DATABASE_URL", "").rstrip("/")
            secret = config.get("FIREBASE_SECRET", "")
            if not db_url or "YOUR-PROJECT-ID" in db_url:
                return False
    except Exception:
        return False
        
    url = f"{db_url}/licenses/{key}.json"
    if secret:
        url += f"?auth={secret}"
        
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200 or not response.json():
            return False
            
        data = response.json()
        if data.get("status") != "active":
            return False
            
        hwid = get_hwid()
        saved_hwid = data.get("hwid", "")
        
        if not saved_hwid:
            requests.patch(url, json={"hwid": hwid}, timeout=5)
            return True
            
        return saved_hwid == hwid
        
    except Exception as e:
        print(f"[Licensing] Error connecting to Firebase: {e}")
        return False

class SetupOverlay(QFrame):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("setupOverlay")
        self.setStyleSheet("""
            #setupOverlay {
                background: #030305;
            }
        """)
        
        self.dialog = QFrame(self)
        self.dialog.setObjectName("setupDialog")
        self.dialog.setFixedWidth(460)
        self.dialog.setMinimumHeight(540)
        self.dialog.setStyleSheet("""
            QFrame#setupDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(28, 28, 35, 255), stop:1 rgba(15, 15, 18, 255));
                border: 1px solid rgba(255, 255, 255, 15);
                border-top: 1px solid rgba(255, 255, 255, 30);
                border-radius: 24px;
            }
        """)

        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(60)
        glow.setColor(QColor(168, 85, 247, 40))
        glow.setOffset(0, 0)
        self.dialog.setGraphicsEffect(glow)

        layout = QVBoxLayout(self.dialog)
        layout.setContentsMargins(40, 44, 40, 44)
        layout.setSpacing(16)

        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lbl.setStyleSheet("background: transparent; border: none;")
        logo_path = BASE_DIR / "logo" / "logo.png"
        pix = QPixmap(str(logo_path))
        if not pix.isNull():
            pix = pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
        else:
            logo_lbl.setText("◈")
            logo_lbl.setStyleSheet("color: #a855f7; font-size: 42px; background: transparent; border: none;")
        
        logo_lay = QHBoxLayout()
        logo_lay.addWidget(logo_lbl)
        layout.addLayout(logo_lay)
        layout.addSpacing(10)

        def _lbl(txt, font_size=11, bold=False, color="#ffffff", align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Inter", font_size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            return w

        layout.addWidget(_lbl("System Initialization", 20, True, "#f8fafc"))
        layout.addWidget(_lbl("Authenticate to boot I.N.D.R.A.", 11, False, "#94a3b8"))
        layout.addSpacing(20)

        layout.addWidget(_lbl("API KEY", 9, True, "#94a3b8", Qt.AlignmentFlag.AlignLeft))

        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Enter Gemini Token")
        self._key_input.setFont(QFont("JetBrains Mono", 11))
        self._key_input.setFixedHeight(50)
        self._key_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 100);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 10);
                border-bottom: 1px solid rgba(255, 255, 255, 25);
                border-radius: 12px;
                padding: 4px 20px;
            }
            QLineEdit:focus {
                border: 1px solid #a855f7;
                background: rgba(168, 85, 247, 20);
            }
        """)
        layout.addWidget(self._key_input)
        
        hint_lay1 = QHBoxLayout()
        hint_lay1.setContentsMargins(4, 0, 4, 0)
        get_key_lbl = QLabel('<a href="https://aistudio.google.com/app/apikey" style="color: #a855f7; text-decoration: none; font-weight: bold;">Get a key &rarr;</a>')
        get_key_lbl.setFont(QFont("Inter", 9))
        get_key_lbl.setStyleSheet("background: transparent; border: none;")
        get_key_lbl.setOpenExternalLinks(True)
        get_key_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        hint_lay1.addStretch()
        hint_lay1.addWidget(get_key_lbl)
        layout.addLayout(hint_lay1)

        layout.addSpacing(16)
        
        layout.addWidget(_lbl("LICENSE KEY", 9, True, "#94a3b8", Qt.AlignmentFlag.AlignLeft))
        
        self._license_input = QLineEdit()
        self._license_input.setPlaceholderText("Enter INDRA License Key (XXXX-XXXX-XXXX-XXXX)")
        self._license_input.setFont(QFont("JetBrains Mono", 11))
        self._license_input.setFixedHeight(50)
        self._license_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 100);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 10);
                border-bottom: 1px solid rgba(255, 255, 255, 25);
                border-radius: 12px;
                padding: 4px 20px;
            }
            QLineEdit:focus {
                border: 1px solid #a855f7;
                background: rgba(168, 85, 247, 20);
            }
        """)
        layout.addWidget(self._license_input)
        
        hint_lay2 = QHBoxLayout()
        hint_lay2.setContentsMargins(4, 0, 4, 0)
        hint_lay2.addWidget(_lbl("Stored locally in secure vault.", 9, False, "#64748b", Qt.AlignmentFlag.AlignLeft))
        layout.addLayout(hint_lay2)
        
        layout.addSpacing(30)

        init_btn = QPushButton("Initialize System")
        init_btn.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        init_btn.setFixedHeight(52)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a855f7, stop:1 #7e22ce);
                color: #ffffff;
                border: none;
                border-radius: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #c084fc, stop:1 #9333ea);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9333ea, stop:1 #6b21a8);
            }
        """)
        
        btn_glow = QGraphicsDropShadowEffect(init_btn)
        btn_glow.setBlurRadius(30)
        btn_glow.setColor(QColor(168, 85, 247, 100))
        btn_glow.setOffset(0, 4)
        init_btn.setGraphicsEffect(btn_glow)
        
        layout.addWidget(init_btn)
        init_btn.clicked.connect(self._submit)
        
        self._key_input.returnPressed.connect(self._submit)
        self._license_input.returnPressed.connect(self._submit)

    def _submit(self):
        key = self._key_input.text().strip()
        license_key = self._license_input.text().strip()
        
        valid = True
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() + " QLineEdit { border: 1px solid #ff453a; }"
            )
            valid = False
            
        if not validate_license_key(license_key):
            self._license_input.setStyleSheet(
                self._license_input.styleSheet() + " QLineEdit { border: 1px solid #ff453a; }"
            )
            valid = False
            
        if not valid:
            return
            
        self.done.emit(key, license_key)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'dialog'):
            self.dialog.move(
                (self.width() - self.dialog.width()) // 2,
                (self.height() - self.dialog.height()) // 2
            )

class ApiKeysOverlay(QFrame):
    closed = pyqtSignal()
    saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        self.setStyleSheet("""
            ApiKeysOverlay {
                background: #0f0f11;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 24px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 44, 40, 44)
        layout.setSpacing(16)

        def _lbl(txt, font_size=11, bold=False, color="#ffffff", align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Inter", font_size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            # Make labels ignore mouse events so we can drag from anywhere on the background
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            return w

        layout.addWidget(_lbl("API Integrations", 18, True))
        layout.addWidget(_lbl("Manage optional INDRA connections", 11, False, "#a1a1a6"))
        layout.addSpacing(16)

        self.inputs = {}

        for key_id, label_txt in [
            ("gemini_vision_api_key", "GEMINI VISION API KEY"),
            ("elevenlabs_api_key", "ELEVENLABS API KEY"),
            ("OPENWEATHER_API_KEY", "OPENWEATHER API KEY")
        ]:
            key_label_lay = QHBoxLayout()
            key_label_lay.addWidget(_lbl(label_txt, 9, True, "#a1a1a6", Qt.AlignmentFlag.AlignLeft))
            layout.addLayout(key_label_lay)

            inp = QLineEdit()
            inp.setEchoMode(QLineEdit.EchoMode.Password)
            inp.setPlaceholderText("Enter Key (Optional)")
            inp.setFont(QFont("JetBrains Mono", 11))
            inp.setFixedHeight(46)
            inp.setStyleSheet("""
                QLineEdit {
                    background: rgba(0, 0, 0, 80);
                    color: #ffffff;
                    border: 1px solid rgba(255, 255, 255, 20);
                    border-radius: 14px;
                    padding: 4px 16px;
                }
                QLineEdit:focus {
                    border: 1px solid rgba(255, 255, 255, 80);
                    background: rgba(255, 255, 255, 10);
                }
            """)
            layout.addWidget(inp)
            self.inputs[key_id] = inp

        layout.addSpacing(20)

        # Buttons
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        cancel_btn.setFixedHeight(48)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 14px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 10); }
        """)
        cancel_btn.clicked.connect(self.closed.emit)
        btn_lay.addWidget(cancel_btn)

        save_btn = QPushButton("Save Keys")
        save_btn.setFont(QFont("Inter", 12, QFont.Weight.Bold))
        save_btn.setFixedHeight(48)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #000000;
                border: none;
                border-radius: 14px;
            }
            QPushButton:hover { background: #e0e0e0; }
            QPushButton:pressed { background: #cccccc; }
        """)
        save_btn.clicked.connect(self._save)
        btn_lay.addWidget(save_btn)

        layout.addLayout(btn_lay)

    def populate(self, data: dict):
        for k, inp in self.inputs.items():
            inp.setText(data.get(k, ""))

    def _save(self):
        new_data = {k: inp.text().strip() for k, inp in self.inputs.items()}
        self.saved.emit(new_data)
        self.closed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback."""

    closed = pyqtSignal()

    _OW, _OH = 620, 360

    def __init__(
        self,
        url: str,
        key: str,
        auto_login_url: str = "",
        manual_url: str = "",
        expiry_secs: int = 600,
        parent=None,
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: #0a0a0a;
                border: 1px solid #222222;
                border-radius: 12px;
            }}
        """)
        self._expiry = time.time() + expiry_secs
        self._on_new_key = None
        self._auto_login_url = auto_login_url
        self._manual_url = manual_url or url

        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(32, 32, 32, 32)
        main_lay.setSpacing(40)

        # Left Column
        left_lay = QVBoxLayout()
        left_lay.setSpacing(8)

        def _lbl(
            txt, fs=10, bold=False, color="#dddddd", align=Qt.AlignmentFlag.AlignLeft
        ):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(
                QFont(
                    "Segoe UI",
                    fs,
                    QFont.Weight.Bold if bold else QFont.Weight.Normal,
                )
            )
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        hdr = _lbl("REMOTE ACCESS", 14, True, "#ffffff")
        hdr.setStyleSheet("color: #ffffff; background: transparent; letter-spacing: 2px;")
        left_lay.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #2a2a2a; border: none; height: 1px; margin: 4px 0;")
        left_lay.addWidget(sep)

        left_lay.addSpacing(10)
        left_lay.addWidget(_lbl("MANUAL OVERRIDE URL", 8, bold=True, color="#888888"))

        self._url_lbl = QLabel(self._auto_login_url)
        self._url_lbl.setFont(QFont("Segoe UI", 9))
        self._url_lbl.setStyleSheet("color: #aaaaaa; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._url_lbl.setWordWrap(True)
        left_lay.addWidget(self._url_lbl)

        left_lay.addSpacing(15)
        left_lay.addWidget(_lbl("AUTHENTICATION KEY", 8, bold=True, color="#888888"))

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont("Consolas", 32, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background: #111111;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 12px;
                letter-spacing: 12px;
            }
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont("Segoe UI", 9))
        self._timer_lbl.setStyleSheet("color: #666666; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        left_lay.addWidget(self._timer_lbl)

        left_lay.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        
        new_btn = QPushButton("NEW KEY")
        new_btn.setFixedHeight(36)
        new_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet("""
            QPushButton {
                background: #222222;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 6px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: #333333;
                border: 1px solid #666666;
            }
            QPushButton:pressed {
                background: #1a1a1a;
            }
        """)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = QPushButton("DISMISS")
        close_btn.setFixedHeight(36)
        close_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888888;
                border: 1px solid #333333;
                border-radius: 6px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                color: #ffffff;
                background: #1a1a1a;
                border: 1px solid #555555;
            }
            QPushButton:pressed {
                background: transparent;
                border: 1px solid #222222;
            }
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        
        left_lay.addLayout(btn_row)
        
        # Right Column
        right_lay = QVBoxLayout()
        right_lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        
        right_lay.addWidget(_lbl("SCAN TO CONNECT", 10, bold=True, color="#ffffff", align=Qt.AlignmentFlag.AlignCenter))
        right_lay.addSpacing(12)
        
        qr_container = QFrame()
        qr_container.setStyleSheet("""
            QFrame {
                background: #111111;
                border: 1px solid #333333;
                border-radius: 12px;
            }
        """)
        qr_lay = QVBoxLayout(qr_container)
        qr_lay.setContentsMargins(16, 16, 16, 16)
        
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(180, 180)
        self._qr_label.setStyleSheet("background: white; border-radius: 4px; padding: 4px;")
        qr_lay.addWidget(self._qr_label)
        
        right_lay.addWidget(qr_container)
        right_lay.addStretch()

        main_lay.addLayout(left_lay, stretch=3)
        main_lay.addLayout(right_lay, stretch=2)

        self._update_qr(auto_login_url)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            from io import BytesIO

            import qrcode as _qrmod

            qr = _qrmod.QRCode(
                box_size=5,
                border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(
                    170,
                    170,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont("Courier New", 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 10px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont("Courier New", 7))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 10px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont("Courier New", 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            "color: #00ff88; background: #001a0d; border-radius: 10px;"
        )
        self._timer_lbl.setText("Phone connected — INDRA ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url = result[0]
                key = result[1]
                auto = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class VisionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)
        self.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        
        hdr = QLabel("◈ VISION SYSTEM")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        lay.addWidget(hdr)
        
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background: #050505; border: 1px solid #111; border-radius: 2px;")
        lay.addWidget(self.img_label, stretch=1)
        
        try:
            self.sct = mss.mss()
        except Exception:
            self.sct = None
            self.img_label.setText("V-SYS OFFLINE")
            self.img_label.setStyleSheet("color: red; background: #050505;")
            
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_vision)
        self.timer.start(500) # 2 FPS
        
    def update_vision(self):
        if not self.sct:
            return
        try:
            from PyQt6.QtGui import QImage, QPixmap
            from PyQt6.QtCore import Qt
            monitors = self.sct.monitors
            target = monitors[1] if len(monitors) > 1 else monitors[0]
            shot = self.sct.grab(target)
            
            img = QImage(shot.bgra, shot.width, shot.height, QImage.Format.Format_RGB32)
            pixmap = QPixmap.fromImage(img)
            scaled = pixmap.scaled(self.img_label.width(), self.img_label.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.img_label.setPixmap(scaled)
        except Exception:
            pass


class WebHudCanvas(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.muted = False
        self.speaking = False
        self._state = "STARTING"

        # Fix transparent background so the dark UI theme from CSS shows properly
        self.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self.page().profile().clearHttpCache()

        url = QUrl.fromLocalFile(str(BASE_DIR / "assets" / "index.html"))
        self.load(url)

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value
        # Update the HTML text dynamically and trigger the orb animations
        js = f"(() => {{ let el = document.getElementById('aiStateText'); if(el) el.innerText = '{value}'; if(window.INDRAOrb) window.INDRAOrb.setState('{value}'); }})();"
        self.page().runJavaScript(js)


class FloatWidget(QWidget):
    def __init__(self, parent, x_anchor: float, y_anchor: float, w: int, h: int):
        super().__init__(parent)
        self.x_anchor = x_anchor
        self.smart_x = None
        self.smart_y = None
        self.y_anchor = y_anchor
        self._w = w
        self._h = h
        self.setFixedSize(w, h)
        
        self.inner = QFrame(self)
        self.inner.setFixedSize(w, h)
        self.inner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.inner.setObjectName("floatInner")
        self.inner.setStyleSheet(f"""
            QFrame#floatInner {{
                background: rgba(8, 8, 12, 0.85);
                border: 1px solid rgba(0, 170, 255, 0.6);
                border-radius: 12px;
            }}
        """)

        self.is_open = False
        self._is_dragging = False
        self._drag_start_pos = None
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.anim_pos = QPropertyAnimation(self, b"pos")
        self.anim_pos.setDuration(400)
        
        self.anim_opacity = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_opacity.setDuration(300)
        
        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.anim_pos)
        self.anim_group.addAnimation(self.anim_opacity)
        self.anim_group.finished.connect(self._on_anim_finished)

        self.hide()

    def _get_target_pos(self, pw: int, ph: int) -> tuple[int, int]:
        if self.smart_x is not None and self.smart_y is not None:
            return int(self.smart_x), int(self.smart_y)
        margin = 25
        target_x = margin if self.x_anchor == 0 else pw - self._w - margin if self.x_anchor == 1 else pw * self.x_anchor - self._w / 2
        target_y = margin if self.y_anchor == 0 else ph - self._h - margin if self.y_anchor == 1 else ph * self.y_anchor - self._h / 2
        return int(target_x), int(target_y)

    def slide_to_smart_pos(self, pw: int, ph: int):
        target_x, target_y = self._get_target_pos(pw, ph)
        if self.pos().x() != target_x or self.pos().y() != target_y:
            self.anim_group.stop()
            self.anim_pos.setStartValue(self.pos())
            self.anim_pos.setEndValue(QPoint(target_x, target_y))
            self.anim_pos.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self.anim_opacity.setStartValue(self.opacity_effect.opacity())
            self.anim_opacity.setEndValue(1.0)
            self.anim_group.start()

    def _get_hidden_pos(self, target_x: int, target_y: int) -> tuple[int, int]:
        offset = 50
        start_x = target_x
        start_y = target_y
        if self.x_anchor == 0:
            start_x -= offset
        elif self.x_anchor == 1:
            start_x += offset
        elif self.y_anchor == 0:
            start_y -= offset
        else:
            start_y += offset
        return start_x, start_y

    def update_geometry(self, pw: int, ph: int):
        target_x, target_y = self._get_target_pos(pw, ph)
        if self.is_open and self.anim_group.state() != QParallelAnimationGroup.State.Running:
            self.move(target_x, target_y)

    def toggle(self):
        self.is_open = not self.is_open
        
        pw = self.parentWidget().width()
        ph = self.parentWidget().height()
        target_x, target_y = self._get_target_pos(pw, ph)
        start_x, start_y = self._get_hidden_pos(target_x, target_y)

        self.anim_group.stop()

        if self.is_open:
            self.show()
            self.raise_()
            self.move(start_x, start_y)
            self.opacity_effect.setOpacity(0.0)
            
            self.anim_pos.setStartValue(QPoint(start_x, start_y))
            self.anim_pos.setEndValue(QPoint(target_x, target_y))
            self.anim_pos.setEasingCurve(QEasingCurve.Type.OutQuart)
            
            self.anim_opacity.setStartValue(0.0)
            self.anim_opacity.setEndValue(1.0)
            self.anim_opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
        else:
            current_x, current_y = self.x(), self.y()
            self.anim_pos.setStartValue(QPoint(current_x, current_y))
            self.anim_pos.setEndValue(QPoint(start_x, start_y))
            self.anim_pos.setEasingCurve(QEasingCurve.Type.InQuart)
            
            current_opacity = self.opacity_effect.opacity()
            self.anim_opacity.setStartValue(current_opacity)
            self.anim_opacity.setEndValue(0.0)
            self.anim_opacity.setEasingCurve(QEasingCurve.Type.OutCubic)
            
        self.anim_group.start()

    def _on_anim_finished(self):
        if not self.is_open:
            self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
            self.anim_group.stop()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            self.move(new_pos)
            self.smart_x = new_pos.x()
            self.smart_y = new_pos.y()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            event.accept()

class CameraThread(QThread):
    change_pixmap_signal = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def run(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            
        # Request High Definition (1080p)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        while self._run_flag:
            ret, cv_img = cap.read()
            if ret:
                # Convert from BGR to RGB
                cv_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                
                # Encode to high-quality JPG bytes to safely pass across thread boundary
                ret, buffer = cv2.imencode('.jpg', cv_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if ret:
                    self.change_pixmap_signal.emit(buffer.tobytes())
            else:
                self.msleep(100)
        cap.release()

    def stop(self):
        self._run_flag = False
        self.wait()

class BootOverlay(QFrame):
    def __init__(self, parent, on_complete=None):
        super().__init__(parent)
        self.on_complete = on_complete
        self.resize(parent.width(), parent.height())
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QFrame {{ background: {C.BG}; }}")
        
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.title = QLabel("I.N.D.R.A")
        self.title.setFont(QFont("Courier New", 54, QFont.Weight.Bold))
        self.title.setStyleSheet(f"color: {C.PRI}; letter-spacing: 15px; background: transparent;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.title)
        
        self.sub = QLabel("CORE SYSTEM INITIALIZATION")
        self.sub.setFont(QFont("Courier New", 12))
        self.sub.setStyleSheet(f"color: {C.TEXT_DIM}; letter-spacing: 5px; background: transparent;")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.sub)
        
        self.terminal = QLabel("")
        self.terminal.setFont(QFont("Courier New", 9))
        self.terminal.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; margin-top: 30px; margin-bottom: 10px;")
        self.terminal.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.terminal)
        
        self.bar = QProgressBar()
        self.bar.setFixedSize(500, 4)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(f"QProgressBar {{ background: rgba(255,255,255,0.05); border: none; border-radius: 2px; }} QProgressBar::chunk {{ background: {C.PRI}; border-radius: 2px; }}")
        lay.addWidget(self.bar, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        
        self.val = 0
        self.boot_messages = [
            "INITIALIZING NEURAL NETWORKS...",
            "LOADING VISION SUBSYSTEMS...",
            "CONNECTING TO GLOBAL MAINFRAME...",
            "ESTABLISHING SECURE PROTOCOLS...",
            "CALIBRATING AUDIO INTERFACES...",
            "BYPASSING SECURITY FIREWALLS...",
            "SYNCHRONIZING CORE DIRECTIVES...",
            "SYSTEMS ONLINE."
        ]
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(35) # 3.5 seconds

    def paintEvent(self, e):
        super().paintEvent(e)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a subtle grid
        painter.setPen(QPen(QColor(0, 170, 255, 15), 1))
        w, h = self.width(), self.height()
        step = 50
        for x in range(0, w, step):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            painter.drawLine(0, y, w, y)

    def _tick(self):
        self.val += 1
        self.bar.setValue(self.val)
        
        msg_idx = min(len(self.boot_messages) - 1, int((self.val / 100) * len(self.boot_messages)))
        self.terminal.setText(self.boot_messages[msg_idx])
        
        if self.val >= 100:
            self.timer.stop()
            self.terminal.setStyleSheet(f"color: {C.GREEN}; background: transparent; margin-top: 30px; margin-bottom: 10px;")
            if self.on_complete:
                self.on_complete()
            QTimer.singleShot(500, self._fade_out)
            
    def _fade_out(self):
        self.anim = QPropertyAnimation(self.eff, b"opacity")
        self.anim.setDuration(1200)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.finished.connect(self.deleteLater)
        self.anim.start()

class ClickableFrame(QFrame):
    clicked = pyqtSignal(str)
    def __init__(self, game_name, parent=None):
        super().__init__(parent)
        self.game_name = game_name
    def mousePressEvent(self, event):
        self.clicked.emit(self.game_name)
        super().mousePressEvent(event)

class GameFetcherThread(QThread):
    finished = pyqtSignal(dict)
    def __init__(self, query: str):
        super().__init__()
        self.query = query
    def run(self):
        try:
            from actions.game_api import search_steam_game
            res = search_steam_game(self.query)
            if res.get("image_url"):
                import requests
                img_data = requests.get(res["image_url"], timeout=5).content
                res["image_bytes"] = img_data
            else:
                res["image_bytes"] = None
            self.finished.emit(res)
        except Exception as e:
            self.finished.emit({"error": str(e)})

class GameDetailWidget(FloatWidget):
    def __init__(self, parent=None):
        # Top-Left corner
        super().__init__(parent, 0, 0.1, 440, 420)
        self.inner.setStyleSheet(self.inner.styleSheet() + " QFrame#floatInner { background: rgba(15, 2, 5, 0.95); border: 1px solid #f43f5e; }")
        
        main_lay = QVBoxLayout(self.inner)
        main_lay.setContentsMargins(20, 20, 20, 20)
        main_lay.setSpacing(15)
        
        search_lay = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search any game...")
        self.search_input.setStyleSheet("background: rgba(255, 255, 255, 0.1); color: white; border: 1px solid rgba(244, 63, 94, 0.5); border-radius: 4px; padding: 5px;")
        self.search_input.returnPressed.connect(self._do_search)
        search_lay.addWidget(self.search_input)
        
        search_btn = QPushButton("SEARCH")
        search_btn.setStyleSheet("background: #f43f5e; color: white; font-weight: bold; border-radius: 4px; padding: 5px 15px;")
        search_btn.clicked.connect(self._do_search)
        search_lay.addWidget(search_btn)
        main_lay.addLayout(search_lay)
        
        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setMinimumHeight(220)
        self.img_lbl.setStyleSheet("background: rgba(0, 0, 0, 0.3); border-radius: 6px;")
        main_lay.addWidget(self.img_lbl)
        
        self.details = QTextBrowser()
        self.details.setStyleSheet("background: transparent; border: none; color: white; font-size: 13px; line-height: 1.5;")
        self.details.setOpenExternalLinks(True)
        main_lay.addWidget(self.details)
        self.fetcher = None
        
    def _do_search(self):
        q = self.search_input.text().strip()
        if q:
            self.fetch_game(q)
            
    def fetch_game(self, game_name: str):
        if not self.is_open:
            self.toggle()
        self.search_input.setText(game_name)
        self.img_lbl.setText("Scanning Steam Database...")
        self.img_lbl.setStyleSheet("color: #f43f5e; font-weight: bold; font-size: 14px; background: rgba(0,0,0,0.3); border-radius: 6px;")
        self.details.setText("")
        
        if self.fetcher and self.fetcher.isRunning():
            self.fetcher.terminate()
            self.fetcher.wait()
            
        self.fetcher = GameFetcherThread(game_name)
        self.fetcher.finished.connect(self._on_fetched)
        self.fetcher.start()
        
    def _on_fetched(self, data: dict):
        if "error" in data:
            self.img_lbl.setText("X")
            self.details.setText(f"<span style='color:#f43f5e;'>Error: {data['error']}</span>")
            return
            
        if data.get("image_bytes"):
            px = QPixmap()
            px.loadFromData(data["image_bytes"])
            self.img_lbl.setPixmap(px.scaled(self.img_lbl.width(), 220, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            self.img_lbl.setText("No Image")
            
        html = f"""
        <h2 style='color:#f43f5e; margin-bottom:5px;'>{data.get('name', '')}</h2>
        <p style='color:#aaaaaa; margin-top:0px;'>
            <b>Released:</b> {data.get('release_date', 'Unknown')} &nbsp;|&nbsp;
            <b>Genre:</b> {data.get('genres', 'Unknown')} &nbsp;|&nbsp;
            <b>Platform:</b> {data.get('platforms', 'PC')}
        </p>
        <p><b>Developer:</b> {data.get('developers', 'Unknown')}<br>
           <b>Publisher:</b> {data.get('publishers', 'Unknown')}</p>
        <hr style='border: 1px solid rgba(244, 63, 94, 0.3);'>
        <p>{data.get('description', '')}</p>
        """
        # Append system requirements if available (FreeToGame source)
        sys_req_html = data.get("sys_req_html", "")
        if sys_req_html:
            html += f"""
        <hr style='border: 1px solid rgba(244, 63, 94, 0.2);'>
        <p style='color:#aaaaaa;'><b>MINIMUM SYSTEM REQUIREMENTS</b></p>
        <p style='font-size:11px; color:#cccccc;'>{sys_req_html}</p>
        """
        # Source badge
        source = data.get("source", "")
        if source:
            src_color = "#1b9aef" if source == "Steam" else "#d4323e"
            html += f"<p style='color:{src_color}; font-size:10px; margin-top:8px;'>SOURCE: {source.upper()}</p>"

        self.details.setHtml(html)

# Platform colors and icons for the game panel
_PLATFORM_META = {
    "Steam": {"color": "#1b9aef", "icon": "⬡", "glow": "rgba(27, 154, 239, 0.15)"},
    "Epic Games": {"color": "#8e44ad", "icon": "◈", "glow": "rgba(142, 68, 173, 0.15)"},
    "Xbox / Game Pass": {"color": "#107c10", "icon": "⬡", "glow": "rgba(16, 124, 16, 0.15)"},
    "Riot Games": {"color": "#d4323e", "icon": "◆", "glow": "rgba(212, 50, 62, 0.15)"},
    "GOG": {"color": "#b48ef3", "icon": "◉", "glow": "rgba(180, 142, 243, 0.15)"},
    "Battle.net": {"color": "#1ca7ff", "icon": "◈", "glow": "rgba(28, 167, 255, 0.15)"},
    "EA App": {"color": "#f06c22", "icon": "◆", "glow": "rgba(240, 108, 34, 0.15)"},
}
_PLATFORM_DEFAULT = {"color": "#f43f5e", "icon": "◆", "glow": "rgba(244, 63, 94, 0.15)"}


class GameListWidget(FloatWidget):
    def __init__(self, parent=None):
        # Bottom-Right corner
        super().__init__(parent, 1, 0.6, 330, 480)
        
        # Override inner panel style for gaming dark theme
        self.inner.setStyleSheet(
            self.inner.styleSheet() + """
            QFrame#floatInner {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(10, 3, 5, 0.97),
                    stop:1 rgba(20, 5, 8, 0.95));
                border: 1px solid rgba(244, 63, 94, 0.4);
                border-radius: 12px;
            }
            """
        )
        
        main_lay = QVBoxLayout(self.inner)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        
        # ── Header bar ────────────────────────────────────────────────────
        header_bar = QWidget()
        header_bar.setFixedHeight(52)
        header_bar.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(244, 63, 94, 0.25),
                stop:1 rgba(244, 63, 94, 0.05));
            border-radius: 12px 12px 0 0;
            border-bottom: 1px solid rgba(244, 63, 94, 0.3);
        """)
        hlay = QHBoxLayout(header_bar)
        hlay.setContentsMargins(16, 0, 16, 0)
        
        title_lbl = QLabel("⚡  GAME LIBRARY")
        title_lbl.setStyleSheet(
            "color: #f43f5e; font-size: 13px; font-weight: 900; "
            "letter-spacing: 3px; background: transparent;"
        )
        title_lbl.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        
        self._count_lbl = QLabel("0 TITLES")
        self._count_lbl.setStyleSheet(
            "color: rgba(244, 63, 94, 0.6); font-size: 10px; "
            "letter-spacing: 2px; background: transparent;"
        )
        
        hlay.addWidget(title_lbl)
        hlay.addStretch()
        hlay.addWidget(self._count_lbl)
        main_lay.addWidget(header_bar)
        
        # ── Scroll area ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(255, 255, 255, 0.03);
                width: 5px;
                border-radius: 2px;
                margin: 4px 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(244, 63, 94, 0.6);
                min-height: 30px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #f43f5e;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self.lay = QVBoxLayout(self._container)
        self.lay.setSpacing(0)
        self.lay.setContentsMargins(12, 12, 12, 12)
        
        scroll.setWidget(self._container)
        main_lay.addWidget(scroll, stretch=1)
        
        # ── Footer ────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(34)
        footer.setStyleSheet("""
            background: rgba(244, 63, 94, 0.05);
            border-top: 1px solid rgba(244, 63, 94, 0.15);
            border-radius: 0 0 12px 12px;
        """)
        flay = QHBoxLayout(footer)
        flay.setContentsMargins(16, 0, 16, 0)
        hint = QLabel("CLICK A GAME FOR DETAILS  •  AI SEARCH AVAILABLE")
        hint.setStyleSheet("color: rgba(244, 63, 94, 0.4); font-size: 9px; letter-spacing: 1px; background: transparent;")
        flay.addWidget(hint)
        main_lay.addWidget(footer)
        
    def populate(self):
        # Clear old content
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        try:
            from actions.game_scanner import get_game_list
            games_dict = get_game_list()
        except Exception:
            games_dict = {}
            
        total_games = sum(len(g) for g in games_dict.values())
        self._count_lbl.setText(f"{total_games} TITLES")
            
        if not games_dict:
            no_game = QLabel("No games detected.\nInstall Steam, Epic, Xbox App to\nauto-discover your library.")
            no_game.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_game.setStyleSheet(
                "color: rgba(255,255,255,0.3); font-size: 12px; "
                "background: transparent; padding: 30px;"
            )
            self.lay.addWidget(no_game)
            self.lay.addStretch()
            return
            
        first_platform = True
        for platform, games in games_dict.items():
            meta = _PLATFORM_META.get(platform, _PLATFORM_DEFAULT)
            clr = meta["color"]
            glow = meta["glow"]
            icon = meta["icon"]
            
            if not first_platform:
                # Divider between platform sections
                div = QWidget()
                div.setFixedHeight(1)
                div.setStyleSheet(f"background: rgba(255,255,255,0.05);")
                self.lay.addWidget(div)
                spacer = QWidget()
                spacer.setFixedHeight(8)
                spacer.setStyleSheet("background: transparent;")
                self.lay.addWidget(spacer)
            first_platform = False
            
            # ── Platform header ───────────────────────────────────────────
            plat_frame = QWidget()
            plat_frame.setFixedHeight(32)
            plat_frame.setStyleSheet(f"""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {glow}, stop:1 transparent);
                border-left: 3px solid {clr};
                border-radius: 0 4px 4px 0;
                margin-bottom: 4px;
            """)
            plat_lay = QHBoxLayout(plat_frame)
            plat_lay.setContentsMargins(10, 0, 10, 0)
            
            plat_icon = QLabel(icon)
            plat_icon.setStyleSheet(f"color: {clr}; font-size: 12px; background: transparent;")
            
            plat_lbl = QLabel(platform.upper())
            plat_lbl.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            plat_lbl.setStyleSheet(
                f"color: {clr}; font-size: 9px; letter-spacing: 2px; background: transparent;"
            )
            
            count_badge = QLabel(f"{len(games)}")
            count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_badge.setFixedSize(22, 16)
            count_badge.setStyleSheet(
                f"background: {clr}; color: black; font-weight: 900; "
                f"font-size: 9px; border-radius: 3px;"
            )
            
            plat_lay.addWidget(plat_icon)
            plat_lay.addWidget(plat_lbl)
            plat_lay.addStretch()
            plat_lay.addWidget(count_badge)
            self.lay.addWidget(plat_frame)
            
            # ── Game rows ─────────────────────────────────────────────────
            for g in games:
                # Truncate long names to fit neatly
                display_name = g if len(g) <= 38 else g[:35] + "…"
                
                row = ClickableFrame(g)
                row.clicked.connect(self.window().open_game_details)
                row.setFixedHeight(40)
                row.setStyleSheet(f"""
                    QFrame {{
                        background: rgba(255, 255, 255, 0.03);
                        border: 1px solid transparent;
                        border-radius: 6px;
                        margin: 2px 0;
                    }}
                    QFrame:hover {{
                        background: {glow};
                        border: 1px solid {clr};
                    }}
                """)
                
                rlay = QHBoxLayout(row)
                rlay.setContentsMargins(10, 0, 10, 0)
                rlay.setSpacing(8)
                
                # Color dot
                dot = QLabel("●")
                dot.setFixedWidth(12)
                dot.setStyleSheet(f"color: {clr}; font-size: 8px; background: transparent; border: none;")
                
                # Game name
                name_lbl = QLabel(display_name)
                name_lbl.setStyleSheet(
                    "color: rgba(255, 255, 255, 0.9); font-size: 12px; "
                    "font-weight: 600; background: transparent; border: none;"
                )
                
                # Arrow indicator
                arrow = QLabel("›")
                arrow.setStyleSheet(f"color: rgba(255,255,255,0.2); font-size: 16px; background: transparent; border: none;")
                
                rlay.addWidget(dot)
                rlay.addWidget(name_lbl, stretch=1)
                rlay.addWidget(arrow)
                
                self.lay.addWidget(row)
            
            # Small spacing after each platform section
            sp = QWidget()
            sp.setFixedHeight(6)
            sp.setStyleSheet("background: transparent;")
            self.lay.addWidget(sp)
            
        self.lay.addStretch()


# ═══════════════════════════════════════════════════════════════════════════════
# AGNI EXCLUSIVE — Game Deals Widget
# ═══════════════════════════════════════════════════════════════════════════════
_STORE_NAMES = {
    "1": "Steam", "7": "GOG", "8": "EA", "11": "Humble",
    "15": "Fanatical", "21": "WinGameStore", "25": "Epic",
}

class DealsFetchThread(QThread):
    finished = pyqtSignal(list)
    def run(self):
        try:
            import requests
            r = requests.get(
                "https://www.cheapshark.com/api/1.0/deals"
                "?pageSize=12&sortBy=DealRating&lowerPrice=0&upperPrice=60",
                timeout=8,
            )
            self.finished.emit(r.json() if r.ok else [])
        except Exception:
            self.finished.emit([])


class GameDealsWidget(FloatWidget):
    """AGNI exclusive: live game deals from CheapShark — no API key needed."""

    def __init__(self, parent=None):
        # Bottom-Left corner
        super().__init__(parent, 0, 0.6, 330, 480)

        self.inner.setStyleSheet(
            self.inner.styleSheet() + """
            QFrame#floatInner {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(5, 10, 5, 0.97),
                    stop:1 rgba(10, 20, 10, 0.95));
                border: 1px solid rgba(16, 124, 16, 0.5);
                border-radius: 12px;
            }
            """
        )

        main_lay = QVBoxLayout(self.inner)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(50)
        hdr.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(16,124,16,0.35), stop:1 rgba(16,124,16,0.05));
            border-radius: 12px 12px 0 0;
            border-bottom: 1px solid rgba(16,124,16,0.4);
        """)
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(14, 0, 14, 0)
        title = QLabel("HOT DEALS")
        title.setStyleSheet(
            "color: #22c55e; font-size: 12px; font-weight: 900; "
            "letter-spacing: 3px; background: transparent;"
        )
        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setFixedSize(28, 28)
        self._refresh_btn.setStyleSheet("""
            QPushButton { background: rgba(34,197,94,0.15); color: #22c55e;
                border: 1px solid rgba(34,197,94,0.3); border-radius: 14px;
                font-size: 14px; font-weight: 700; }
            QPushButton:hover { background: rgba(34,197,94,0.3); }
        """)
        self._refresh_btn.clicked.connect(self.refresh)
        self._status = QLabel("Loading...")
        self._status.setStyleSheet(
            "color: rgba(34,197,94,0.5); font-size: 10px; background: transparent;"
        )
        hlay.addWidget(title)
        hlay.addStretch()
        hlay.addWidget(self._status)
        hlay.addWidget(self._refresh_btn)
        main_lay.addWidget(hdr)

        # Scrollable deal list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: rgba(255,255,255,0.04); width: 4px; border-radius: 2px; }
            QScrollBar::handle:vertical { background: rgba(34,197,94,0.4); border-radius: 2px; }
        """)
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list_container)
        self._list_lay.setContentsMargins(6, 6, 6, 6)
        self._list_lay.setSpacing(4)
        scroll.setWidget(self._list_container)
        main_lay.addWidget(scroll, stretch=1)

        # Footer
        ftr = QLabel("Powered by CheapShark API • Click to view on Steam")
        ftr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ftr.setStyleSheet(
            "color: rgba(34,197,94,0.35); font-size: 9px; "
            "padding: 6px; background: transparent;"
        )
        main_lay.addWidget(ftr)

        self.refresh()

    def refresh(self):
        self._status.setText("Fetching...")
        self._refresh_btn.setEnabled(False)
        self._fetcher = DealsFetchThread()
        self._fetcher.finished.connect(self._on_deals)
        self._fetcher.start()

    def _on_deals(self, deals: list):
        self._refresh_btn.setEnabled(True)
        self._status.setText(f"{len(deals)} deals")

        # Clear old entries
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not deals:
            lbl = QLabel("Could not fetch deals. Check connection.")
            lbl.setStyleSheet("color: rgba(255,255,255,0.4); padding: 20px; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_lay.addWidget(lbl)
            return

        for deal in deals:
            sale = float(deal.get("salePrice", 0))
            normal = float(deal.get("normalPrice", 0))
            savings = float(deal.get("savings", 0))
            title = deal.get("title", "Unknown")
            store_id = deal.get("storeID", "1")
            store = _STORE_NAMES.get(store_id, f"Store {store_id}")
            metacritic = deal.get("metacriticScore", "")
            deal_id = deal.get("dealID", "")
            steam_id = deal.get("steamAppID", "")

            # Color by discount level
            if savings >= 90:
                accent = "#ff4500"  # blazing red
            elif savings >= 75:
                accent = "#f43f5e"  # hot pink
            elif savings >= 50:
                accent = "#f97316"  # orange
            elif sale == 0:
                accent = "#22c55e"  # free = green
            else:
                accent = "#84cc16"  # mild

            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background: rgba(255,255,255,0.03);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-left: 3px solid {accent};
                    border-radius: 6px;
                }}
                QFrame:hover {{
                    background: rgba(34,197,94,0.08);
                    border-left: 3px solid {accent};
                }}
            """)
            row.setFixedHeight(62)
            row.setCursor(Qt.CursorShape.PointingHandCursor)

            # Click to open Steam store page
            def _open(checked, sid=steam_id, did=deal_id):
                import webbrowser
                if sid:
                    webbrowser.open(f"https://store.steampowered.com/app/{sid}/")
                else:
                    webbrowser.open(f"https://www.cheapshark.com/redirect?dealID={did}")

            row.mousePressEvent = _open

            rlay = QHBoxLayout(row)
            rlay.setContentsMargins(10, 6, 10, 6)
            rlay.setSpacing(8)

            # Left: badge
            badge = QLabel("FREE" if sale == 0 else f"-{int(savings)}%")
            badge.setFixedWidth(48)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(f"""
                background: {accent}; color: white; font-size: 9px; font-weight: 900;
                border-radius: 4px; padding: 2px;
            """)

            # Center: title + store
            info = QVBoxLayout()
            info.setSpacing(1)
            name_lbl = QLabel(title[:36] + ("…" if len(title) > 36 else ""))
            name_lbl.setStyleSheet(
                "color: rgba(255,255,255,0.92); font-size: 11px; "
                "font-weight: 700; background: transparent;"
            )
            sub_parts = [store]
            if metacritic and metacritic != "0":
                sub_parts.append(f"Meta: {metacritic}")
            store_lbl = QLabel("  •  ".join(sub_parts))
            store_lbl.setStyleSheet(
                "color: rgba(255,255,255,0.4); font-size: 9px; background: transparent;"
            )
            info.addWidget(name_lbl)
            info.addWidget(store_lbl)

            # Right: price
            price_col = QVBoxLayout()
            price_col.setSpacing(0)
            if sale == 0:
                price_lbl = QLabel("FREE")
                price_lbl.setStyleSheet(
                    "color: #22c55e; font-size: 13px; font-weight: 900; background: transparent;"
                )
            else:
                price_lbl = QLabel(f"${sale:.2f}")
                price_lbl.setStyleSheet(
                    f"color: {accent}; font-size: 12px; font-weight: 900; background: transparent;"
                )
            was_lbl = QLabel(f"${normal:.2f}")
            was_lbl.setStyleSheet(
                "color: rgba(255,255,255,0.25); font-size: 9px; "
                "text-decoration: line-through; background: transparent;"
            )
            price_col.addWidget(price_lbl)
            price_col.addWidget(was_lbl)

            rlay.addWidget(badge)
            rlay.addLayout(info, stretch=1)
            rlay.addLayout(price_col)

            self._list_lay.addWidget(row)

        self._list_lay.addStretch()


# ═══════════════════════════════════════════════════════════════════════════════
# AGNI EXCLUSIVE — Gaming News Widget
# ═══════════════════════════════════════════════════════════════════════════════
class NewsFetchThread(QThread):
    finished = pyqtSignal(list)
    def run(self):
        try:
            import requests, xml.etree.ElementTree as ET
            # IGN gaming RSS feed (free, no key)
            r = requests.get(
                "https://feeds.feedburner.com/ign/games-all",
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0 INDRA-GameBot/1.0"},
            )
            if not r.ok:
                self.finished.emit([])
                return
            root = ET.fromstring(r.content)
            items = []
            for item in root.findall(".//item")[:10]:
                title_el = item.find("title")
                link_el = item.find("link")
                pub_el = item.find("pubDate")
                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                pub = pub_el.text.strip()[:16] if pub_el is not None and pub_el.text else ""
                if title:
                    items.append({"title": title, "link": link, "pub": pub})
            self.finished.emit(items)
        except Exception:
            # Fallback: Rock Paper Shotgun
            try:
                import requests, xml.etree.ElementTree as ET
                r = requests.get("https://www.rockpapershotgun.com/feed", timeout=8,
                                 headers={"User-Agent": "Mozilla/5.0"})
                root = ET.fromstring(r.content)
                items = []
                for item in root.findall(".//item")[:10]:
                    te = item.find("title")
                    le = item.find("link")
                    t = te.text.strip() if te is not None and te.text else ""
                    l = le.text.strip() if le is not None and le.text else ""
                    if t:
                        items.append({"title": t, "link": l, "pub": ""})
                self.finished.emit(items)
            except Exception:
                self.finished.emit([])


class GamingNewsWidget(FloatWidget):
    """AGNI exclusive: latest gaming headlines."""

    def __init__(self, parent=None):
        # Top-Right corner
        super().__init__(parent, 1, 0.1, 420, 240)

        self.inner.setStyleSheet(
            self.inner.styleSheet() + """
            QFrame#floatInner {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(8, 4, 15, 0.97),
                    stop:1 rgba(15, 5, 25, 0.95));
                border: 1px solid rgba(168, 85, 247, 0.45);
                border-radius: 12px;
            }
            """
        )

        main_lay = QVBoxLayout(self.inner)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(50)
        hdr.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(168,85,247,0.30), stop:1 rgba(168,85,247,0.05));
            border-radius: 12px 12px 0 0;
            border-bottom: 1px solid rgba(168,85,247,0.35);
        """)
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(14, 0, 14, 0)
        title = QLabel("GAMING NEWS")
        title.setStyleSheet(
            "color: #a855f7; font-size: 12px; font-weight: 900; "
            "letter-spacing: 3px; background: transparent;"
        )
        self._news_status = QLabel("Loading...")
        self._news_status.setStyleSheet(
            "color: rgba(168,85,247,0.5); font-size: 10px; background: transparent;"
        )
        self._news_refresh = QPushButton("↻")
        self._news_refresh.setFixedSize(28, 28)
        self._news_refresh.setStyleSheet("""
            QPushButton { background: rgba(168,85,247,0.15); color: #a855f7;
                border: 1px solid rgba(168,85,247,0.3); border-radius: 14px;
                font-size: 14px; font-weight: 700; }
            QPushButton:hover { background: rgba(168,85,247,0.3); }
        """)
        self._news_refresh.clicked.connect(self.refresh)
        hlay.addWidget(title)
        hlay.addStretch()
        hlay.addWidget(self._news_status)
        hlay.addWidget(self._news_refresh)
        main_lay.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: rgba(255,255,255,0.04); width: 4px; border-radius: 2px; }
            QScrollBar::handle:vertical { background: rgba(168,85,247,0.4); border-radius: 2px; }
        """)
        self._news_container = QWidget()
        self._news_container.setStyleSheet("background: transparent;")
        self._news_lay = QVBoxLayout(self._news_container)
        self._news_lay.setContentsMargins(8, 8, 8, 8)
        self._news_lay.setSpacing(5)
        scroll.setWidget(self._news_container)
        main_lay.addWidget(scroll, stretch=1)

        ftr = QLabel("Live gaming headlines • Click to read full article")
        ftr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ftr.setStyleSheet(
            "color: rgba(168,85,247,0.3); font-size: 9px; padding: 6px; background: transparent;"
        )
        main_lay.addWidget(ftr)

        self.refresh()

    def refresh(self):
        self._news_status.setText("Fetching...")
        self._news_refresh.setEnabled(False)
        self._fetcher = NewsFetchThread()
        self._fetcher.finished.connect(self._on_news)
        self._fetcher.start()

    def _on_news(self, items: list):
        self._news_refresh.setEnabled(True)
        self._news_status.setText(f"{len(items)} articles")

        while self._news_lay.count():
            item = self._news_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not items:
            lbl = QLabel("Could not load news. Check your internet connection.")
            lbl.setStyleSheet("color: rgba(255,255,255,0.4); padding: 20px; background: transparent;")
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._news_lay.addWidget(lbl)
            return

        accents = ["#a855f7", "#c084fc", "#d8b4fe", "#9333ea", "#7c3aed"]
        for i, art in enumerate(items):
            clr = accents[i % len(accents)]
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background: rgba(255,255,255,0.03);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-left: 3px solid {clr};
                    border-radius: 6px;
                }}
                QFrame:hover {{ background: rgba(168,85,247,0.1); }}
            """)
            row.setCursor(Qt.CursorShape.PointingHandCursor)

            link_url = art.get("link", "")
            def _open(ev, url=link_url):
                import webbrowser
                if url:
                    webbrowser.open(url)
            row.mousePressEvent = _open

            rlay = QVBoxLayout(row)
            rlay.setContentsMargins(10, 7, 10, 7)
            rlay.setSpacing(2)

            headline = QLabel(art["title"])
            headline.setWordWrap(True)
            headline.setStyleSheet(
                "color: rgba(255,255,255,0.9); font-size: 11px; font-weight: 600; background: transparent;"
            )
            pub_lbl = QLabel(art.get("pub", ""))
            pub_lbl.setStyleSheet(
                f"color: {clr}; font-size: 9px; background: transparent;"
            )
            rlay.addWidget(headline)
            if art.get("pub"):
                rlay.addWidget(pub_lbl)
            self._news_lay.addWidget(row)

        self._news_lay.addStretch()


# ═══════════════════════════════════════════════════════════════════════════════
# AGNI EXCLUSIVE — Gaming HUD / Live Stats Widget
# ═══════════════════════════════════════════════════════════════════════════════
class GamingHUDWidget(FloatWidget):
    """AGNI exclusive: real-time gaming performance monitor.
    Shows GPU%, GPU Temp, VRAM, CPU%, RAM, session timer."""

    def __init__(self, parent=None):
        # Bottom of screen using y_anchor=1 (25px from bottom)
        super().__init__(parent, 0.5, 1, 720, 78)

        self.inner.setStyleSheet(
            self.inner.styleSheet() + """
            QFrame#floatInner {
                background: rgba(5, 2, 8, 0.92);
                border: 1px solid rgba(244, 63, 94, 0.4);
                border-radius: 10px;
            }
            """
        )

        import time as _time
        self._session_start = _time.time()

        lay = QHBoxLayout(self.inner)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(0)

        self._stat_labels = {}

        def _stat_block(icon: str, label: str, key: str, accent: str):
            block = QFrame()
            block.setStyleSheet(f"""
                QFrame {{
                    border-right: 1px solid rgba(255,255,255,0.08);
                    background: transparent;
                }}
            """)
            bl = QVBoxLayout(block)
            bl.setContentsMargins(12, 0, 12, 0)
            bl.setSpacing(1)
            # Icon + label row
            top = QHBoxLayout()
            top.setSpacing(4)
            ico = QLabel(icon)
            ico.setStyleSheet(f"color: {accent}; font-size: 13px; background: transparent;")
            lbl = QLabel(label)
            lbl.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 8px; background: transparent; letter-spacing: 1px;")
            top.addWidget(ico)
            top.addWidget(lbl)
            top.addStretch()
            val = QLabel("--")
            val.setStyleSheet(f"color: {accent}; font-size: 18px; font-weight: 900; background: transparent;")
            bl.addLayout(top)
            bl.addWidget(val)
            self._stat_labels[key] = val
            return block

        lay.addWidget(_stat_block("", "CPU", "cpu", "#38bdf8"))
        lay.addWidget(_stat_block("", "RAM", "ram", "#a855f7"))
        lay.addWidget(_stat_block("", "GPU", "gpu", "#f43f5e"))
        lay.addWidget(_stat_block("", "TEMP", "temp", "#f97316"))
        lay.addWidget(_stat_block("", "VRAM", "vram", "#22c55e"))

        # Session timer (no border on last block)
        timer_block = QFrame()
        timer_block.setStyleSheet("background: transparent;")
        tl = QVBoxLayout(timer_block)
        tl.setContentsMargins(12, 0, 4, 0)
        tl.setSpacing(1)
        top2 = QHBoxLayout()
        top2.setSpacing(4)
        ico2 = QLabel("")
        ico2.setStyleSheet("color: #fbbf24; font-size: 13px; background: transparent;")
        lbl2 = QLabel("SESSION")
        lbl2.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 8px; background: transparent; letter-spacing: 1px;")
        top2.addWidget(ico2)
        top2.addWidget(lbl2)
        top2.addStretch()
        self._session_lbl = QLabel("00:00")
        self._session_lbl.setStyleSheet(
            "color: #fbbf24; font-size: 18px; font-weight: 900; background: transparent;"
        )
        tl.addLayout(top2)
        tl.addWidget(self._session_lbl)
        lay.addWidget(timer_block)

        # Update timer
        self._hud_timer = QTimer(self)
        self._hud_timer.timeout.connect(self._update_hud)
        self._hud_timer.start(2000)
        self._update_hud()

    def _update_hud(self):
        import time as _t
        try:
            snap = _metrics.snapshot()
            cpu = snap.get("cpu", 0)
            mem = snap.get("mem", 0)
            gpu = snap.get("gpu", -1)
            tmp = snap.get("tmp", -1)

            self._stat_labels["cpu"].setText(f"{cpu:.0f}%")
            self._stat_labels["ram"].setText(f"{mem:.0f}%")
            self._stat_labels["gpu"].setText(f"{gpu:.0f}%" if gpu >= 0 else "N/A")
            self._stat_labels["temp"].setText(f"{tmp:.0f}°" if tmp >= 0 else "N/A")

            # VRAM via nvidia-smi
            try:
                import subprocess
                r = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=1,
                )
                used, total = r.stdout.strip().split(", ")
                self._stat_labels["vram"].setText(f"{int(used)}M")
            except Exception:
                self._stat_labels["vram"].setText("N/A")

            # Session timer
            elapsed = int(_t.time() - self._session_start)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self._session_lbl.setText(
                f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            )

            # Color CPU/GPU red if overloaded
            cpu_clr = "#ff4444" if cpu > 85 else "#38bdf8"
            gpu_clr = "#ff4444" if (gpu >= 0 and gpu > 90) else "#f43f5e"
            tmp_clr = "#ff4444" if (tmp >= 0 and tmp > 80) else "#f97316"
            self._stat_labels["cpu"].setStyleSheet(
                f"color: {cpu_clr}; font-size: 18px; font-weight: 900; background: transparent;"
            )
            self._stat_labels["gpu"].setStyleSheet(
                f"color: {gpu_clr}; font-size: 18px; font-weight: 900; background: transparent;"
            )
            self._stat_labels["temp"].setStyleSheet(
                f"color: {tmp_clr}; font-size: 18px; font-weight: 900; background: transparent;"
            )
        except Exception:
            pass

    def showEvent(self, event):
        """Reset session timer each time the HUD is shown (AGNI activated)."""
        import time as _t
        self._session_start = _t.time()
        super().showEvent(event)


class MainWindow(QMainWindow):


    _log_sig = pyqtSignal(str)
    _state_sig = pyqtSignal(str)
    _ui_cmd_sig = pyqtSignal(str)
    _phone_sig = pyqtSignal()

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("I.N.D.R.A — INDRA CORE")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width() - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command = None
        self.on_remote_clicked = None  # callable: () -> (url, key) | None
        self._muted = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        self._atlas_mode = False
        
        # Atlas Map Layer (back)
        self.atlas_view = QWebEngineView(central)
        self.atlas_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.atlas_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.atlas_view.page().setBackgroundColor(Qt.GlobalColor.black)
        self.atlas_view.page().profile().clearHttpCache()
        self.atlas_view.hide()
        url = QUrl.fromLocalFile(str(BASE_DIR / "assets" / "atlas.html"))
        self.atlas_view.load(url)
        
        # INDRA Orb Layer (front)
        self.hud = WebHudCanvas(central)

        # Floating Widgets: anchor x, anchor y, w, h
        # Top Center: Time
        self._status_panel = FloatWidget(central, 0, 0, 180, 50)
        self._build_status_panel(self._status_panel.inner)
        
        self._title_panel = FloatWidget(central, 0.5, 0, 420, 90)
        self._build_title_panel(self._title_panel.inner)
        
        self._time_panel = FloatWidget(central, 1, 0, 200, 80)
        self._build_time_panel(self._time_panel.inner)
        
        self._bottom_panel = FloatWidget(central, 0.5, 1, 450, 95)
        self._build_footer(self._bottom_panel.inner)

        self._sys_panel = FloatWidget(central, 0, 0.28, _LEFT_W + 20, 290)
        self._build_sys_monitor(self._sys_panel.inner)

        self._vision_panel = FloatWidget(central, 0, 0.72, _LEFT_W + 20, 220)
        self._build_vision_monitor(self._vision_panel.inner)
        
        self._webcam_panel = FloatWidget(central, 0.5, 0.5, 350, 250)
        self._build_webcam_monitor(self._webcam_panel.inner)
        
        self._agents_panel = FloatWidget(central, 0.82, 0.3, 280, 220)
        self._build_agents_panel(self._agents_panel.inner)
        
        self._games_panel = GameListWidget(central)
        self._games_panel.populate()
        self._games_panel.hide()
        
        self._game_detail_panel = GameDetailWidget(central)
        self._game_detail_panel.hide()

        # AGNI-exclusive extra panels
        self._game_deals_panel = GameDealsWidget(central)
        self._game_deals_panel.hide()
        self._gaming_news_panel = GamingNewsWidget(central)
        self._gaming_news_panel.hide()
        self._gaming_hud_panel = GamingHUDWidget(central)
        self._gaming_hud_panel.hide()
        
        self._right_panel = FloatWidget(central, 1, 0.5, _RIGHT_W + 20, 300)
        self._build_log_only(self._right_panel.inner)

        self._upload_panel = FloatWidget(central, 1, 1, _RIGHT_W + 20, 180)
        self._build_upload_only(self._upload_panel.inner)
        
        self._cmd_panel = FloatWidget(central, 0, 1, 400, 80)
        self._build_cmd_only(self._cmd_panel.inner)

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metrik güncelleme timer'ı
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._sync_tmr = QTimer(self)
        self._sync_tmr.timeout.connect(self._sync_widget_bounds)
        self._sync_tmr.start(1000 // 60) # 60 FPS smooth tracking

        self._log_sig.connect(self._log.append_log, Qt.ConnectionType.QueuedConnection)
        self._state_sig.connect(self._apply_state, Qt.ConnectionType.QueuedConnection)
        self._ui_cmd_sig.connect(self._handle_ui_cmd, Qt.ConnectionType.QueuedConnection)
        self._phone_sig.connect(self._handle_phone_conn, Qt.ConnectionType.QueuedConnection)

        self._overlay: SetupOverlay | None = None
        self._api_keys_overlay: ApiKeysOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self.hud.hide()
            self._show_setup()
        else:
            self.hud.hide() # Crucial: fully hide WebEngine to prevent OpenGL bleed
            self.boot_overlay = BootOverlay(central, on_complete=self.hud.show)
            self.boot_overlay.raise_()
            self.boot_overlay.show()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def toggle_atlas_mode(self, show: bool = True):
        self._atlas_mode = show
        
        if not hasattr(self, 'hud_anim'):
            self.hud_anim = QPropertyAnimation(self.hud, b"geometry")
            self.hud_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self.hud_anim.setDuration(800)
            
        if show:
            self.atlas_view.show()
            self.atlas_view.page().runJavaScript("window.dispatchEvent(new Event('resize'));")
            self.hud.page().runJavaScript("if(window.setMapMode) window.setMapMode(true);")
            self.hud_anim.setStartValue(self.hud.geometry())
            self.hud_anim.setEndValue(QRect(20, 20, 300, 300))
            self.hud_anim.start()
            
            # Hide some panels that might block the view
            if self._sys_panel.is_open: self._sys_panel.toggle(False)
            if self._vision_panel.is_open: self._vision_panel.toggle(False)
        else:
            cw = self.centralWidget()
            self.hud.page().runJavaScript("if(window.setMapMode) window.setMapMode(false);")
            self.hud_anim.setStartValue(self.hud.geometry())
            self.hud_anim.setEndValue(QRect(0, 0, cw.width(), cw.height()))
            self.hud_anim.finished.connect(self._hide_atlas_after_anim)
            self.hud_anim.start()
            
    def _hide_atlas_after_anim(self):
        self.hud_anim.finished.disconnect(self._hide_atlas_after_anim)
        if not self._atlas_mode:
            self.atlas_view.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        pw, ph = cw.width(), cw.height()
        
        if getattr(self, '_atlas_mode', False):
            if hasattr(self, 'atlas_view'): self.atlas_view.setGeometry(0, 0, pw, ph)
            # When in atlas mode, HUD geometry is managed by QPropertyAnimation
        else:
            if hasattr(self, 'atlas_view'): self.atlas_view.setGeometry(0, 0, pw, ph)
            if hasattr(self, 'hud'): self.hud.setGeometry(0, 0, pw, ph)
            
        for p in [getattr(self, k, None) for k in ('_sys_panel', '_vision_panel', '_right_panel', '_title_panel', '_time_panel', '_status_panel', '_bottom_panel', '_upload_panel', '_cmd_panel')]:
            if p: p.update_geometry(pw, ph)
        if hasattr(self, 'boot_overlay') and self.boot_overlay:
            try:
                self.boot_overlay.resize(pw, ph)
            except RuntimeError:
                pass
        if self._overlay:
            self._overlay.setGeometry(0, 0, pw, ph)
        if hasattr(self, '_api_keys_overlay') and self._api_keys_overlay:
            ow, oh = 540, 520
            self._api_keys_overlay.setGeometry(
                cw.width() - ow - 30,
                30,
                ow,
                oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width() - ow) // 2,
                (cw.height() - oh) // 2,
                ow,
                oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")


    def _apply_theme(self, mode: str):
        """Swaps the UI theme between INDRA, VAYU, and AGNI."""
        self._time_panel.setStyleSheet(self._time_panel.styleSheet().replace("#38bdf8", C.PRI).replace("#f43f5e", C.PRI))
        
        if mode == "vayu":
            panels_to_close = [self._games_panel, getattr(self, '_game_detail_panel', None)]
            to_toggle = [p for p in panels_to_close if p and p.is_open]
            if to_toggle:
                for p in to_toggle: p.is_open = False
                self._update_smart_layout()
                for p in to_toggle: p.is_open = True
                for p in to_toggle: p.toggle()
            if hasattr(self, '_status_lbl'):
                self._status_lbl.setText("VAYU ONLINE")
                self._status_lbl.setStyleSheet("color: #38bdf8; background: transparent;")
            if hasattr(self, '_title_lbl'):
                self._title_lbl.setText("V.A.Y.U")
                self._title_lbl.setStyleSheet("color: #38bdf8; background: transparent;")
                self._sub_lbl.setText("Visual Analysis and Yield Unit")
                self._sub_lbl.setStyleSheet("color: rgba(56, 189, 248, 0.7); background: transparent;")
            self._time_panel.setStyleSheet(self._time_panel.styleSheet().replace(C.PRI, "#38bdf8").replace(C.PRI_DIM, "#38bdf8"))
            if hasattr(self, 'hud'):
                self.hud.page().runJavaScript("if (typeof window.setTheme === 'function') window.setTheme('vayu');")
        elif mode == "agni":
            # Close all other panels to keep the UI clean for gaming
            panels_to_close = [self._sys_panel, self._vision_panel, self._right_panel, 
                               self._agents_panel, self._upload_panel, self._cmd_panel, self._webcam_panel]
            to_toggle = [p for p in panels_to_close if p.is_open]
            if to_toggle:
                for p in to_toggle: p.is_open = False
                self._update_smart_layout()
                for p in to_toggle: p.is_open = True
                for p in to_toggle: p.toggle()
                
            if hasattr(self, '_status_lbl'):
                self._status_lbl.setText("AGNI ONLINE")
                self._status_lbl.setStyleSheet("color: #f43f5e; background: transparent;")
            if hasattr(self, '_title_lbl'):
                self._title_lbl.setText("A.G.N.I")
                self._title_lbl.setStyleSheet("color: #f43f5e; background: transparent;")
                self._sub_lbl.setText("Advanced Gaming Network Interface")
                self._sub_lbl.setStyleSheet("color: rgba(244, 63, 94, 0.7); background: transparent;")
            self._time_panel.setStyleSheet(self._time_panel.styleSheet().replace(C.PRI, "#f43f5e").replace(C.PRI_DIM, "#f43f5e"))
            if hasattr(self, 'hud'):
                self.hud.page().runJavaScript("if (typeof window.setTheme === 'function') window.setTheme('agni');")

        # For VAYU and INDRA: close all gaming panels
        if mode in ("vayu", "indra"):
            all_gaming = [
                self._games_panel,
                getattr(self, '_game_detail_panel', None),
                getattr(self, '_game_deals_panel', None),
                getattr(self, '_gaming_news_panel', None),
                getattr(self, '_gaming_hud_panel', None),
            ]
            to_toggle = [p for p in all_gaming if p and p.is_open]
            if to_toggle:
                for p in to_toggle: p.is_open = False
                self._update_smart_layout()
                for p in to_toggle: p.is_open = True
                for p in to_toggle: p.toggle()

        if mode == "vayu":
            pass  # vayu-specific label/color already set above
        elif mode == "agni":
            pass  # agni-specific label/color already set above
        else:
            if hasattr(self, '_status_lbl'):
                self._status_lbl.setText("INDRA CORE")
                self._status_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
            if hasattr(self, '_title_lbl'):
                self._title_lbl.setText("I.N.D.R.A")
                self._title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
                self._sub_lbl.setText("Just A Rather Very Intelligent System")
                self._sub_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
            if hasattr(self, 'hud'):
                self.hud.page().runJavaScript("if (typeof window.setTheme === 'function') window.setTheme('indra');")

    @pyqtSlot(str)
    def _handle_ui_cmd(self, cmd: str):
        if cmd == "API_KEYS":
            self.show_api_keys()
            return
            
        panels = {
            "sys": self._sys_panel,
            "vision": self._vision_panel,
            "log": self._right_panel,
            "title": self._title_panel,
            "status": self._status_panel,
            "webcam": self._webcam_panel,
            "time": self._time_panel,
            "upload": self._upload_panel,
            "cmd": self._cmd_panel,
            "agents": self._agents_panel,
            "games": self._games_panel,
            "gamedetails": self._game_detail_panel,
            "gamedeals": self._game_deals_panel,
            "gamingnews": self._gaming_news_panel,
            "gaminghud": self._gaming_hud_panel,
        }
        _agni_only = {"games", "gamedetails", "gamedeals", "gamingnews", "gaminghud"}
        if cmd in panels:
            self._update_smart_layout(panels[cmd])
            panels[cmd].toggle()
        elif cmd == "all":
            # AGNI: open only gaming panels
            if hasattr(self, '_status_lbl') and self._status_lbl.text() == "AGNI ONLINE":
                target_panels = {k: v for k, v in panels.items() if k in _agni_only}
            else:
                # INDRA/VAYU: open everything except AGNI-only panels
                target_panels = {k: v for k, v in panels.items() if k not in _agni_only}
                
            # Pre-calculate layout for all target panels toggling
            for p in target_panels.values(): p.is_open = not p.is_open
            self._update_smart_layout()
            for p in target_panels.values(): p.is_open = not p.is_open
            
            for p in target_panels.values():
                p.toggle()
        elif cmd == "remote":
            self.open_remote()
        elif cmd == "switch_vayu":
            self._apply_theme(mode="vayu")
        elif cmd == "switch_agni":
            self._apply_theme(mode="agni")
        elif cmd == "switch_indra":
            self._apply_theme(mode="indra")
        elif cmd == "fullscreen_on":
            self.showFullScreen()
        elif cmd == "fullscreen_off":
            self.showNormal()
        elif cmd == "hide_to_tray":
            self.hide()
        elif cmd == "show_from_tray":
            self.showFullScreen()
        elif cmd == "open_atlas":
            url_str = f"file:///{str(BASE_DIR.as_posix())}/assets/atlas.html"
            if self.atlas_view.url().toString() != url_str:
                self.atlas_view.load(QUrl(url_str))
            
            if not getattr(self, '_atlas_mode', False):
                self.toggle_atlas_mode(True)
            
            # Crossfade to globe
            self.atlas_view.page().runJavaScript("if(window.INDRA) window.INDRA.showGlobe();")
            
        elif cmd == "close_atlas":
            self.toggle_atlas_mode(False)
        elif cmd.startswith("locate_place|"):
            _, target = cmd.split("|", 1)
            
            url_str = f"file:///{str(BASE_DIR.as_posix())}/assets/atlas.html"
            if self.atlas_view.url().toString() != url_str:
                self.atlas_view.load(QUrl(url_str))
                
            if not getattr(self, '_atlas_mode', False):
                self.toggle_atlas_mode(True)
                
            # Crossfade to map and fly
            js = f"if(window.INDRA) window.INDRA.flyTo('{target}');"
            self.atlas_view.page().runJavaScript(js)

    def toggle_activity_log(self):
        self._right_panel.toggle()

    def _build_status_panel(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        self._status_lbl = QLabel("INDRA CORE")
        self._status_lbl.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        self._status_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status_lbl)

    def _build_title_panel(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(1)
        self._title_lbl = QLabel("I.N.D.R.A")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setFont(QFont("Courier New", 22, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(self._title_lbl)
        self._sub_lbl = QLabel("Just A Rather Very Intelligent System")
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setFont(QFont("Courier New", 9))
        self._sub_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        lay.addWidget(self._sub_lbl)

    def _build_time_panel(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 9))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._date_lbl)

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_sys_monitor(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈ SYS MONITOR")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color: {C.PRI}; background: transparent; "
            f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;"
        )
        lay.addWidget(hdr)
        lay.addSpacing(2)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("NET", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TMP", "#ff6688")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net, self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)
        info_panel = QWidget()
        info_panel.setStyleSheet(f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(6, 5, 6, 5)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 8))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)
        lay.addWidget(info_panel)

    def _build_vision_monitor(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈ VISION SYSTEM")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color: {C.PRI}; background: transparent; "
            f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;"
        )
        lay.addWidget(hdr)
        lay.addSpacing(2)

        self._vision_panel_view = VisionPanel()
        lay.addWidget(self._vision_panel_view)
        lay.addSpacing(4)

        for txt, col in [
            ("AI CORE\nACTIVE", C.GREEN),
            ("SEC\nCLEARED", C.PRI),
            ("PROTOCOL\nXXXVIII", C.TEXT_DIM),
        ]:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: rgba(0, 170, 255, 0.05); "
                f"border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px;"
            )
            lay.addWidget(lbl)

    def _sec(self, txt: str) -> QLabel:
        l = QLabel(f"◈ {txt}")
        l.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        l.setStyleSheet(
            f"color: {C.PRI}; background: transparent; "
            f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;"
        )
        return l

    def _build_webcam_monitor(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(self._sec("WEBCAM FEED"))
        
        self.webcam_label = QLabel()
        self.webcam_label.setFixedSize(320, 180)
        self.webcam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.webcam_label.setStyleSheet(f"background: {C.BG}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        lay.addWidget(self.webcam_label)

        self.camera_thread = None
        self._latest_webcam_frame = None

    def update_webcam_image(self, jpg_bytes):
        self._latest_webcam_frame = jpg_bytes
        pixmap = QPixmap()
        pixmap.loadFromData(jpg_bytes)
        scaled_pixmap = pixmap.scaled(
            self.webcam_label.width(),
            self.webcam_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.webcam_label.setPixmap(scaled_pixmap)

    def toggle_webcam_panel(self):
        if self._webcam_panel.is_open:
            self._webcam_panel.toggle()
            if self.camera_thread:
                self.camera_thread.stop()
                self.camera_thread = None
        else:
            self._webcam_panel.toggle()
            self.camera_thread = CameraThread()
            self.camera_thread.change_pixmap_signal.connect(self.update_webcam_image)
            self.camera_thread.start()

    def _build_agents_panel(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.setSpacing(12)

        header_lay = QHBoxLayout()
        icon = QLabel("⚲")
        icon.setStyleSheet(f"color: {C.PRI}; font-size: 18px;")
        lbl = QLabel("NETWORK AGENTS")
        lbl.setStyleSheet(f"color: {C.PRI}; font-size: 14px; font-weight: 800; letter-spacing: 2px;")
        header_lay.addWidget(icon)
        header_lay.addWidget(lbl)
        header_lay.addStretch()
        lay.addLayout(header_lay)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
        line.setFixedHeight(1)
        lay.addWidget(line)

        def make_agent_row(name, color, is_active=True):
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background: rgba(10, 10, 15, 0.6);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 6px;
                }}
                QFrame:hover {{
                    border: 1px solid {color};
                    background: rgba(255, 255, 255, 0.05);
                }}
            """)
            rlay = QHBoxLayout(row)
            rlay.setContentsMargins(12, 10, 12, 10)
            rlay.setSpacing(10)
            
            dot = QLabel("●")
            dot_color = "#4ade80" if is_active else "#94a3b8"
            dot.setStyleSheet(f"color: {dot_color}; font-size: 14px; background: transparent; border: none;")
            
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px; background: transparent; border: none;")
            
            status_lbl = QLabel("ONLINE" if is_active else "STANDBY")
            status_lbl.setStyleSheet(f"color: {dot_color}; font-size: 10px; font-weight: bold; font-family: monospace; background: transparent; border: none;")
            
            rlay.addWidget(dot)
            rlay.addWidget(name_lbl)
            rlay.addStretch()
            rlay.addWidget(status_lbl)
            return row

        lay.addWidget(make_agent_row("INDRA", C.PRI, True))
        lay.addWidget(make_agent_row("VAYU", "#38bdf8", True))
        lay.addWidget(make_agent_row("AGNI", "#f43f5e", True))
        
        lay.addStretch()

    def _sync_widget_bounds(self):
        if not hasattr(self, 'hud'): return
        import json
        bounds = []
        ignored = getattr(self, '_ignored_smart', None)
        if ignored is None:
            ignored = getattr(self, '_status_panel', None)
            if ignored is not None:
                ignored = [self._status_panel, self._time_panel, self._title_panel, self._bottom_panel, self._cmd_panel]
                self._ignored_smart = ignored
            else:
                ignored = []
                
        for w in self.findChildren(FloatWidget):
            if w in ignored: continue
            if w.is_open or w.anim_group.state() == QParallelAnimationGroup.State.Running:
                op = w.opacity_effect.opacity()
                if op > 0.05:
                    bounds.append({"x": w.x(), "y": w.y(), "w": w._w, "h": w._h, "op": op})
        
        bounds_json = json.dumps(bounds)
        if getattr(self, '_last_bounds_json', None) == bounds_json:
            return
        self._last_bounds_json = bounds_json
            
        js = f"if(typeof window.updateWidgetBounds === 'function') window.updateWidgetBounds({bounds_json});"
        self.hud.page().runJavaScript(js)

    def _update_smart_layout(self, toggling_widget=None):
        pw = self.width()
        ph = self.height()
        margin = 25
        spacing = 40

        # Ignore fixed header/footer panels from dynamic layout
        ignored = getattr(self, '_ignored_smart', None)
        if ignored is None:
            # AGNI panels are fixed dashboard widgets, ignore them from smart auto-stacking
            ignored = [
                self._status_panel, self._time_panel, self._title_panel, 
                self._bottom_panel, self._cmd_panel,
                getattr(self, '_gaming_hud_panel', None),
                getattr(self, '_game_deals_panel', None),
                getattr(self, '_gaming_news_panel', None),
                getattr(self, '_games_panel', None),
                getattr(self, '_game_detail_panel', None)
            ]
            self._ignored_smart = ignored

        future_open = []
        for w in self.findChildren(FloatWidget):
            if w in ignored: continue
            
            will_be_open = w.is_open
            if w == toggling_widget:
                will_be_open = not w.is_open
            if will_be_open:
                future_open.append(w)

        left_widgets = [w for w in future_open if w.x_anchor < 0.3]
        center_widgets = [w for w in future_open if 0.3 <= w.x_anchor <= 0.7]
        right_widgets = [w for w in future_open if w.x_anchor > 0.7]

        def layout_group(group, side_x_anchor):
            if not group: return
            group.sort(key=lambda w: w.y_anchor)
            total_h = sum(w._h for w in group)
            available_h = ph - 2 * margin
            
            # If total height exceeds available height, pack tightly
            if total_h >= available_h:
                gap = 10
                start_y = margin
            else:
                # Evenly distribute the remaining space
                gap = (available_h - total_h) / (len(group) + 1)
                start_y = margin + gap
            
            current_y = start_y
            for w in group:
                if side_x_anchor == 0: target_x = margin
                elif side_x_anchor == 1: target_x = pw - w._w - margin
                else: target_x = pw * side_x_anchor - w._w / 2
                
                w.smart_x = target_x
                w.smart_y = current_y
                current_y += w._h + gap

        layout_group(left_widgets, 0)
        layout_group(center_widgets, 0.5)
        layout_group(right_widgets, 1)

        # Trigger slide for widgets that are ALREADY open (excluding the one being toggled)
        for w in future_open:
            if w != toggling_widget and w.is_open:
                w.slide_to_smart_pos(pw, ph)

    def _build_log_only(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(self._sec("ACTIVITY LOG"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

    def _build_upload_only(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(self._sec("FILE UPLOAD"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)
        self._file_hint = QLabel("Drop or click to upload")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        lay.addWidget(self._file_hint)

    def _build_cmd_only(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(self._sec("COMMAND INPUT"))
        row = QHBoxLayout()
        row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{ background: rgba(0, 13, 20, 0.5); color: {C.WHITE}; border: 1px solid {C.BORDER}; border-radius: 4px; padding: 3px 7px; }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)
        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{ background: rgba(0, 170, 255, 0.2); color: {C.PRI}; border: 1px solid {C.PRI_DIM}; border-radius: 4px; }}
            QPushButton:hover {{ background: rgba(0, 170, 255, 0.4); border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        lay.addLayout(row)

    def _build_footer(self, w: QWidget):
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 15, 10, 15)
        lay.setSpacing(6)

        title = QLabel("I.N.D.R.A  ·  SYSTEM CONTROLS")
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        sub = QLabel("[F4] Toggle Microphone   |   [F11] Toggle Fullscreen")
        sub.setFont(QFont("Courier New", 8))
        sub.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)

        copy = QLabel("FatihMakes Industries  ·  © STARK INDUSTRIES")
        copy.setFont(QFont("Courier New", 7))
        copy.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(copy)

    def _on_file_selected(self, path: str):
        self._current_file = path
        p = Path(path)
        cat = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(
            f"{icon}  {p.name}  ·  {size}  ·  Tell INDRA what to do with it"
        )
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(
                target=self.on_text_command, args=(msg,), daemon=True
            ).start()


    def _handle_phone_conn(self):
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def notify_phone_connected(self) -> None:
        self._phone_sig.emit()

    @pyqtSlot(str)
    def open_game_details(self, game_name: str):
        self._game_detail_panel.fetch_game(game_name)

    def open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url = result[0]
        key = result[1]
        auto = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov = RemoteKeyOverlay(
            url, key, auto_login_url=auto, manual_url=manual, expiry_secs=600, parent=cw
        )
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width() - ow) // 2,
            (cw.height() - oh) // 2,
            ow,
            oh,
        )
        ov.closed.connect(lambda: setattr(self, "_remote_overlay", None))
        ov.show()
        ov.raise_()  # Force to the top of the Z-order so the orb doesn't clip through!
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #140006; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 3px;
                }}
            """)
        else:
            self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt:
            return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(
                target=self.on_text_command, args=(txt,), daemon=True
            ).start()

    def _apply_state(self, state: str):
        self.hud.state = state
        self.hud.speaking = state == "SPEAKING"

    def _check_config(self) -> bool:
        if not API_FILE.exists():
            return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and validate_license_key(d.get("license_key", ""))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ov.setGeometry(0, 0, cw.width(), cw.height())
        ov.done.connect(self._on_setup_done)
        ov.show()
        ov.raise_()
        self._overlay = ov

    def _enable_autostart(self):
        if platform.system() == "Windows":
            try:
                exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "INDRA_AI", 0, winreg.REG_SZ, f'"{exe_path}"')
                winreg.CloseKey(key)
                self._log.append_log("SYS: Auto-start enabled in Windows Registry.")
            except Exception as e:
                self._log.append_log(f"SYS: Auto-start failed: {e}")

    def _on_setup_done(self, key: str, license_key: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "license_key": license_key}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        self._enable_autostart()
        
        if self._overlay:
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None
            
        cw = self.centralWidget()
        self.hud.hide() # Keep web engine hidden while BootOverlay plays
        self.boot_overlay = BootOverlay(cw, on_complete=self.hud.show)
        self.boot_overlay.resize(cw.width(), cw.height())
        self.boot_overlay.raise_()
        self.boot_overlay.show()

        self._apply_state("LISTENING")
        self._log.append_log(f"SYS: Initialised. OS={platform.system().upper()}. INDRA online.")

    def show_api_keys(self):
        if not hasattr(self, '_api_keys_overlay') or self._api_keys_overlay is None:
            ov = ApiKeysOverlay(self.centralWidget())
            
            # Load existing keys
            try:
                with open(API_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
            ov.populate(data)
            
            ov.closed.connect(self._close_api_keys)
            ov.saved.connect(self._save_api_keys)
            self._api_keys_overlay = ov

        cw = self.centralWidget()
        ow, oh = 540, 520
        self._api_keys_overlay.setGeometry(
            cw.width() - ow - 30,
            30,
            ow,
            oh,
        )
        self._api_keys_overlay.show()
        self._api_keys_overlay.raise_()

    def _close_api_keys(self):
        if hasattr(self, '_api_keys_overlay') and self._api_keys_overlay:
            self._api_keys_overlay.hide()

    def _save_api_keys(self, new_data: dict):
        try:
            with open(API_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
            
        for k, v in new_data.items():
            if v:  # Only update if a value was actually entered
                data[k] = v
                
        with open(API_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
        self._log.append_log("SYS: Optional API keys updated in vault.")


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app

    def mainloop(self):
        self._app.exec()

    def protocol(self, *_):
        pass


class INDRAUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._app.setQuitOnLastWindowClosed(False)
        self._win = MainWindow(face_path)
        
        # System Tray
        self._tray = QSystemTrayIcon(QIcon(face_path), self._app)
        self._tray.setToolTip("I.N.D.R.A Core")
        
        self._tray_menu = QMenu()
        show_action = QAction("Show INDRA", self._app)
        show_action.triggered.connect(self._win.showFullScreen)
        quit_action = QAction("Quit", self._app)
        quit_action.triggered.connect(self._app.quit)
        
        self._tray_menu.addAction(show_action)
        self._tray_menu.addAction(quit_action)
        self._tray.setContextMenu(self._tray_menu)
        self._tray.show()
        
        self._win.showFullScreen()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()


    def _safe_cmd(self, cmd: str):
        """Thread-safe way to send a UI command from any thread (including asyncio)."""
        QMetaObject.invokeMethod(
            self._win,
            "_handle_ui_cmd",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, cmd),
        )

    def toggle_sys_monitor(self):
        self._safe_cmd("sys")

    def toggle_vision_monitor(self):
        self._safe_cmd("vision")

    def toggle_webcam_panel(self):
        self._safe_cmd("webcam")

    def toggle_agents_panel(self):
        self._safe_cmd("agents")

    @property
    def latest_webcam_frame(self) -> bytes | None:
        return getattr(self._win, "_latest_webcam_frame", None)

    def toggle_activity_log(self):
        self._safe_cmd("log")

    def toggle_time_panel(self):
        self._safe_cmd("time")

    def toggle_title_panel(self):
        self._safe_cmd("title")

    def toggle_status_panel(self):
        self._safe_cmd("status")

    def toggle_controls_panel(self):
        self._safe_cmd("controls")

    def toggle_upload_panel(self):
        self._safe_cmd("upload")

    def toggle_cmd_panel(self):
        self._safe_cmd("cmd")

    def toggle_all_panels(self):
        self._safe_cmd("all")

    def open_remote(self):
        self._safe_cmd("remote")
        
    def set_fullscreen(self, enabled: bool):
        self._win._ui_cmd_sig.emit("fullscreen_on" if enabled else "fullscreen_off")

    def set_state(self, state: str):    
        try:
            self._win._state_sig.emit(state)
        except RuntimeError:
            pass

    def write_log(self, text: str):
        try:
            self._win._log_sig.emit(text)
        except RuntimeError:
            pass

    def trigger_ui_cmd(self, cmd: str):
        try:
            self._win._ui_cmd_sig.emit(cmd)
        except RuntimeError:
            pass

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")


