import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


SUPPORTED_FORMATS = [
    ("Bilddateien", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
    ("JPEG", "*.jpg *.jpeg"),
    ("PNG", "*.png"),
    ("BMP", "*.bmp"),
    ("WebP", "*.webp"),
    ("TIFF", "*.tif *.tiff"),
    ("Alle Dateien", "*.*"),
]


class ImageToPdfApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image to PDF")
        self.root.geometry("820x560")
        self.root.minsize(720, 500)

        self.images = []

        self.page_orientation = tk.StringVar(value="Hochformat")
        self.margin_mm = tk.DoubleVar(value=12.0)

        self.build_ui()

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(
            outer,
            text="Bilder zu PDF",
            font=("Segoe UI", 18, "bold")
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            outer,
            text="Bilder hinzufügen, sortieren und als mehrseitige A4-PDF exportieren."
        )
        subtitle.pack(anchor="w", pady=(2, 14))

        main = ttk.Frame(outer)
        main.pack(fill="both", expand=True)

        list_frame = ttk.LabelFrame(main, text="Bilder", padding=10)
        list_frame.pack(side="left", fill="both", expand=True)

        self.listbox = tk.Listbox(
            list_frame,
            selectmode=tk.SINGLE,
            activestyle="none",
            font=("Segoe UI", 10)
        )
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.listbox.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        controls = ttk.Frame(main, padding=(12, 0, 0, 0))
        controls.pack(side="right", fill="y")

        ttk.Button(
            controls,
            text="Bilder hinzufügen",
            command=self.add_images,
            width=22
        ).pack(fill="x", pady=(0, 8))

        ttk.Button(
            controls,
            text="Auswahl entfernen",
            command=self.remove_selected,
            width=22
        ).pack(fill="x", pady=4)

        ttk.Separator(controls).pack(fill="x", pady=10)

        ttk.Button(
            controls,
            text="Nach oben",
            command=self.move_up,
            width=22
        ).pack(fill="x", pady=4)

        ttk.Button(
            controls,
            text="Nach unten",
            command=self.move_down,
            width=22
        ).pack(fill="x", pady=4)

        ttk.Separator(controls).pack(fill="x", pady=10)

        ttk.Button(
            controls,
            text="Liste leeren",
            command=self.clear_list,
            width=22
        ).pack(fill="x", pady=4)

        options = ttk.LabelFrame(outer, text="PDF-Einstellungen", padding=10)
        options.pack(fill="x", pady=(14, 10))

        ttk.Label(options, text="Ausrichtung:").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )

        orientation_box = ttk.Combobox(
            options,
            textvariable=self.page_orientation,
            state="readonly",
            values=["Hochformat", "Querformat"],
            width=18
        )
        orientation_box.grid(row=0, column=1, sticky="w")

        ttk.Label(options, text="Seitenrand (mm):").grid(
            row=0, column=2, sticky="w", padx=(24, 8)
        )

        margin_spin = ttk.Spinbox(
            options,
            from_=0,
            to=50,
            increment=1,
            textvariable=self.margin_mm,
            width=8
        )
        margin_spin.grid(row=0, column=3, sticky="w")

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x")

        self.status = ttk.Label(bottom, text="0 Bilder geladen")
        self.status.pack(side="left")

        ttk.Button(
            bottom,
            text="PDF erstellen",
            command=self.create_pdf
        ).pack(side="right")

    def refresh_list(self, selected_index=None):
        self.listbox.delete(0, tk.END)

        for index, path in enumerate(self.images, start=1):
            self.listbox.insert(tk.END, f"{index:02d}  {os.path.basename(path)}")

        self.status.config(text=f"{len(self.images)} Bilder geladen")

        if selected_index is not None and self.images:
            selected_index = max(0, min(selected_index, len(self.images) - 1))
            self.listbox.selection_set(selected_index)
            self.listbox.activate(selected_index)

    def add_images(self):
        paths = filedialog.askopenfilenames(
            title="Bilder auswählen",
            filetypes=SUPPORTED_FORMATS
        )

        if not paths:
            return

        self.images.extend(paths)
        self.refresh_list(len(self.images) - 1)

    def remove_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Bild auswählen.")
            return

        index = selection[0]
        del self.images[index]
        self.refresh_list(index)

    def clear_list(self):
        if not self.images:
            return

        if messagebox.askyesno(
            "Liste leeren",
            "Möchtest du wirklich alle Bilder aus der Liste entfernen?"
        ):
            self.images.clear()
            self.refresh_list()

    def move_up(self):
        selection = self.listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if index <= 0:
            return

        self.images[index - 1], self.images[index] = (
            self.images[index],
            self.images[index - 1]
        )
        self.refresh_list(index - 1)

    def move_down(self):
        selection = self.listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if index >= len(self.images) - 1:
            return

        self.images[index + 1], self.images[index] = (
            self.images[index],
            self.images[index + 1]
        )
        self.refresh_list(index + 1)

    def create_pdf(self):
        if not self.images:
            messagebox.showwarning(
                "Keine Bilder",
                "Bitte zuerst mindestens ein Bild hinzufügen."
            )
            return

        output = filedialog.asksaveasfilename(
            title="PDF speichern",
            defaultextension=".pdf",
            filetypes=[("PDF-Datei", "*.pdf")],
            initialfile="bilder.pdf"
        )

        if not output:
            return

        try:
            margin_mm = float(self.margin_mm.get())
            if margin_mm < 0 or margin_mm > 50:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror(
                "Ungültiger Seitenrand",
                "Bitte einen Wert zwischen 0 und 50 mm eingeben."
            )
            return

        page_size = A4
        if self.page_orientation.get() == "Querformat":
            page_size = landscape(A4)

        page_width, page_height = page_size
        margin = margin_mm * 72 / 25.4

        available_width = page_width - (2 * margin)
        available_height = page_height - (2 * margin)

        if available_width <= 0 or available_height <= 0:
            messagebox.showerror(
                "Ungültige Einstellung",
                "Der Seitenrand ist für das gewählte Seitenformat zu groß."
            )
            return

        pdf = canvas.Canvas(output, pagesize=page_size)

        errors = []

        for path in self.images:
            try:
                with Image.open(path) as image:
                    image = ImageOps.exif_transpose(image)

                    if image.mode not in ("RGB", "RGBA"):
                        image = image.convert("RGB")

                    image_width, image_height = image.size
                    ratio = min(
                        available_width / image_width,
                        available_height / image_height
                    )

                    draw_width = image_width * ratio
                    draw_height = image_height * ratio

                    x = (page_width - draw_width) / 2
                    y = (page_height - draw_height) / 2

                    pdf.drawImage(
                        ImageReader(image),
                        x,
                        y,
                        width=draw_width,
                        height=draw_height,
                        preserveAspectRatio=True,
                        mask="auto"
                    )
                    pdf.showPage()

            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")

        pdf.save()

        if errors:
            messagebox.showwarning(
                "PDF erstellt",
                "Die PDF wurde erstellt, einige Bilder konnten jedoch nicht "
                "verarbeitet werden:\n\n" + "\n".join(errors)
            )
        else:
            messagebox.showinfo(
                "Fertig",
                f"Die PDF wurde erfolgreich erstellt:\n\n{output}"
            )


def main():
    root = tk.Tk()

    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass

    ImageToPdfApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
