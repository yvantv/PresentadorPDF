import sys
import os
import fitz  # PyMuPDF
from PyQt6.QtCore import Qt, QObject, QEvent, QSettings
from PyQt6.QtGui import QImage, QPixmap, QPen, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QFileDialog, QLabel,
    QColorDialog, QSpinBox, QMessageBox, QFrame
)

# -------------------------------------------------------------------
# 0. FILTRO GLOBAL DE EVENTOS DE TECLADO (Atajos Globales)
# -------------------------------------------------------------------
class KeyNavigationFilter(QObject):
    """Intercepta teclas de navegación, pizarras y herramientas sin importar el foco."""
    def __init__(self, ventana_control):
        super().__init__()
        self.control = ventana_control

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            
            # --- Navegación de páginas / pizarras ---
            if key in (Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Left):
                self.control.prev_page()
                return True
            elif key in (Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Right):
                self.control.next_page()
                return True
            
            # --- Pizarras en blanco (B) y Volver al PDF (Esc o 0) ---
            elif key == Qt.Key.Key_B:
                self.control.alternar_o_crear_pizarra()
                return True
            elif key in (Qt.Key.Key_Escape, Qt.Key.Key_0):
                self.control.volver_al_pdf()
                return True

            # --- Cambio rápido de Herramientas ---
            elif key == Qt.Key.Key_P:
                self.control.activar_lapiz()
                return True
            elif key == Qt.Key.Key_H:
                self.control.activar_resaltador()
                return True
            elif key == Qt.Key.Key_L:
                self.control.proyector.capa_anotaciones.set_modo('laser')
                self.control.actualizar_ui_herramientas()
                return True
            elif key == Qt.Key.Key_C:
                self.control.proyector.capa_anotaciones.limpiar_pantalla()
                return True

            # --- Selección rápida de los 4 colores de la paleta (Teclas 1, 2, 3, 4) ---
            elif key in (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4):
                idx = key - Qt.Key.Key_1
                self.control.seleccionar_color_paleta_por_indice(idx)
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
        
        self.setMouseTracking(True)
        self.modo = 'pen' 
        
        self.color_lapiz = QColor(230, 30, 30)
        self.color_resaltador = QColor(255, 235, 59)
        
        self.grosor_lapiz = 4
        self.grosor_resaltador = 24
        
        self.id_vista_actual = 0
        self.trazos_por_vista = {}
        
        self.trazo_actual = []
        self.pos_laser = None
        self.laser_presionado = False

    def tiene_anotaciones(self):
        for lista_trazos in self.trazos_por_vista.values():
            if len(lista_trazos) > 0:
                return True
        return False

    def reiniciar_anotaciones(self):
        self.trazos_por_vista.clear()
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
            self.unsetCursor()
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

    def leaveEvent(self, event):
        if self.modo == 'laser':
            self.pos_laser = None
            self.laser_presionado = False
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def enterEvent(self, event):
        if self.modo == 'laser':
            self.setCursor(Qt.CursorShape.BlankCursor)
        super().enterEvent(event)

    def mousePressEvent(self, event):
        if self.modo == 'laser':
            self.laser_presionado = True
            self.pos_laser = event.position()
            self.update()
        elif event.button() == Qt.MouseButton.LeftButton and self.modo in ['pen', 'highlighter']:
            self.trazo_actual = [event.position()]

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self.modo == 'laser':
            self.pos_laser = pos
            self.laser_presionado = bool(event.buttons() & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton))
            self.update()
        elif event.buttons() & Qt.MouseButton.LeftButton and self.modo in ['pen', 'highlighter']:
            self.trazo_actual.append(pos)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.modo == 'laser':
            self.laser_presionado = False
            self.update()
        elif event.button() == Qt.MouseButton.LeftButton and self.modo in ['pen', 'highlighter']:
            if self.id_vista_actual not in self.trazos_por_vista:
                self.trazos_por_vista[self.id_vista_actual] = []
            
            grosor = self.grosor_lapiz if self.modo == 'pen' else self.grosor_resaltador
            color = QColor(self.color_lapiz if self.modo == 'pen' else self.color_resaltador)

            self.trazos_por_vista[self.id_vista_actual].append({
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

        trazos_a_dibujar = self.trazos_por_vista.get(self.id_vista_actual, []).copy()
        
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

        if self.modo == 'laser' and self.pos_laser:
            if self.laser_presionado:
                painter.setBrush(QColor(255, 0, 0, 230))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(self.pos_laser, 14, 14)
                
                painter.setBrush(QColor(255, 255, 255, 255))
                painter.drawEllipse(self.pos_laser, 5, 5)
            else:
                painter.setBrush(QColor(255, 0, 0, 70))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(self.pos_laser, 10, 10)
                
                painter.setBrush(QColor(255, 255, 255, 120))
                painter.drawEllipse(self.pos_laser, 3, 3)

    def limpiar_pantalla(self):
        self.trazos_por_vista[self.id_vista_actual] = []
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
    TITULO_BASE = "Panel de Control - Presentador PDF HD (1920x1080)"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.TITULO_BASE)
        self.resize(1200, 680)

        self.doc_pdf = None
        self.ruta_pdf_actual = ""
        self.pagina_actual = 0
        
        self.pizarras = [] 
        self.indice_pizarra_actual = -1 

        self.proyector = VentanaProyeccion(ventana_control=self)
        self.settings = QSettings()

        self.colores_recientes = [
            QColor(230, 30, 30),    # Rojo
            QColor(255, 235, 59),   # Amarillo
            QColor(46, 125, 50),    # Verde
            QColor(33, 150, 243)    # Azul
        ]
        self.botones_paleta = []

        self.init_ui()
        self.configurar_segunda_pantalla()
        self.cargar_configuracion()
        self.actualizar_ui_herramientas()

    def actualizar_titulo_ventana(self):
        info_vista = ""
        if self.indice_pizarra_actual >= 0:
            info_vista = f" [PIZARRA {self.indice_pizarra_actual + 1}/{len(self.pizarras)}]"
        elif self.doc_pdf:
            info_vista = f" [Pág. {self.pagina_actual + 1}/{len(self.doc_pdf)}]"

        if self.ruta_pdf_actual:
            nombre_archivo = os.path.basename(self.ruta_pdf_actual)
            self.setWindowTitle(f"{self.TITULO_BASE} - [{nombre_archivo}]{info_vista}")
        else:
            self.setWindowTitle(f"{self.TITULO_BASE}{info_vista}")

    def init_ui(self):
        main_layout = QVBoxLayout()
        body_layout = QHBoxLayout()

        # ===============================================================
        # 1. BARRA SUPERIOR (Movimiento de páginas + Herramientas de Dibujo)
        # ===============================================================
        top_layout = QHBoxLayout()

        btn_prev = QPushButton("◀ Anterior")
        btn_prev.clicked.connect(self.prev_page)

        btn_next = QPushButton("Siguiente ▶")
        btn_next.clicked.connect(self.next_page)

        self.btn_pen = QPushButton("✏ Lápiz [P]")
        self.btn_pen.clicked.connect(self.activar_lapiz)

        self.btn_hl = QPushButton("🖍 Resaltador [H]")
        self.btn_hl.clicked.connect(self.activar_resaltador)

        self.btn_color = QPushButton("🎨 Color")
        self.btn_color.clicked.connect(self.elegir_color)

        lbl_grosor = QLabel("Grosor:")
        self.spin_grosor = QSpinBox()
        self.spin_grosor.setRange(1, 80)
        self.spin_grosor.setSuffix(" px")
        self.spin_grosor.valueChanged.connect(self.cambiar_grosor)

        self.btn_laser = QPushButton("🔴 Láser [L]")
        self.btn_laser.clicked.connect(lambda: (self.proyector.capa_anotaciones.set_modo('laser'), self.actualizar_ui_herramientas()))

        btn_clear = QPushButton("🗑 Limpiar [C]")
        btn_clear.clicked.connect(self.proyector.capa_anotaciones.limpiar_pantalla)

        # Ensamblar Barra Superior
        top_layout.addWidget(btn_prev)
        top_layout.addWidget(btn_next)
        top_layout.addSpacing(15)
        top_layout.addWidget(self.btn_pen)
        top_layout.addWidget(self.btn_hl)
        top_layout.addWidget(self.btn_color)

        # Paleta de 4 colores rápidos
        paleta_layout = QHBoxLayout()
        paleta_layout.setSpacing(2)
        for i in range(4):
            btn = QPushButton(str(i + 1))
            btn.setFixedSize(26, 26)
            btn.setToolTip(f"Usar color (Tecla {i+1})")
            btn.clicked.connect(lambda _, idx=i: self.seleccionar_color_paleta_por_indice(idx))
            self.botones_paleta.append(btn)
            paleta_layout.addWidget(btn)

        top_layout.addLayout(paleta_layout)
        top_layout.addWidget(lbl_grosor)
        top_layout.addWidget(self.spin_grosor)
        top_layout.addWidget(self.btn_laser)
        top_layout.addWidget(btn_clear)
        top_layout.addStretch()

        # ===============================================================
        # 2. BARRA LATERAL IZQUIERDA (Pizarras, Navegación de Vistas y Guardado)
        # ===============================================================
        sidebar_frame = QFrame()
        sidebar_frame.setFrameShape(QFrame.Shape.StyledPanel)
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(5, 10, 5, 10)
        sidebar_layout.setSpacing(10)

        btn_open = QPushButton("📂 Abrir PDF")
        btn_open.clicked.connect(self.abrir_pdf)

        btn_pdf_mode = QPushButton("📄 PDF [Esc]")
        btn_pdf_mode.clicked.connect(self.volver_al_pdf)

        btn_board = QPushButton("📋 Pizarra [B]")
        btn_board.setStyleSheet("background-color: #1565c0; color: white; font-weight: bold;")
        btn_board.clicked.connect(self.alternar_o_crear_pizarra)

        btn_new_board = QPushButton("➕ Nueva Pizarra")
        btn_new_board.clicked.connect(self.crear_nueva_pizarra)

        btn_save = QPushButton("💾 Guardar PDF")
        btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.guardar_pdf_anotado)

        sidebar_layout.addWidget(btn_open)
        sidebar_layout.addWidget(btn_pdf_mode)
        sidebar_layout.addWidget(btn_board)
        sidebar_layout.addWidget(btn_new_board)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(btn_save)

        # ===============================================================
        # 3. ÁREA PRINCIPAL (Previsualización de Pantalla)
        # ===============================================================
        self.lbl_preview = QLabel("Carga un archivo PDF para comenzar")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("border: 1px solid #444; background-color: #222; color: #fff;")
        self.lbl_preview.setScaledContents(True)
        self.lbl_preview.setMinimumSize(1, 1)

        body_layout.addWidget(sidebar_frame, stretch=0)
        body_layout.addWidget(self.lbl_preview, stretch=1)

        main_layout.addLayout(top_layout)
        main_layout.addLayout(body_layout, stretch=1)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    # -------------------------------------------------------------------
    # SISTEMA DE PIZARRAS BLANCAS Y VISTAS
    # -------------------------------------------------------------------
    def crear_nueva_pizarra(self):
        num_pizarra = len(self.pizarras) + 1
        id_pizarra = f"pizarra_{num_pizarra}"
        self.pizarras.append(id_pizarra)
        self.indice_pizarra_actual = len(self.pizarras) - 1
        self.renderizar_vista()

    def alternar_o_crear_pizarra(self):
        """Abre la siguiente pizarra o crea una nueva si no existe."""
        if not self.pizarras:
            self.crear_nueva_pizarra()
        else:
            if self.indice_pizarra_actual == -1:
                self.indice_pizarra_actual = 0
            else:
                self.indice_pizarra_actual += 1
                if self.indice_pizarra_actual >= len(self.pizarras):
                    self.indice_pizarra_actual = 0
            self.renderizar_vista()

    def volver_al_pdf(self):
        """Regresa a la lectura del PDF."""
        self.indice_pizarra_actual = -1
        self.renderizar_vista()

    def generar_pixmap_blanco(self):
        """Genera un lienzo blanco HD de 1920x1080 para la pizarra."""
        img = QImage(1920, 1080, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        return QPixmap.fromImage(img)

    def renderizar_vista(self):
        """Renderiza la vista actual (PDF o Pizarra en blanco)."""
        if self.indice_pizarra_actual >= 0:
            # --- MODO PIZARRA ---
            id_pizarra = self.pizarras[self.indice_pizarra_actual]
            self.proyector.capa_anotaciones.id_vista_actual = id_pizarra
            pixmap = self.generar_pixmap_blanco()
        else:
            # --- MODO PDF ---
            self.proyector.capa_anotaciones.id_vista_actual = self.pagina_actual
            if self.doc_pdf:
                page = self.doc_pdf.load_page(self.pagina_actual)
                rect_pdf = page.rect
                zoom_x = 1920 / rect_pdf.width
                zoom_y = 1080 / rect_pdf.height
                mat = fitz.Matrix(zoom_x, zoom_y)
                pix = page.get_pixmap(matrix=mat, alpha=False)

                fmt = QImage.Format.Format_RGB888
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                pixmap = QPixmap.fromImage(qimg)
            else:
                pixmap = self.generar_pixmap_blanco()

        self.proyector.mostrar_pixmap(pixmap)
        self.lbl_preview.setPixmap(pixmap)
        self.proyector.capa_anotaciones.update()
        self.actualizar_titulo_ventana()

    def next_page(self):
        if self.indice_pizarra_actual >= 0:
            if self.indice_pizarra_actual < len(self.pizarras) - 1:
                self.indice_pizarra_actual += 1
                self.renderizar_vista()
            else:
                self.volver_al_pdf()
        else:
            if self.doc_pdf and self.pagina_actual < len(self.doc_pdf) - 1:
                self.pagina_actual += 1
                self.renderizar_vista()
            elif self.pizarras:
                self.indice_pizarra_actual = 0
                self.renderizar_vista()

    def prev_page(self):
        if self.indice_pizarra_actual >= 0:
            if self.indice_pizarra_actual > 0:
                self.indice_pizarra_actual -= 1
                self.renderizar_vista()
            else:
                self.volver_al_pdf()
        else:
            if self.doc_pdf and self.pagina_actual > 0:
                self.pagina_actual -= 1
                self.renderizar_vista()

    # -------------------------------------------------------------------
    # HISTORIAL DE COLORES Y PALETA
    # -------------------------------------------------------------------
    def actualizar_paleta_ui(self):
        for i, color in enumerate(self.colores_recientes):
            btn = self.botones_paleta[i]
            texto_color = "black" if color.lightness() > 128 else "white"
            btn.setStyleSheet(
                f"background-color: {color.name()}; "
                f"color: {texto_color}; "
                f"border: 1px solid #666; "
                f"font-weight: bold; borderRadius: 3px;"
            )

    def registrar_nuevo_color(self, color):
        if color.name() in [c.name() for c in self.colores_recientes]:
            self.colores_recientes = [c for c in self.colores_recientes if c.name() != color.name()]
            self.colores_recientes.insert(0, color)
        else:
            self.colores_recientes.insert(0, color)
            self.colores_recientes = self.colores_recientes[:4]
        
        self.actualizar_paleta_ui()

    def seleccionar_color_paleta_por_indice(self, idx):
        if 0 <= idx < len(self.colores_recientes):
            color = self.colores_recientes[idx]
            self.proyector.capa_anotaciones.set_color(color)
            self.actualizar_ui_herramientas()

    def obtener_directorio_inicial(self):
        directorio_guardado = self.settings.value("ultimo_directorio", "")
        if directorio_guardado and os.path.exists(directorio_guardado):
            return directorio_guardado
        elif self.ruta_pdf_actual and os.path.exists(self.ruta_pdf_actual):
            return os.path.dirname(self.ruta_pdf_actual)
        return ""

    def guardar_directorio_inicial(self, ruta_archivo):
        if ruta_archivo:
            carpeta = os.path.dirname(ruta_archivo)
            self.settings.setValue("ultimo_directorio", carpeta)

    def cargar_configuracion(self):
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

        recientes = self.settings.value("colores_recientes")
        if recientes and isinstance(recientes, list) and len(recientes) == 4:
            self.colores_recientes = [QColor(hex_val) for hex_val in recientes]
        self.actualizar_paleta_ui()

        ultimo_pdf = self.settings.value("ultimo_pdf", "")
        if ultimo_pdf and os.path.exists(ultimo_pdf):
            try:
                self.doc_pdf = fitz.open(ultimo_pdf)
                self.ruta_pdf_actual = ultimo_pdf
                self.pagina_actual = 0
                self.pizarras.clear()
                self.indice_pizarra_actual = -1
                self.proyector.capa_anotaciones.reiniciar_anotaciones()
                self.renderizar_vista()
            except Exception as e:
                print(f"No se pudo cargar el último archivo: {e}")

    def guardar_configuracion(self):
        self.settings.setValue("geometria_ventana", self.saveGeometry())
        
        capa = self.proyector.capa_anotaciones
        self.settings.setValue("color_lapiz", capa.color_lapiz.name())
        self.settings.setValue("grosor_lapiz", capa.grosor_lapiz)
        self.settings.setValue("color_resaltador", capa.color_resaltador.name())
        self.settings.setValue("grosor_resaltador", capa.grosor_resaltador)
        
        hex_recientes = [c.name() for c in self.colores_recientes]
        self.settings.setValue("colores_recientes", hex_recientes)
        
        self.settings.setValue("ultimo_pdf", self.ruta_pdf_actual)

    def actualizar_ui_herramientas(self):
        capa = self.proyector.capa_anotaciones
        color = capa.get_color_actual()
        
        self.btn_color.setStyleSheet(
            f"background-color: {color.name()}; "
            f"color: {'black' if color.lightness() > 128 else 'white'}; "
            f"font-weight: bold;"
        )
        
        estilo_activo = "background-color: #005fb8; color: white; font-weight: bold;"
        self.btn_pen.setStyleSheet(estilo_activo if capa.modo == 'pen' else "")
        self.btn_hl.setStyleSheet(estilo_activo if capa.modo == 'highlighter' else "")
        self.btn_laser.setStyleSheet(estilo_activo if capa.modo == 'laser' else "")

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
            self.registrar_nuevo_color(nuevo_color)
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
                "El PDF actual o sus pizarras contienen trazos guardados.\n¿Deseas guardarlos antes de abrir un nuevo archivo?",
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
            self.pizarras.clear()
            self.indice_pizarra_actual = -1
            self.proyector.capa_anotaciones.reiniciar_anotaciones()
            self.renderizar_vista()

    # -------------------------------------------------------------------
    # GUARDADO COMPLETO (PDF + PIZARRAS COMO NUEVAS PÁGINAS)
    # -------------------------------------------------------------------
    def guardar_pdf_anotado(self):
        if not self.doc_pdf:
            return False

        dir_inicial = self.obtener_directorio_inicial()
        
        if self.ruta_pdf_actual:
            nombre_base = os.path.splitext(os.path.basename(self.ruta_pdf_actual))[0]
            nombre_sugerido_file = f"{nombre_base} - anotaciones.pdf"
            ruta_sugerida = os.path.join(dir_inicial, nombre_sugerido_file)
        else:
            ruta_sugerida = dir_inicial

        path_guardar, _ = QFileDialog.getSaveFileName(
            self, "Guardar PDF con Anotaciones y Pizarras", ruta_sugerida, "Archivos PDF (*.pdf)"
        )
        if not path_guardar:
            return False

        self.guardar_directorio_inicial(path_guardar)

        trazos_por_vista = self.proyector.capa_anotaciones.trazos_por_vista
        ancho_pantalla = self.proyector.capa_anotaciones.width()
        alto_pantalla = self.proyector.capa_anotaciones.height()

        # 1. Guardar anotaciones en las páginas del PDF original
        for num_pagina in range(len(self.doc_pdf)):
            pagina = self.doc_pdf.load_page(num_pagina)
            rect_pdf = pagina.rect

            trazos = trazos_por_vista.get(num_pagina, [])
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

        # 2. Agregar las Pizarras Blancas como páginas adicionales al final
        for id_pizarra in self.pizarras:
            nueva_pagina = self.doc_pdf.new_page(width=1920, height=1080)
            trazos = trazos_por_vista.get(id_pizarra, [])

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
                    nueva_pagina.draw_polyline(
                        puntos_pdf, color=color_fitz, width=grosor_pdf, lineCap=1, lineJoin=1
                    )
                elif trazo['modo'] == 'highlighter':
                    nueva_pagina.draw_polyline(
                        puntos_pdf, color=color_fitz, width=grosor_pdf, stroke_opacity=0.35, lineCap=1, lineJoin=1
                    )

        try:
            self.doc_pdf.save(path_guardar)
            QMessageBox.information(
                self, "Éxito", f"El archivo final (PDF + Pizarras agregadas) se guardó en:\n{path_guardar}"
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
    
    app.setOrganizationName("YvanTV")
    app.setApplicationName("PresentadorPDF")

    window = VentanaControl()
    
    nav_filter = KeyNavigationFilter(window)
    app.installEventFilter(nav_filter)

    window.show()
    sys.exit(app.exec())
