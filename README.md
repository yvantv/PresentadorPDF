# Dual-Screen PDF Presenter & Annotation Tool

A lightweight, powerful desktop application built with Python and PyQt6 designed for speakers, lecturers, and presenters. It provides a dual-screen presentation experience, interactive annotation tools (pen, highlighter, laser pointer), and a whiteboarding system that integrates seamlessly with PDF documents.

![Application Interface](https://via.placeholder.com/1200x680.png?text=PDF+Presenter+Interface) <!-- Replace with a screenshot of your app -->

---

## 🔑 Key Features

* **Dual-Screen Presenter Architecture:** Automatically detects secondary screens or projectors to render full-screen 1080p slides while keeping control tools accessible on your primary monitor.
* **Smart UI Layout:**
  * **Top Toolbar:** Quick access to drawing tools (Pen, Highlighter, Laser), dynamic color palette (1–4), stroke weight, screen wiper, and PDF page navigation.
  * **Left Sidebar:** Document management, view switcher (PDF Mode vs. Whiteboard Mode), new whiteboard creation, and output saving.
* **Vector Annotation Engine:** High-definition live drawing (smooth lines, alpha-blended highlighting, and an illuminated virtual laser pointer).
* **Multi-Whiteboard System:** Create blank $1920 \times 1080$ whiteboards on the fly without interrupting your presentation flow.
* **Export PDF with Embedded Notes & Whiteboards:** Save annotated slides and automatically attach newly created whiteboard pages to the end of the exported PDF.
* **Global Keyboard Shortcuts:** Operate presentation flows fluidly using quick keys without losing control focus.

---

## ⌨️ Global Keyboard Shortcuts

| Shortcut Key | Action |
| :--- | :--- |
| `Left` / `Up` / `PageUp` | Navigate to previous page or whiteboard |
| `Right` / `Down` / `PageDown` | Navigate to next page or whiteboard |
| `P` | Activate **Pen Tool** |
| `H` | Activate **Highlighter Tool** |
| `L` | Activate **Laser Pointer** |
| `C` | **Clear** current annotations |
| `1`, `2`, `3`, `4` | Select quick palette color 1, 2, 3, or 4 |
| `B` | Toggle or create a **Blank Whiteboard** |
| `Esc` or `0` | Return to **PDF View** |

---

## 🛠️ System Requirements & Dependencies

* Python 3.9+
* **PyQt6** (GUI framework)
* **PyMuPDF (fitz)** (PDF rendering and vector manipulation engine)

---

## 📥 Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/your-username/pdf-presenter.git](https://github.com/your-username/pdf-presenter.git)
   cd pdf-presenter
