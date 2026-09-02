from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from metadata_extractor import APP_NAME, APP_VERSION, SUPPORTED_EXTENSIONS, export_csv, export_json, extract_metadata, flatten_dict


IMAGE_FILE_TYPES = [
    ("Bilddateien", "*.jpg *.jpeg *.jpe *.jfif *.png *.webp *.tif *.tiff *.bmp *.gif *.ico *.pcx *.ppm *.pgm *.pbm *.avif *.heic *.heif *.jxl"),
    ("JPEG", "*.jpg *.jpeg *.jpe *.jfif"),
    ("PNG", "*.png"),
    ("WebP", "*.webp"),
    ("TIFF", "*.tif *.tiff"),
    ("Weitere Bildformate", "*.bmp *.gif *.ico *.pcx *.ppm *.pgm *.pbm *.avif *.heic *.heif *.jxl"),
    ("Alle Dateien", "*.*"),
]


class MetadataInspectorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1280x780")
        self.root.minsize(980, 640)

        self.files: list[str] = []
        self.results: dict[str, Any] = {}
        self.current_file: str | None = None
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.scan_thread: threading.Thread | None = None

        self.use_c2pa = tk.BooleanVar(value=True)
        self.use_exiftool = tk.BooleanVar(value=True)
        self.exiftool_path = tk.StringVar(value="")
        self.status = tk.StringVar(value="Bereit")
        self.filter_text = tk.StringVar(value="")

        self._configure_style()
        self._build_ui()
        self.root.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            try:
                style.theme_use("vista")
            except tk.TclError:
                pass
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10))
        style.configure("Status.TLabel", padding=(8, 4))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="BYLICKILABS // IMAGE METADATA INSPECTOR", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="EXIF · GPS · IPTC · XMP · ICC · Dateiinformationen · Hashes · C2PA / Content Credentials · optionaler ExifTool Deep-Scan",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Bilder hinzufügen", command=self.add_files).pack(side="left")
        ttk.Button(toolbar, text="Ordner hinzufügen", command=self.add_folder).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Auswahl entfernen", command=self.remove_selected).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Liste leeren", command=self.clear_files).pack(side="left", padx=(6, 0))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)
        self.scan_button = ttk.Button(toolbar, text="Metadaten analysieren", command=self.scan_files)
        self.scan_button.pack(side="left")
        ttk.Button(toolbar, text="JSON exportieren", command=self.export_json_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="CSV exportieren", command=self.export_csv_dialog).pack(side="left", padx=(6, 0))

        options = ttk.LabelFrame(outer, text="Analyseoptionen", padding=8)
        options.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(options, text="C2PA / Content Credentials prüfen", variable=self.use_c2pa).pack(side="left")
        ttk.Checkbutton(options, text="ExifTool Deep-Scan verwenden", variable=self.use_exiftool).pack(side="left", padx=(18, 0))
        ttk.Label(options, text="ExifTool-Pfad (optional):").pack(side="left", padx=(18, 4))
        ttk.Entry(options, textvariable=self.exiftool_path, width=34).pack(side="left", fill="x", expand=True)
        ttk.Button(options, text="…", width=3, command=self.select_exiftool).pack(side="left", padx=(4, 0))

        paned = ttk.Panedwindow(outer, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=4)

        ttk.Label(left, text="Bilddateien", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.file_list = tk.Listbox(list_frame, selectmode=tk.BROWSE, exportselection=False, font=("Segoe UI", 9))
        self.file_list.pack(side="left", fill="both", expand=True)
        file_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_list.yview)
        file_scroll.pack(side="right", fill="y")
        self.file_list.configure(yscrollcommand=file_scroll.set)
        self.file_list.bind("<<ListboxSelect>>", self.on_file_selected)

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)

        tree_tab = ttk.Frame(notebook, padding=6)
        raw_tab = ttk.Frame(notebook, padding=6)
        c2pa_tab = ttk.Frame(notebook, padding=6)
        notebook.add(tree_tab, text="Metadaten")
        notebook.add(raw_tab, text="Raw JSON")
        notebook.add(c2pa_tab, text="C2PA")

        filter_bar = ttk.Frame(tree_tab)
        filter_bar.pack(fill="x", pady=(0, 6))
        ttk.Label(filter_bar, text="Filter:").pack(side="left")
        filter_entry = ttk.Entry(filter_bar, textvariable=self.filter_text)
        filter_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        filter_entry.bind("<KeyRelease>", lambda _e: self.refresh_current_view())

        tree_frame = ttk.Frame(tree_tab)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=("value",), show="tree headings")
        self.tree.heading("#0", text="Feld")
        self.tree.heading("value", text="Wert")
        self.tree.column("#0", width=390, stretch=True)
        self.tree.column("value", width=650, stretch=True)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x = ttk.Scrollbar(tree_tab, orient="horizontal", command=self.tree.xview)
        tree_scroll_x.pack(fill="x")
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.raw_text = tk.Text(raw_tab, wrap="none", font=("Consolas", 9), undo=False)
        raw_scroll_y = ttk.Scrollbar(raw_tab, orient="vertical", command=self.raw_text.yview)
        raw_scroll_x = ttk.Scrollbar(raw_tab, orient="horizontal", command=self.raw_text.xview)
        self.raw_text.configure(yscrollcommand=raw_scroll_y.set, xscrollcommand=raw_scroll_x.set)
        self.raw_text.grid(row=0, column=0, sticky="nsew")
        raw_scroll_y.grid(row=0, column=1, sticky="ns")
        raw_scroll_x.grid(row=1, column=0, sticky="ew")
        raw_tab.rowconfigure(0, weight=1)
        raw_tab.columnconfigure(0, weight=1)

        self.c2pa_text = tk.Text(c2pa_tab, wrap="none", font=("Consolas", 9), undo=False)
        c2pa_scroll_y = ttk.Scrollbar(c2pa_tab, orient="vertical", command=self.c2pa_text.yview)
        c2pa_scroll_x = ttk.Scrollbar(c2pa_tab, orient="horizontal", command=self.c2pa_text.xview)
        self.c2pa_text.configure(yscrollcommand=c2pa_scroll_y.set, xscrollcommand=c2pa_scroll_x.set)
        self.c2pa_text.grid(row=0, column=0, sticky="nsew")
        c2pa_scroll_y.grid(row=0, column=1, sticky="ns")
        c2pa_scroll_x.grid(row=1, column=0, sticky="ew")
        c2pa_tab.rowconfigure(0, weight=1)
        c2pa_tab.columnconfigure(0, weight=1)

        status_bar = ttk.Frame(outer)
        status_bar.pack(fill="x", pady=(8, 0))
        self.progress = ttk.Progressbar(status_bar, mode="determinate", length=240)
        self.progress.pack(side="right")
        ttk.Label(status_bar, textvariable=self.status, style="Status.TLabel").pack(side="left", fill="x", expand=True)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Bilddateien auswählen", filetypes=IMAGE_FILE_TYPES)
        self._append_files(paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Bildordner auswählen")
        if not folder:
            return
        candidates = []
        for path in Path(folder).rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                candidates.append(str(path))
        self._append_files(candidates)

    def _append_files(self, paths: Any) -> None:
        added = 0
        for path in paths:
            normalized = str(Path(path).resolve())
            if normalized not in self.files:
                self.files.append(normalized)
                self.file_list.insert(tk.END, Path(normalized).name)
                added += 1
        self.status.set(f"{added} Datei(en) hinzugefügt. Gesamt: {len(self.files)}")
        if self.files and self.file_list.size() and not self.file_list.curselection():
            self.file_list.selection_set(0)
            self.file_list.event_generate("<<ListboxSelect>>")

    def remove_selected(self) -> None:
        selection = self.file_list.curselection()
        if not selection:
            return
        index = selection[0]
        path = self.files.pop(index)
        self.results.pop(path, None)
        self.file_list.delete(index)
        self.current_file = None
        self.refresh_current_view()
        self.status.set(f"Datei entfernt. Gesamt: {len(self.files)}")

    def clear_files(self) -> None:
        self.files.clear()
        self.results.clear()
        self.current_file = None
        self.file_list.delete(0, tk.END)
        self.refresh_current_view()
        self.status.set("Liste geleert")

    def select_exiftool(self) -> None:
        path = filedialog.askopenfilename(title="ExifTool auswählen", filetypes=[("Executable", "*.exe"), ("Alle Dateien", "*.*")])
        if path:
            self.exiftool_path.set(path)

    def scan_files(self) -> None:
        if not self.files:
            messagebox.showwarning("Keine Dateien", "Bitte zuerst mindestens eine Bilddatei hinzufügen.")
            return
        if self.scan_thread and self.scan_thread.is_alive():
            return

        self.scan_button.configure(state="disabled")
        self.progress.configure(maximum=len(self.files), value=0)
        self.status.set("Analyse gestartet …")
        files_snapshot = list(self.files)
        use_c2pa = self.use_c2pa.get()
        use_exiftool = self.use_exiftool.get()
        exiftool_path = self.exiftool_path.get().strip() or None

        def worker() -> None:
            for index, path in enumerate(files_snapshot, start=1):
                try:
                    result = extract_metadata(path, use_exiftool=use_exiftool, exiftool_path=exiftool_path, use_c2pa=use_c2pa)
                    self.events.put(("result", (path, result, index, len(files_snapshot))))
                except Exception as exc:
                    self.events.put(("error", (path, str(exc), index, len(files_snapshot))))
            self.events.put(("done", len(files_snapshot)))

        self.scan_thread = threading.Thread(target=worker, daemon=True)
        self.scan_thread.start()

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "result":
                    path, result, index, total = payload
                    self.results[path] = result
                    self.progress.configure(value=index)
                    self.status.set(f"Analysiert {index}/{total}: {Path(path).name}")
                    if path == self.current_file:
                        self.refresh_current_view()
                elif event == "error":
                    path, error, index, total = payload
                    self.results[path] = {"Error": error}
                    self.progress.configure(value=index)
                    self.status.set(f"Fehler {index}/{total}: {Path(path).name}")
                    if path == self.current_file:
                        self.refresh_current_view()
                elif event == "done":
                    self.scan_button.configure(state="normal")
                    self.status.set(f"Analyse abgeschlossen: {payload} Datei(en)")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def on_file_selected(self, _event: Any = None) -> None:
        selection = self.file_list.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.files):
            self.current_file = self.files[index]
            self.refresh_current_view()

    def refresh_current_view(self) -> None:
        payload = self.results.get(self.current_file or "")
        self.tree.delete(*self.tree.get_children())
        self.raw_text.configure(state="normal")
        self.c2pa_text.configure(state="normal")
        self.raw_text.delete("1.0", tk.END)
        self.c2pa_text.delete("1.0", tk.END)

        if not payload:
            if self.current_file:
                self.raw_text.insert("1.0", "Noch nicht analysiert.")
                self.c2pa_text.insert("1.0", "Noch nicht analysiert.")
            self.raw_text.configure(state="disabled")
            self.c2pa_text.configure(state="disabled")
            return

        filter_value = self.filter_text.get().strip().lower()
        for key, value in payload.items():
            self._insert_tree_node("", str(key), value, filter_value)

        self.raw_text.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2))
        c2pa_payload = payload.get("C2PA_ContentCredentials", {"Status": "not_scanned"})
        self.c2pa_text.insert("1.0", json.dumps(c2pa_payload, ensure_ascii=False, indent=2))
        self.raw_text.configure(state="disabled")
        self.c2pa_text.configure(state="disabled")

    def _matches_filter(self, key: str, value: Any, filter_value: str) -> bool:
        if not filter_value:
            return True
        try:
            haystack = f"{key} {json.dumps(value, ensure_ascii=False, default=str)}".lower()
        except Exception:
            haystack = f"{key} {value}".lower()
        return filter_value in haystack

    def _insert_tree_node(self, parent: str, key: str, value: Any, filter_value: str) -> str | None:
        if filter_value and not self._matches_filter(key, value, filter_value):
            return None
        if isinstance(value, dict):
            node = self.tree.insert(parent, "end", text=key, values=(f"{len(value)} Feld(er)",), open=bool(filter_value))
            for child_key, child_value in value.items():
                self._insert_tree_node(node, str(child_key), child_value, filter_value)
            return node
        if isinstance(value, list):
            node = self.tree.insert(parent, "end", text=key, values=(f"{len(value)} Eintrag/Einträge",), open=bool(filter_value))
            for index, child_value in enumerate(value):
                self._insert_tree_node(node, f"[{index}]", child_value, filter_value)
            return node
        text = "" if value is None else str(value)
        return self.tree.insert(parent, "end", text=key, values=(text,))

    def _export_payload(self) -> dict[str, Any]:
        return {path: self.results[path] for path in self.files if path in self.results}

    def export_json_dialog(self) -> None:
        payload = self._export_payload()
        if not payload:
            messagebox.showinfo("Kein Ergebnis", "Bitte zuerst die Metadaten analysieren.")
            return
        path = filedialog.asksaveasfilename(title="JSON exportieren", defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="image_metadata_report.json")
        if path:
            export_json(payload, path)
            self.status.set(f"JSON exportiert: {path}")

    def export_csv_dialog(self) -> None:
        payload = self._export_payload()
        if not payload:
            messagebox.showinfo("Kein Ergebnis", "Bitte zuerst die Metadaten analysieren.")
            return
        path = filedialog.asksaveasfilename(title="CSV exportieren", defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="image_metadata_report.csv")
        if path:
            export_csv(payload, path)
            self.status.set(f"CSV exportiert: {path}")


def main() -> None:
    root = tk.Tk()
    MetadataInspectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()