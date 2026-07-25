import sys
import os
import fitz  # PyMuPDF
from PyQt6.QtCore import Qt, QObject, QEvent, QSettings
from PyQt6.QtGui import QImage, QPixmap, QPen, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QFileDialog, QLabel,
    QColorDialog, QSpinBox, QMessageBox
)

# -------------------------------------------------------------------
# 0. FILTRO GLOBAL DE EVENTOS DE TECLADO
# -------------------------------------------------------------------
class KeyNavigationFilter(QObject):
    """Intercepta las teclas de navegación sin importar qué ventana o widget tenga el foco."""
    def __init__(self, ventana_control):
        super().__init__()
        self.control = ventana_control

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Left):
                self.control.prev_page()
                return True
            elif key in (Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Right):
                self.control.next_page()
                return True
        return super().eventFilter(obj, event)


# -------------------------------------------------------------------
# 1. CAPA DE DIBUJO Y LÁSER (Canvas Interactivo)
# -------------------------------------------------------------------
class LayerAnotaciones(QWidget):
    """Capa transparente superpuesta para trazar y manejar el láser."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        self.modo = 'pen' 
        
        # Colores independientes por defecto
        self.color_lapiz = QColor(230, 30, 30)
        self.color_resaltador = QColor(255, 235, 59)
        
        # Grosores independientes por defecto
        self.grosor_lapiz = 4
        self.grosor_resaltador = 24
        
        self.trazos_por_pagina = {}
        self.pagina_actual = 0
        
        self.trazo_actual = []
        self.pos_laser = None

    def tiene_anotaciones(self):
        for lista_trazos in self.trazos_por_pagina.values():
            if len(lista_trazos) > 0:
                return True
        return False

    def reiniciar_anotaciones(self):
        self.trazos_por_pagina.clear()
        self.trazo_actual.clear()
        self.update()

    def get_color_actual(self):
        if self.modo == 'highlighter':
            return self.color_resaltador
        return self.color_lapiz

    def set_modo(self, nuevo_modo):
        self.modo = nuevo_modo
        if self.modo == 'laser':
            self.setCursor(Qt.CursorShape.BlankCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def set_color(self, nuevo_color):
        if nuevo_color.isValid():
            if self.modo == 'highlighter':
                self.color_resaltador = nuevo_color
            else:
                self.color_lapiz = nuevo_color

    def set_grosor(self, nuevo_grosor):
        if self.modo == 'highlighter':
            self.grosor_resaltador = nuevo_grosor
        else:
            self.grosor_lapiz = nuevo_grosor

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
            color = QColor(self.color_lapiz if self.modo == 'pen' else self.color_resaltador)

            self.trazos_por_pagina[self.pagina_actual].append({
                'modo': self.modo,
                'puntos': list(self.trazo_actual),
                'color': color,
                'grosor': grosor
            })
            self.trazo_actual = []
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        grosor_actual = self.grosor_lapiz if self.modo == 'pen' else self.grosor_resaltador
        color_actual = self.color_lapiz if self.modo == 'pen' else self.color_resaltador

        trazos_a_dibujar = self.trazos_por_pagina.get(self.pagina_actual, []).copy()
        
        if self.trazo_actual:
            trazos_a_dibujar.append({
                'modo': self.modo,
                'puntos': self.trazo_actual,
                'color': color_actual,
                'grosor': grosor_actual
            })

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
                color_resaltador = QColor(color_base.red(), color_base.green(), color_base.blue(), 100)
                pen.setColor(color_resaltador)
                pen.setWidth(grosor)
            
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        # -----------------------------------------------------------
        # DIBUJO DEL LÁSER (Menos transparente / Más visible)
        # -----------------------------------------------------------
        if self.modo == 'laser' and self.pos_laser:
            # Halo exterior rojo con mayor opacidad (200 de 255 = ~80%)
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.pos_laser, 12, 12)
            
            # Centro blanco brillante e intenso
            painter.setBrush(QColor(255, 255, 255, 255))
            painter.drawEllipse(self.pos_laser, 4, 4)

    def limpiar_pantalla(self):
        self.trazos_por_pagina[self.pagina_actual] = []
        self.update()


# -------------------------------------------------------------------
# 2. VENTANA DE PROYECCIÓN (Pantalla Secundaria / Fullscreen)
# -------------------------------------------------------------------
class VentanaProyeccion(QWidget):
    def __init__(self, ventana_control=None):
        super().__init__()
        self.control = ventana_control
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
        self.resize(1050, 650)

        self.doc_pdf = None
        self.ruta_pdf_actual = ""
        self.pagina_actual = 0
        self.proyector = VentanaProyeccion(ventana_control=self)

        self.settings = QSettings()

        self.init_ui()
        self.configurar_segunda_pantalla()
        self.cargar_configuracion()
        self.actualizar_ui_herramientas()

    def init_ui(self):
        main_layout = QVBoxLayout()
        toolbar_layout = QHBoxLayout()

        btn_open = QPushButton("📂 Abrir PDF")
        btn_open.clicked.connect(self.abrir_pdf)

        btn_prev = QPushButton("◀ Anterior")
        btn_prev.clicked.connect(self.prev_page)

        btn_next = QPushButton("Siguiente ▶")
        btn_next.clicked.connect(self.next_page)

        btn_pen = QPushButton("✏ Lápiz")
        btn_pen.clicked.connect(self.activar_lapiz)

        btn_hl = QPushButton("🖍 Resaltador")
        btn_hl.clicked.connect(self.activar_resaltador)

        self.btn_color = QPushButton("🎨 Color")
        self.btn_color.clicked.connect(self.elegir_color)

        lbl_grosor = QLabel("Grosor:")
        self.spin_grosor = QSpinBox()
        self.spin_grosor.setRange(1, 80)
        self.spin_grosor.setSuffix(" px")
        self.spin_grosor.valueChanged.connect(self.cambiar_grosor)

        btn_laser = QPushButton("🔴 Láser")
        btn_laser.clicked.connect(lambda: self.proyector.capa_anotaciones.set_modo('laser'))

        btn_clear = QPushButton("🗑 Limpiar")
        btn_clear.clicked.connect(self.proyector.capa_anotaciones.limpiar_pantalla)

        btn_save = QPushButton("💾 Guardar PDF")
        btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.guardar_pdf_anotado)

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

        self.lbl_preview = QLabel("Carga un archivo PDF para comenzar")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("border: 1px solid #444; background-color: #222; color: #fff;")
        
        self.lbl_preview.setScaledContents(True)
        self.lbl_preview.setMinimumSize(1, 1)

        main_layout.addLayout(toolbar_layout)
        main_layout.addWidget(self.lbl_preview, stretch=1)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    # -------------------------------------------------------------------
    # MÉTODOS DE PERSISTENCIA Y CARPETA INICIAL
    # -------------------------------------------------------------------
    def obtener_directorio_inicial(self):
        """Retorna la última carpeta guardada o la ruta del último PDF."""
        directorio_guardado = self.settings.value("ultimo_directorio", "")
        if directorio_guardado and os.path.exists(directorio_guardado):
            return directorio_guardado
        elif self.ruta_pdf_actual and os.path.exists(self.ruta_pdf_actual):
            return os.path.dirname(self.ruta_pdf_actual)
        return ""

    def guardar_directorio_inicial(self, ruta_archivo):
        """Guarda la carpeta contenedora del archivo seleccionado."""
        if ruta_archivo:
            carpeta = os.path.dirname(ruta_archivo)
            self.settings.setValue("ultimo_directorio", carpeta)

    def cargar_configuracion(self):
        """Carga la posición de la ventana, herramientas y el último PDF al iniciar."""
        geometria = self.settings.value("geometria_ventana")
        if geometria:
            self.restoreGeometry(geometria)

        capa = self.proyector.capa_anotaciones
        
        color_lapiz = self.settings.value("color_lapiz", "#E61E1E")
        capa.color_lapiz = QColor(color_lapiz)
        capa.grosor_lapiz = int(self.settings.value("grosor_lapiz", 4))

        color_resaltador = self.settings.value("color_resaltador", "#EBEB3B")
        capa.color_resaltador = QColor(color_resaltador)
        capa.grosor_resaltador = int(self.settings.value("grosor_resaltador", 24))

        ultimo_pdf = self.settings.value("ultimo_pdf", "")
        if ultimo_pdf and os.path.exists(ultimo_pdf):
            try:
                self.doc_pdf = fitz.open(ultimo_pdf)
                self.ruta_pdf_actual = ultimo_pdf
                self.pagina_actual = 0
                self.proyector.capa_anotaciones.reiniciar_anotaciones()
                self.renderizar_pagina()
            except Exception as e:
                print(f"No se pudo cargar el último archivo: {e}")

    def guardar_configuracion(self):
        """Guarda la posición de la ventana, herramientas y ruta del archivo."""
        self.settings.setValue("geometria_ventana", self.saveGeometry())
        
        capa = self.proyector.capa_anotaciones
        self.settings.setValue("color_lapiz", capa.color_lapiz.name())
        self.settings.setValue("grosor_lapiz", capa.grosor_lapiz)
        self.settings.setValue("color_resaltador", capa.color_resaltador.name())
        self.settings.setValue("grosor_resaltador", capa.grosor_resaltador)
        
        self.settings.setValue("ultimo_pdf", self.ruta_pdf_actual)

    def actualizar_ui_herramientas(self):
        capa = self.proyector.capa_anotaciones
        color = capa.get_color_actual()
        
        self.btn_color.setStyleSheet(
            f"background-color: {color.name()}; "
            f"color: {'black' if color.lightness() > 128 else 'white'}; "
            f"font-weight: bold;"
        )
        
        grosor = capa.grosor_resaltador if capa.modo == 'highlighter' else capa.grosor_lapiz
        self.spin_grosor.blockSignals(True)
        self.spin_grosor.setValue(grosor)
        self.spin_grosor.blockSignals(False)

    def activar_lapiz(self):
        self.proyector.capa_anotaciones.set_modo('pen')
        self.actualizar_ui_herramientas()

    def activar_resaltador(self):
        self.proyector.capa_anotaciones.set_modo('highlighter')
        self.actualizar_ui_herramientas()

    def elegir_color(self):
        capa = self.proyector.capa_anotaciones
        color_inicial = capa.get_color_actual()
        nuevo_color = QColorDialog.getColor(color_inicial, self, "Selecciona un Color")
        
        if nuevo_color.isValid():
            capa.set_color(nuevo_color)
            self.actualizar_ui_herramientas()

    def cambiar_grosor(self, valor):
        self.proyector.capa_anotaciones.set_grosor(valor)

    def closeEvent(self, event):
        self.guardar_configuracion()
        if self.proyector:
            self.proyector.close()
        event.accept()

    def configurar_segunda_pantalla(self):
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
        if self.doc_pdf and self.proyector.capa_anotaciones.tiene_anotaciones():
            respuesta = QMessageBox.question(
                self,
                "Anotaciones no guardadas",
                "El PDF actual tiene anotaciones realizadas.\n¿Deseas guardarlas antes de abrir un nuevo archivo?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )

            if respuesta == QMessageBox.StandardButton.Save:
                guardado_exitoso = self.guardar_pdf_anotado()
                if not guardado_exitoso:
                    return
            elif respuesta == QMessageBox.StandardButton.Cancel:
                return

        dir_inicial = self.obtener_directorio_inicial()
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar PDF", dir_inicial, "Archivos PDF (*.pdf)"
        )
        if path:
            self.doc_pdf = fitz.open(path)
            self.ruta_pdf_actual = path
            self.guardar_directorio_inicial(path)
            self.pagina_actual = 0
            self.proyector.capa_anotaciones.reiniciar_anotaciones()
            self.renderizar_pagina()

    def renderizar_pagina(self):
        if not self.doc_pdf:
            return

        page = self.doc_pdf.load_page(self.pagina_actual)
        rect_pdf = page.rect
        
        zoom_x = 1920 / rect_pdf.width
        zoom_y = 1080 / rect_pdf.height
        mat = fitz.Matrix(zoom_x, zoom_y)
        
        pix = page.get_pixmap(matrix=mat, alpha=False)

        fmt = QImage.Format.Format_RGB888
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        pixmap = QPixmap.fromImage(qimg)

        self.proyector.capa_anotaciones.pagina_actual = self.pagina_actual
        self.proyector.mostrar_pixmap(pixmap)
        self.lbl_preview.setPixmap(pixmap)
        self.proyector.capa_anotaciones.update()

    def next_page(self):
        if self.doc_pdf and self.pagina_actual < len(self.doc_pdf) - 1:
            self.pagina_actual += 1
            self.renderizar_pagina()

    def prev_page(self):
        if self.doc_pdf and self.pagina_actual > 0:
            self.pagina_actual -= 1
            self.renderizar_pagina()

    # -------------------------------------------------------------------
    # GUARDAR CON SUFIJO "anotaciones"
    # -------------------------------------------------------------------
    def guardar_pdf_anotado(self):
        if not self.doc_pdf:
            return False

        dir_inicial = self.obtener_directorio_inicial()
        
        # Genera el nombre sugerido: "NombreOriginal - anotaciones.pdf"
        if self.ruta_pdf_actual:
            nombre_base = os.path.splitext(os.path.basename(self.ruta_pdf_actual))[0]
            nombre_sugerido_file = f"{nombre_base} - anotaciones.pdf"
            ruta_sugerida = os.path.join(dir_inicial, nombre_sugerido_file)
        else:
            ruta_sugerida = dir_inicial

        path_guardar, _ = QFileDialog.getSaveFileName(
            self, "Guardar PDF con Anotaciones", ruta_sugerida, "Archivos PDF (*.pdf)"
        )
        if not path_guardar:
            return False

        self.guardar_directorio_inicial(path_guardar)

        trazos_por_pagina = self.proyector.capa_anotaciones.trazos_por_pagina
        ancho_pantalla = self.proyector.capa_anotaciones.width()
        alto_pantalla = self.proyector.capa_anotaciones.height()

        for num_pagina in range(len(self.doc_pdf)):
            pagina = self.doc_pdf.load_page(num_pagina)
            rect_pdf = pagina.rect

            trazos = trazos_por_pagina.get(num_pagina, [])
            if not trazos:
                continue

            escala_x = rect_pdf.width / ancho_pantalla
            escala_y = rect_pdf.height / alto_pantalla

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
                self, "Éxito", f"El nuevo PDF con anotaciones se guardó en:\n{path_guardar}"
            )
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el archivo:\n{str(e)}")
            return False


# -------------------------------------------------------------------
# PUNTO DE ENTRADA DE LA APLICACIÓN
# -------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    app.setOrganizationName("MiEmpresa")
    app.setApplicationName("PresentadorPDF")

    window = VentanaControl()
    
    nav_filter = KeyNavigationFilter(window)
    app.installEventFilter(nav_filter)

    window.show()
    sys.exit(app.exec())