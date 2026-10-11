"""Native two-pass liquid glass. GLSL restored from this project's MIT web UI.

Render the moving environment to a texture, then refract that texture through
rounded panel lenses. Qt paints the resulting frame behind ordinary widgets.
No browser, webview, HTTP server, or screen capture is involved.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import struct
import sys
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QOffscreenSurface,
                          QOpenGLContext, QPainter, QPainterPath, QPen,
                          QRadialGradient, QSurfaceFormat, QVector2D, QVector3D, QVector4D)
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLFramebufferObject, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtWidgets import QApplication, QFrame, QWidget

SHADERS = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets" / "shaders"


class GlassRenderer:
    """Own a private OpenGL 2.1 context and bounded-size render targets."""
    def __init__(self):
        self.context = self.surface = self.buffer = None
        self.programs = {}
        self.targets = None
        self.error = ""
        self.available = False
        try:
            if os.environ.get("QT_QPA_PLATFORM") in {"offscreen", "minimal"}:
                raise RuntimeError("Headless platform: using the still Aero background.")
            fmt = QSurfaceFormat()
            fmt.setVersion(2, 1)
            fmt.setDepthBufferSize(0)
            fmt.setStencilBufferSize(0)
            self.context = QOpenGLContext()
            self.context.setFormat(fmt)
            if not self.context.create():
                raise RuntimeError("OpenGL context is unavailable.")
            self.surface = QOffscreenSurface()
            self.surface.setFormat(self.context.format())
            self.surface.create()
            if not self.surface.isValid() or not self.context.makeCurrent(self.surface):
                raise RuntimeError("OpenGL surface is unavailable.")
            vertex = (SHADERS / "vertex.vert").read_text(encoding="utf-8")
            for name in ("environment", "copy", "glass"):
                program = QOpenGLShaderProgram()
                if not (program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertex)
                        and program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment,
                                                           (SHADERS / (name + ".frag")).read_text(encoding="utf-8"))
                        and program.link()):
                    raise RuntimeError(f"{name} shader: {program.log()}")
                self.programs[name] = program
            self.buffer = QOpenGLBuffer()
            if not self.buffer.create():
                raise RuntimeError("OpenGL vertex buffer is unavailable.")
            self.buffer.bind()
            vertices = struct.pack("8f", -1, -1, 1, -1, -1, 1, 1, 1)
            self.buffer.allocate(vertices, len(vertices))
            self.buffer.release()
            self.functions = self.context.functions()
            self.functions.initializeOpenGLFunctions()
            self.available = True
        except Exception as exc:
            self.error = str(exc)
        finally:
            if self.context:
                self.context.doneCurrent()

    def _float(self, program, name, value):
        # Force glUniform1f: PySide's scalar overload can choose the integer type.
        self.functions.glUniform1f(program.uniformLocation(name), float(value))

    def _quad(self, program):
        location = program.attributeLocation("aPosition")
        self.buffer.bind()
        program.enableAttributeArray(location)
        program.setAttributeBuffer(location, 0x1406, 0, 2)
        self.functions.glDrawArrays(0x0005, 0, 4)
        program.disableAttributeArray(location)
        self.buffer.release()

    def render(self, width, height, clock, pointer, ripples, panes, dark):
        if not self.available or width < 1 or height < 1:
            return QImage()
        if not self.context.makeCurrent(self.surface):
            raise RuntimeError("Lost the OpenGL context.")
        try:
            scale = min(1.25, math.sqrt(1_400_000 / (width * height)))
            size = (max(1, int(width * scale)), max(1, int(height * scale)))
            if not self.targets or (self.targets[0].width(), self.targets[0].height()) != size:
                self.targets = (QOpenGLFramebufferObject(*size), QOpenGLFramebufferObject(*size))
                if not all(target.isValid() for target in self.targets):
                    raise RuntimeError("OpenGL render target allocation failed.")
            scene, output = self.targets
            gl = self.functions
            gl.glViewport(0, 0, *size)
            gl.glDisable(0x0BE2)
            scene.bind()
            program = self.programs["environment"]
            program.bind()
            program.setUniformValue("uResolution", QVector2D(width, height))
            program.setUniformValue("uPointer", QVector2D(*pointer[:2]))
            self._float(program, "uTime", clock)
            self._float(program, "uDark", dark)
            self._quad(program)
            program.release()
            output.bind()
            gl.glActiveTexture(0x84C0)
            gl.glBindTexture(0x0DE1, scene.texture())
            program = self.programs["copy"]
            program.bind()
            program.setUniformValue("uScene", 0)
            self._quad(program)
            program.release()
            gl.glEnable(0x0BE2)
            gl.glBlendFunc(0x0302, 0x0303)
            program = self.programs["glass"]
            program.bind()
            program.setUniformValue("uScene", 0)
            program.setUniformValue("uResolution", QVector2D(width, height))
            program.setUniformValue("uPointer", QVector3D(*pointer))
            self._float(program, "uDark", dark)
            for index in range(4):
                ripple = ripples[index] if index < len(ripples) else (0, 0, 0, 0)
                program.setUniformValue(f"uRipples[{index}]", QVector4D(*ripple))
            gl.glEnable(0x0C11)  # Scissor each lens, including the scroll viewport.
            for rect, radius, material, clip in panes:
                bounds = clip.intersected(QRectF(0, 0, width, height))
                if bounds.isEmpty():
                    continue
                gl.glScissor(int(bounds.x() * size[0] / width), int((height - bounds.bottom()) * size[1] / height),
                             math.ceil(bounds.width() * size[0] / width), math.ceil(bounds.height() * size[1] / height))
                program.setUniformValue("uRect", QVector4D(rect.x(), rect.y(), rect.width(), rect.height()))
                self._float(program, "uRadius", radius)
                self._float(program, "uMaterial", material)
                self._quad(program)
            program.release()
            gl.glDisable(0x0C11)
            gl.glBindTexture(0x0DE1, 0)
            gl.glDisable(0x0BE2)
            image = output.toImage()
            output.release()
            if image.isNull():
                raise RuntimeError("The liquid glass frame is empty.")
            return image
        finally:
            self.context.doneCurrent()

    def close(self):
        self.available = False
        if self.context and self.surface and self.context.makeCurrent(self.surface):
            self.targets = None
            self.programs.clear()
            if self.buffer:
                self.buffer.destroy()
                self.buffer = None
            self.context.doneCurrent()
        if self.surface:
            self.surface.destroy()


def reduced_motion():
    if sys.platform != "win32":
        return False
    import ctypes
    enabled = ctypes.c_int(1)
    return bool(ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0) and not enabled.value)


class AeroBackdrop(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = GlassRenderer()
        self.frame = QImage()
        self.panels = []
        self.dark = False
        self.live = True
        self.reduced_motion = reduced_motion()
        self.epoch = time.monotonic()
        self.pointer = (-300.0, -300.0, 0.0)
        self.target_pointer = self.pointer
        self.clicks = []
        self.disposed = False
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        kind = event.type()
        if isinstance(watched, QWidget) and watched.window() == self.window():
            if kind in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
                point = self.mapFromGlobal(event.globalPosition().toPoint())
                self.target_pointer = (float(point.x()), float(point.y()), 1.0)
                if kind == QEvent.Type.MouseButtonPress and self.live and not self.reduced_motion:
                    self.clicks = (self.clicks + [(point.x(), point.y(), time.monotonic())])[-4:]
            elif kind == QEvent.Type.Leave and watched is self:
                self.target_pointer = (*self.target_pointer[:2], 0.0)
            elif kind in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate, QEvent.Type.WindowStateChange,
                          QEvent.Type.Show, QEvent.Type.Hide):
                QTimer.singleShot(0, self.sync_animation)
        return False

    def sync_animation(self):
        active = (not self.disposed and self.live and not self.reduced_motion and self.renderer.available
                  and self.isVisible() and self.window().isActiveWindow() and not self.window().isMinimized())
        if active and not self.timer.isActive():
            self.timer.start()
        elif not active:
            self.timer.stop()

    def set_appearance(self, dark, live):
        self.dark, self.live = dark, live
        self.clicks.clear()
        self.tick()
        self.sync_animation()

    def pane_rects(self):
        panes = []
        for panel in self.panels:
            if not panel.isVisible():
                continue
            rect = QRectF(panel.mapTo(self, panel.rect().topLeft()), panel.size())
            clip = rect.adjusted(-2, -2, 2, 2)
            ancestor = panel.parentWidget()
            while ancestor and ancestor is not self:
                clip = clip.intersected(QRectF(ancestor.mapTo(self, ancestor.rect().topLeft()), ancestor.size()))
                ancestor = ancestor.parentWidget()
            panes.append((rect, panel.radius, panel.material, clip))
        return panes

    def tick(self):
        if self.disposed:
            return
        self.pointer = tuple(a + (b - a) * .22 for a, b in zip(self.pointer, self.target_pointer))
        now = time.monotonic()
        self.clicks = [click for click in self.clicks if now - click[2] < 3]
        ripples = [(x, y, now - birth, 1.0) for x, y, birth in self.clicks]
        try:
            self.frame = self.renderer.render(self.width(), self.height(), now - self.epoch if self.live and not self.reduced_motion else 0,
                                              self.pointer, ripples, self.pane_rects(), self.dark)
        except Exception as exc:
            self.renderer.error = str(exc)
            self.renderer.available = False
            self.frame = QImage()
            self.timer.stop()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.tick)

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.frame.isNull():
            painter.drawImage(self.rect(), self.frame)
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QLinearGradient(0, 0, self.width(), self.height())
        for at, light, dark in [(0, "#b0e5ee", "#102939"), (.45, "#dae5f6", "#25253e"), (1, "#a4e5cd", "#13372f")]:
            base.setColorAt(at, QColor(dark if self.dark else light))
        painter.fillRect(self.rect(), base)
        for y, color in ((.3, "#ffffff"), (.76, "#53bfcc")):
            path = QPainterPath(QPointF(-100, self.height() * y))
            path.cubicTo(self.width() * .3, -100, self.width() * .65, self.height() * 1.2, self.width() + 100, self.height() * y)
            tint = QColor(color)
            tint.setAlpha(20 if self.dark else 40)
            painter.setPen(QPen(tint, 50))
            painter.drawPath(path)

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
        self.renderer.close()


class GlassPanel(QFrame):
    def __init__(self, scene, parent=None, material=0, radius=26):
        super().__init__(parent)
        self.scene, self.material, self.radius = scene, material, radius
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        scene.panels.append(self)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(.75, .75, -.75, -.75)
        gradient = QLinearGradient(0, 0, 0, self.height())
        rendered = self.scene.renderer.available and not self.scene.frame.isNull()
        if self.material:
            gradient.setColorAt(0, QColor(34, 103, 139, 30 if rendered else 235))
            gradient.setColorAt(1, QColor(8, 44, 68, 45 if rendered else 245))
        elif self.scene.dark:
            gradient.setColorAt(0, QColor(100, 153, 192, 24 if rendered else 55))
            gradient.setColorAt(1, QColor(17, 35, 53, 35 if rendered else 220))
        else:
            gradient.setColorAt(0, QColor(255, 255, 255, 45 if rendered else 210))
            gradient.setColorAt(1, QColor(237, 253, 255, 15 if rendered else 155))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 65 if self.scene.dark else 175), 1.2))
        painter.drawRoundedRect(rect, self.radius, self.radius)


class PocketPlayer(QWidget):
    """Original Aero motif, drawn as native vector artwork at any display scale."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(230, 205)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(min(self.width() / 260, self.height() / 220), min(self.width() / 260, self.height() / 220))
        for x, y, r, color in [(-94, -64, 28, "#68cddd"), (83, 60, 34, "#c3b6f3"), (91, -72, 13, "#a5ecd7")]:
            orb = QRadialGradient(x - r / 3, y - r / 3, r * 1.4)
            orb.setColorAt(0, QColor("#ffffff"))
            orb.setColorAt(.4, QColor(color))
            orb.setColorAt(1, QColor(color))
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(orb)
            painter.drawEllipse(QPointF(x, y), r, r)
        painter.rotate(-12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(31, 78, 99, 35))
        painter.drawRoundedRect(QRectF(-56, -84, 125, 185), 22, 22)
        shell = QLinearGradient(-60, -90, 65, 100)
        shell.setColorAt(0, QColor("#ffffff"))
        shell.setColorAt(.5, QColor("#f8fdff"))
        shell.setColorAt(1, QColor("#bfd2db"))
        painter.setBrush(shell)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawRoundedRect(QRectF(-63, -94, 126, 184), 20, 20)
        screen = QLinearGradient(0, -75, 0, -5)
        screen.setColorAt(0, QColor("#c9f2da"))
        screen.setColorAt(1, QColor("#74bfad"))
        painter.setBrush(screen)
        painter.setPen(QPen(QColor("#77a9a1"), 1))
        painter.drawRoundedRect(QRectF(-48, -77, 96, 65), 8, 8)
        painter.setPen(QColor("#316b61"))
        painter.drawText(QRectF(-40, -72, 82, 16), Qt.AlignmentFlag.AlignCenter, "NOW PLAYING")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#438d79"))
        for index, height in enumerate([12, 22, 30, 19, 35, 25, 16]):
            painter.drawRoundedRect(QRectF(-35 + index * 11, -20 - height, 6, height), 2, 2)
        wheel = QRadialGradient(-12, 22, 55)
        wheel.setColorAt(0, QColor("#ffffff"))
        wheel.setColorAt(1, QColor("#cfdee7"))
        painter.setBrush(wheel)
        painter.setPen(QPen(QColor("#b4cbd6"), 1))
        painter.drawEllipse(QPointF(0, 39), 37, 37)
        painter.setBrush(QColor("#f9fdff"))
        painter.drawEllipse(QPointF(0, 39), 14, 14)
        painter.setPen(QColor("#5e879b"))
        painter.drawText(QRectF(-26, 6, 52, 16), Qt.AlignmentFlag.AlignCenter, "MENU")
        painter.drawText(QRectF(-28, 58, 56, 16), Qt.AlignmentFlag.AlignCenter, "▶ Ⅱ")
