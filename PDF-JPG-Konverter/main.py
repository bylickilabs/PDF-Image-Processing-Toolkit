from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

import pymupdf
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "PDF zu JPG Konverter"
APP_VERSION = "1.0.0"


def safe_name(value: str) -> str:
    """Erzeugt einen Windows-tauglichen Dateinamen."""
    value = re.sub(r'[<>:"/\\|?*]+', "_", value)
    value = value.strip().strip(".")
    return value or "PDF"


def unique_directory(path: Path) -> Path:
    """Liefert einen noch nicht vorhandenen Ordnerpfad."""
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = path.with_name(f"{path.name}_{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


class PdfDropList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(180)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            pdfs = [
                Path(url.toLocalFile())
                for url in event.mimeData().urls()
                if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
            ]
            if pdfs:
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        pdfs = [
            str(Path(url.toLocalFile()).resolve())
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
        ]
        if pdfs:
            self.files_dropped.emit(pdfs)
            event.acceptProposedAction()
        else:
            event.ignore()


class ConversionWorker(QObject):
    progress = Signal(int, int)
    current_file = Signal(str)
    log = Signal(str)
    finished = Signal(int, int, str)
    failed = Signal(str)

    def __init__(
        self,
        pdf_files: list[str],
        output_root: str,
        dpi: int,
        quality: int,
        prefix: str,
        start_number: int,
        own_folder: bool,
        global_numbering: bool,
        overwrite: bool,
        password: str,
    ) -> None:
        super().__init__()
        self.pdf_files = pdf_files
        self.output_root = Path(output_root)
        self.dpi = dpi
        self.quality = quality
        self.prefix = safe_name(prefix or "Seite")
        self.start_number = start_number
        self.own_folder = own_folder
        self.global_numbering = global_numbering
        self.overwrite = overwrite
        self.password = password
        self._stop_requested = False

    @Slot()
    def stop(self) -> None:
        self._stop_requested = True

    def _count_pages(self) -> int:
        total = 0
        for filename in self.pdf_files:
            try:
                doc = pymupdf.open(filename)
                if doc.needs_pass and (not self.password or not doc.authenticate(self.password)):
                    self.log.emit(
                        f"Übersprungen (Passwort erforderlich oder falsch): {filename}"
                    )
                    doc.close()
                    continue
                total += doc.page_count
                doc.close()
            except Exception as exc:
                self.log.emit(f"Seitenzahl konnte nicht gelesen werden: {filename} | {exc}")
        return total

    def _target_directory(self, pdf_path: Path) -> Path:
        if self.own_folder:
            target = self.output_root / safe_name(pdf_path.stem)
            if not self.overwrite:
                target = unique_directory(target)
        else:
            target = self.output_root

        target.mkdir(parents=True, exist_ok=True)
        return target

    @Slot()
    def run(self) -> None:
        try:
            self.output_root.mkdir(parents=True, exist_ok=True)

            total_pages = self._count_pages()
            if total_pages <= 0:
                self.failed.emit("Es wurden keine konvertierbaren PDF-Seiten gefunden.")
                return

            completed_pages = 0
            converted_pages = 0
            failed_pdfs = 0
            global_counter = self.start_number

            self.progress.emit(0, total_pages)

            for filename in self.pdf_files:
                if self._stop_requested:
                    self.log.emit("Vorgang wurde abgebrochen.")
                    break

                pdf_path = Path(filename)
                self.current_file.emit(pdf_path.name)
                self.log.emit(f"Starte: {pdf_path}")

                try:
                    doc = pymupdf.open(pdf_path)

                    if doc.needs_pass:
                        if not self.password or not doc.authenticate(self.password):
                            failed_pdfs += 1
                            self.log.emit(
                                f"FEHLER: '{pdf_path.name}' ist passwortgeschützt. "
                                "Kein gültiges Passwort angegeben."
                            )
                            doc.close()
                            continue

                    target_dir = self._target_directory(pdf_path)
                    page_counter = self.start_number

                    for page_index in range(doc.page_count):
                        if self._stop_requested:
                            break

                        page = doc.load_page(page_index)
                        pix = page.get_pixmap(
                            dpi=self.dpi,
                            colorspace=pymupdf.csRGB,
                            alpha=False,
                        )

                        number = global_counter if self.global_numbering else page_counter

                        if self.own_folder:
                            filename_base = f"{self.prefix}_{number:04d}.jpg"
                        else:
                            # Wenn alle PDFs in denselben Ordner gehen, bleibt der PDF-Name
                            # im JPG-Dateinamen erhalten, damit nichts kollidiert.
                            filename_base = (
                                f"{safe_name(pdf_path.stem)}_{self.prefix}_{number:04d}.jpg"
                            )

                        output_file = target_dir / filename_base

                        if output_file.exists() and not self.overwrite:
                            stem = output_file.stem
                            suffix_counter = 2
                            while output_file.exists():
                                output_file = target_dir / (
                                    f"{stem}_{suffix_counter}{output_file.suffix}"
                                )
                                suffix_counter += 1

                        pix.save(str(output_file), jpg_quality=self.quality)
                        del pix

                        converted_pages += 1
                        completed_pages += 1
                        page_counter += 1
                        global_counter += 1

                        self.progress.emit(completed_pages, total_pages)
                        self.log.emit(
                            f"  Seite {page_index + 1}/{doc.page_count} -> {output_file.name}"
                        )

                    doc.close()

                except Exception as exc:
                    failed_pdfs += 1
                    self.log.emit(f"FEHLER bei '{pdf_path.name}': {exc}")

            status = "abgebrochen" if self._stop_requested else "abgeschlossen"
            self.finished.emit(converted_pages, failed_pdfs, status)

        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.thread: QThread | None = None
        self.worker: ConversionWorker | None = None
        self.pdf_paths: list[str] = []

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(920, 720)
        self.setMinimumSize(780, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        title = QLabel("PDF ZU JPG KONVERTER")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(title)

        subtitle = QLabel(
            "Jede PDF-Seite wird als einzelnes JPG exportiert und eindeutig nummeriert."
        )
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        files_group = QGroupBox("PDF-Dokumente")
        files_layout = QVBoxLayout(files_group)

        self.pdf_list = PdfDropList()
        self.pdf_list.files_dropped.connect(self.add_pdf_paths)
        files_layout.addWidget(self.pdf_list)

        file_buttons = QHBoxLayout()
        self.add_button = QPushButton("PDF hinzufügen")
        self.remove_button = QPushButton("Auswahl entfernen")
        self.clear_button = QPushButton("Liste leeren")
        file_buttons.addWidget(self.add_button)
        file_buttons.addWidget(self.remove_button)
        file_buttons.addWidget(self.clear_button)
        file_buttons.addStretch()
        files_layout.addLayout(file_buttons)

        root.addWidget(files_group)

        output_group = QGroupBox("Ausgabe")
        output_form = QFormLayout(output_group)

        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_button = QPushButton("Ordner wählen")
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.output_button)
        output_form.addRow("Ausgabeordner:", output_row)

        self.prefix_edit = QLineEdit("Seite")
        output_form.addRow("Dateipräfix:", self.prefix_edit)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 999999)
        self.start_spin.setValue(1)
        output_form.addRow("Startnummer:", self.start_spin)

        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["150", "200", "300", "400", "600"])
        self.dpi_combo.setCurrentText("300")
        output_form.addRow("Auflösung (DPI):", self.dpi_combo)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(95)
        output_form.addRow("JPG-Qualität:", self.quality_spin)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Optional – nur für passwortgeschützte PDFs")
        output_form.addRow("PDF-Passwort:", self.password_edit)

        self.own_folder_check = QCheckBox("Für jede PDF einen eigenen Unterordner erstellen")
        self.own_folder_check.setChecked(True)
        output_form.addRow("", self.own_folder_check)

        self.global_number_check = QCheckBox(
            "Nummerierung über alle geladenen PDFs fortlaufend weiterführen"
        )
        self.global_number_check.setChecked(False)
        output_form.addRow("", self.global_number_check)

        self.overwrite_check = QCheckBox("Vorhandene Ausgabedateien überschreiben")
        self.overwrite_check.setChecked(False)
        output_form.addRow("", self.overwrite_check)

        root.addWidget(output_group)

        progress_group = QGroupBox("Konvertierung")
        progress_layout = QVBoxLayout(progress_group)

        self.current_label = QLabel("Bereit.")
        progress_layout.addWidget(self.current_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("Konvertierung starten")
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setEnabled(False)
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.cancel_button)
        action_row.addStretch()
        progress_layout.addLayout(action_row)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(130)
        progress_layout.addWidget(self.log_edit)

        root.addWidget(progress_group, 1)

        self.add_button.clicked.connect(self.choose_pdfs)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear_pdfs)
        self.output_button.clicked.connect(self.choose_output)
        self.start_button.clicked.connect(self.start_conversion)
        self.cancel_button.clicked.connect(self.cancel_conversion)

        self.statusBar().showMessage("Bereit")

    def choose_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "PDF-Dokumente auswählen",
            "",
            "PDF-Dokumente (*.pdf)",
        )
        if files:
            self.add_pdf_paths(files)

    @Slot(list)
    def add_pdf_paths(self, files: Iterable[str]) -> None:
        added = 0
        for filename in files:
            path = str(Path(filename).resolve())
            if not path.lower().endswith(".pdf"):
                continue
            if path not in self.pdf_paths:
                self.pdf_paths.append(path)
                self.pdf_list.addItem(path)
                added += 1

        if added and not self.output_edit.text().strip():
            first_parent = Path(self.pdf_paths[0]).parent
            self.output_edit.setText(str(first_parent / "PDF_JPG_Export"))

        self.statusBar().showMessage(
            f"{len(self.pdf_paths)} PDF-Dokument(e) geladen"
        )

    def remove_selected(self) -> None:
        selected_rows = sorted(
            {self.pdf_list.row(item) for item in self.pdf_list.selectedItems()},
            reverse=True,
        )
        for row in selected_rows:
            self.pdf_list.takeItem(row)
            del self.pdf_paths[row]

    def clear_pdfs(self) -> None:
        self.pdf_paths.clear()
        self.pdf_list.clear()
        self.statusBar().showMessage("PDF-Liste geleert")

    def choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Ausgabeordner auswählen",
            self.output_edit.text().strip() or "",
        )
        if folder:
            self.output_edit.setText(folder)

    def set_running(self, running: bool) -> None:
        self.add_button.setEnabled(not running)
        self.remove_button.setEnabled(not running)
        self.clear_button.setEnabled(not running)
        self.output_button.setEnabled(not running)
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)

    def start_conversion(self) -> None:
        if not self.pdf_paths:
            QMessageBox.warning(self, APP_NAME, "Bitte mindestens eine PDF hinzufügen.")
            return

        output = self.output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, APP_NAME, "Bitte einen Ausgabeordner festlegen.")
            return

        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self.current_label.setText("Konvertierung wird vorbereitet …")
        self.set_running(True)

        self.thread = QThread(self)
        self.worker = ConversionWorker(
            pdf_files=list(self.pdf_paths),
            output_root=output,
            dpi=int(self.dpi_combo.currentText()),
            quality=self.quality_spin.value(),
            prefix=self.prefix_edit.text().strip() or "Seite",
            start_number=self.start_spin.value(),
            own_folder=self.own_folder_check.isChecked(),
            global_numbering=self.global_number_check.isChecked(),
            overwrite=self.overwrite_check.isChecked(),
            password=self.password_edit.text(),
        )

        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.current_file.connect(
            lambda name: self.current_label.setText(f"Aktuell: {name}")
        )
        self.worker.log.connect(self.log_edit.append)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)

        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup_thread)

        self.thread.start()

    @Slot(int, int)
    def on_progress(self, current: int, total: int) -> None:
        percent = int((current / total) * 100) if total else 0
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{current} / {total} Seiten  ({percent} %)")

    @Slot(int, int, str)
    def on_finished(self, converted: int, failed_pdfs: int, status: str) -> None:
        self.set_running(False)
        self.current_label.setText(
            f"Vorgang {status}: {converted} JPG-Datei(en) erstellt."
        )
        self.statusBar().showMessage(f"Konvertierung {status}")

        message = (
            f"Konvertierung {status}.\n\n"
            f"Erstellte JPG-Dateien: {converted}\n"
            f"PDFs mit Fehlern: {failed_pdfs}\n\n"
            f"Ausgabe: {self.output_edit.text().strip()}"
        )
        QMessageBox.information(self, APP_NAME, message)

    @Slot(str)
    def on_failed(self, message: str) -> None:
        self.set_running(False)
        self.current_label.setText("Konvertierung fehlgeschlagen.")
        self.log_edit.append(f"FEHLER: {message}")
        QMessageBox.critical(self, APP_NAME, message)

    @Slot()
    def cleanup_thread(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None

    def cancel_conversion(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.cancel_button.setEnabled(False)
            self.current_label.setText("Abbruch angefordert …")

    def closeEvent(self, event) -> None:
        if self.thread is not None and self.thread.isRunning():
            answer = QMessageBox.question(
                self,
                APP_NAME,
                "Eine Konvertierung läuft noch. Wirklich beenden?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            if self.worker is not None:
                self.worker.stop()
            self.thread.quit()
            self.thread.wait(3000)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
