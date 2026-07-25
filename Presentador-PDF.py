import sys
import fitz  # PyMuPDF para manipular y renderizar el PDF
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap, QPen, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QFileDialog, QLabel,
    QColorDialog, QSpinBox, QMessageBox
)

# -------------------------------------------------------------------
# 1. CAPA DE DIBUJO Y LÁSER (Canvas Interactivo)
# -------------------------------------------------------------------
class LayerAnotaciones(QWidget):
    """Capa transparente superpuesta para trazar y manejar el láser."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        # Modo activo: 'pen', 'highlighter', 'laser'
        self.modo = 'pen' 
        self.color_actual = QColor(230, 30, 30)  # Color por defecto (Rojo)
        
        # Grosores independientes por defecto
        self.grosor_lapiz = 4
        self.grosor_resaltador = 24
        
        # Almacenamiento de trazos por página: {num_pagina: [lista_de_trazos]}
        self.trazos_por_pagina = {}
        self.pagina_actual = 0
        
        self.trazo_actual = []
        self.pos_laser = None

    def set_modo(self, nuevo_modo):
        self.modo = nuevo_modo
        if self.modo == 'laser':
            self.setCursor(Qt.CursorShape.BlankCursor)  # Oculta el cursor estándar
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def set_color(self, nuevo_color):
        if nuevo_color.isValid():
            self.color_actual = nuevo_color

    def set_grosor(self, nuevo_grosor):
        if self.modo == 'pen':
            self.grosor_lapiz = nuevo_grosor
        elif self.modo == 'highlighter':
            self.grosor_resaltador = nuevo_grosor

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.modo in ['pen', 'highlighter']:
                self.trazo_actual = [event.position()]

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self.modo == 'laser':
            self.pos_laser = pos
            self.update()
        elif event.buttons() & Qt.MouseButton.LeftButton and self.modo in ['pen', 'highlighter']:
            self.trazo_actual.append(pos)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.modo in ['pen', 'highlighter']:
            if self.pagina_actual not in self.trazos_por_pagina:
                self.trazos_por_pagina[self.pagina_actual] = []
            
            grosor = self.grosor_lapiz if self.modo == 'pen' else self.grosor_resaltador

            # Guardar trazo con su color, grosor y coordenadas
            self.trazos_por_pagina[self.pagina_actual].append({
                'modo': self.modo,
                'puntos': list(self.trazo_actual),
                'color': QColor(self.color_actual),
                'grosor': grosor
            })
            self.trazo_actual = []
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Preparar lista de trazos para renderizar
        grosor_actual = self.grosor_lapiz if self.modo == 'pen' else self.grosor_resaltador
        trazos_a_dibujar = self.trazos_por_pagina.get(self.pagina_actual, []).copy()
        
        if self.trazo_actual:
            trazos_a_dibujar.append({
                'modo': self.modo,
                'puntos': self.trazo_actual,
                'color': self.color_actual,
                'grosor': grosor_actual
            })

        # 2. Dibujar Trazos Vectoriales
        for trazo in trazos_a_dibujar:
            if not trazo['puntos']:
                continue
            
            path = QPainterPath()
            path.moveTo(trazo['puntos'][0])
            for pt in trazo['puntos'][1:]:
                path.lineTo(pt)

            pen = QPen()
            color_base = trazo['color']
            grosor = trazo['grosor']

            if trazo['modo'] == 'pen':
                pen.setColor(color_base)
                pen.setWidth(grosor)
            elif trazo['modo'] == 'highlighter':
                # Color semi-transparente (Alpha = 100)
                color_resaltador = QColor(color_base.red(), color_base.green(), color_base.blue(), 100)
                pen.setColor(color_resaltador)
                pen.setWidth(grosor)
            
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        # 3. Dibujar Puntero Láser
        if self.modo == 'laser' and self.pos_laser:
            painter.setBrush(QColor(255, 0, 0, 80))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.pos_laser, 12, 12)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(self.pos_laser, 4, 4)

    def limpiar_pantalla(self):
        self.trazos_por_pagina[self.pagina_actual] = []
        self.update()


# -------------------------------------------------------------------
# 2. VENTANA DE PROYECCIÓN (Pantalla Secundaria / Fullscreen)
# -------------------------------------------------------------------
class VentanaProyeccion(QWidget):
    """Ventana sin bordes optimizada para mostrarse en el proyector."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proyección PDF HD")
        self.setStyleSheet("background-color: black;")
        
        self.label_pdf = QLabel(self)
        self.label_pdf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.capa_anotaciones = LayerAnotaciones(self)

    def resizeEvent(self, event):
        self.label_pdf.setGeometry(0, 0, self.width(), self.height())
        self.capa_anotaciones.setGeometry(0, 0, self.width(), self.height())

    def mostrar_pixmap(self, pixmap):
        self.label_pdf.setPixmap(pixmap)


# -------------------------------------------------------------------
# 3. VENTANA DE CONTROL (Monitor Principal)
# -------------------------------------------------------------------
class VentanaControl(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Panel de Control - Presentador PDF HD (1920x1080)")
        self.resize(1000, 650)

        self.doc_pdf = None
        self.pagina_actual = 0
        self.proyector = VentanaProyeccion()

        self.init_ui()
        self.configurar_segunda_pantalla()

    def init_ui(self):
        main_layout = QVBoxLayout()
        toolbar_layout = QHBoxLayout()

        # Botones de Archivo y Navegación
        btn_open = QPushButton("📂 Abrir PDF")
        btn_open.clicked.connect(self.abrir_pdf)

        btn_prev = QPushButton("◀ Anterior")
        btn_prev.clicked.connect(self.prev_page)

        btn_next = QPushButton("Siguiente ▶")
        btn_next.clicked.connect(self.next_page)

        # Botones de Herramientas
        btn_pen = QPushButton("✏ Lápiz")
        btn_pen.clicked.connect(self.activar_lapiz)

        btn_hl = QPushButton("🖍 Resaltador")
        btn_hl.clicked.connect(self.activar_resaltador)

        self.btn_color = QPushButton("🎨 Color")
        self.btn_color.setStyleSheet("background-color: #E61E1E; color: white; font-weight: bold;")
        self.btn_color.clicked.connect(self.elegir_color)

        lbl_grosor = QLabel("Grosor:")
        self.spin_grosor = QSpinBox()
        self.spin_grosor.setRange(1, 80)
        self.spin_grosor.setValue(4)
        self.spin_grosor.setSuffix(" px")
        self.spin_grosor.valueChanged.connect(self.cambiar_grosor)

        btn_laser = QPushButton("🔴 Láser")
        btn_laser.clicked.connect(lambda: self.proyector.capa_anotaciones.set_modo('laser'))

        btn_clear = QPushButton("🗑 Limpiar")
        btn_clear.clicked.connect(self.proyector.capa_anotaciones.limpiar_pantalla)

        btn_save = QPushButton("💾 Guardar PDF")
        btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.guardar_pdf_anotado)

        # Ensamblar Toolbar
        toolbar_layout.addWidget(btn_open)
        toolbar_layout.addWidget(btn_prev)
        toolbar_layout.addWidget(btn_next)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(btn_pen)
        toolbar_layout.addWidget(btn_hl)
        toolbar_layout.addWidget(self.btn_color)
        toolbar_layout.addWidget(lbl_grosor)
        toolbar_layout.addWidget(self.spin_grosor)
        toolbar_layout.addWidget(btn_laser)
        toolbar_layout.addWidget(btn_clear)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(btn_save)

        # Vista Previa para el Moderador
        self.lbl_preview = QLabel("Carga un archivo PDF para comenzar")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("border: 1px solid #444; background-color: #222; color: #fff;")

        main_layout.addLayout(toolbar_layout)
        main_layout.addWidget(self.lbl_preview, stretch=1)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def configurar_segunda_pantalla(self):
        """Mueve automáticamente la ventana de proyección al segundo monitor."""
        screens = QApplication.screens()
        if len(screens) > 1:
            segunda_pantalla = screens[1]
            geo = segunda_pantalla.geometry()
            self.proyector.move(geo.x(), geo.y())
            self.proyector.showFullScreen()
        else:
            self.proyector.resize(960, 540)
            self.proyector.show()

    def abrir_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar PDF", "", "Archivos PDF (*.pdf)")
        if path:
            self.doc_pdf = fitz.open(path)
            self.pagina_actual = 0
            self.renderizar_pagina()

    def renderizar_pagina(self):
        """Garantiza la escala y alta fidelidad en renderizado HD (1920x1080)."""
        if not self.doc_pdf:
            return

        page = self.doc_pdf.load_page(self.pagina_actual)
        rect_pdf = page.rect
        
        # Forzar matriz de resolución hacia Full HD (1920x1080)
        zoom_x = 1920 / rect_pdf.width
        zoom_y = 1080 / rect_pdf.height
        mat = fitz.Matrix(zoom_x, zoom_y)
        
        pix = page.get_pixmap(matrix=mat, alpha=False)

        fmt = QImage.Format.Format_RGB888
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        pixmap = QPixmap.fromImage(qimg)

        # Asignar a pantallas
        self.proyector.capa_anotaciones.pagina_actual = self.pagina_actual
        self.proyector.mostrar_pixmap(pixmap)
        self.lbl_preview.setPixmap(pixmap.scaled(self.lbl_preview.size(), Qt.AspectRatioMode.KeepAspectRatio))
        self.proyector.capa_anotaciones.update()

    def activar_lapiz(self):
        self.proyector.capa_anotaciones.set_modo('pen')
        self.spin_grosor.setValue(self.proyector.capa_anotaciones.grosor_lapiz)

    def activar_resaltador(self):
        self.proyector.capa_anotaciones.set_modo('highlighter')
        self.spin_grosor.setValue(self.proyector.capa_anotaciones.grosor_resaltador)

    def elegir_color(self):
        color_inicial = self.proyector.capa_anotaciones.color_actual
        nuevo_color = QColorDialog.getColor(color_inicial, self, "Selecciona un Color")
        if nuevo_color.isValid():
            self.proyector.capa_anotaciones.set_color(nuevo_color)
            self.btn_color.setStyleSheet(
                f"background-color: {nuevo_color.name()}; "
                f"color: {'black' if nuevo_color.lightness() > 128 else 'white'}; "
                f"font-weight: bold;"
            )

    def cambiar_grosor(self, valor):
        self.proyector.capa_anotaciones.set_grosor(valor)

    def next_page(self):
        if self.doc_pdf and self.pagina_actual < len(self.doc_pdf) - 1:
            self.pagina_actual += 1
            self.renderizar_pagina()

    def prev_page(self):
        if self.doc_pdf and self.pagina_actual > 0:
            self.pagina_actual -= 1
            self.renderizar_pagina()

    def guardar_pdf_anotado(self):
        """Redimensiona el PDF a 1920x1080 pt nativos y fusiona las trazas vectoriales."""
        if not self.doc_pdf:
            return

        path_guardar, _ = QFileDialog.getSaveFileName(
            self, "Guardar PDF con Anotaciones", "", "Archivos PDF (*.pdf)"
        )
        if not path_guardar:
            return

        trazos_por_pagina = self.proyector.capa_anotaciones.trazos_por_pagina
        ancho_pantalla = self.proyector.capa_anotaciones.width()
        alto_pantalla = self.proyector.capa_anotaciones.height()

        for num_pagina in range(len(self.doc_pdf)):
            pagina = self.doc_pdf.load_page(num_pagina)
            
            # --- Forzar tamaño de lienzo nativo HD (1920x1080 pt) ---
            rect_hd = fitz.Rect(0, 0, 1920, 1080)
            pagina.set_cropbox(rect_hd)
            pagina.set_mediabox(rect_hd)

            trazos = trazos_por_pagina.get(num_pagina, [])
            if not trazos:
                continue

            escala_x = 1920 / ancho_pantalla
            escala_y = 1080 / alto_pantalla

            for trazo in trazos:
                puntos_pantalla = trazo['puntos']
                if len(puntos_pantalla) < 2:
                    continue

                puntos_pdf = [
                    fitz.Point(pt.x() * escala_x, pt.y() * escala_y)
                    for pt in puntos_pantalla
                ]

                color_q = trazo['color']
                color_fitz = (
                    color_q.red() / 255.0,
                    color_q.green() / 255.0,
                    color_q.blue() / 255.0
                )
                grosor_pdf = trazo['grosor'] * escala_x

                if trazo['modo'] == 'pen':
                    pagina.draw_polyline(
                        puntos_pdf, color=color_fitz, width=grosor_pdf, lineCap=1, lineJoin=1
                    )
                elif trazo['modo'] == 'highlighter':
                    pagina.draw_polyline(
                        puntos_pdf, color=color_fitz, width=grosor_pdf, stroke_opacity=0.35, lineCap=1, lineJoin=1
                    )

        try:
            self.doc_pdf.save(path_guardar)
            QMessageBox.information(
                self, "Éxito", f"El nuevo PDF HD con anotaciones se guardó en:\n{path_guardar}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el archivo:\n{str(e)}")


# -------------------------------------------------------------------
# PUNTO DE ENTRADA DE LA APLICACIÓN
# -------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VentanaControl()
    window.show()
    sys.exit(app.exec())