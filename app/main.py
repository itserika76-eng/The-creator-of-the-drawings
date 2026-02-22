from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from engine import DrawingEngine


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AI-конструктор чертежей для КОМПАС-3D (MVP)")
        self.root.geometry("840x560")

        self.compas_path = tk.StringVar()
        self.image_path = tk.StringVar()
        self.project_name = tk.StringVar(value="Новый проект")
        self.prompt_text = tk.StringVar()
        self.mode = tk.StringVar(value="image")

        self._build_ui()

    def _build_ui(self) -> None:
        frm = ttk.Frame(self.root, padding=16)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="1) Выберите исполняемый файл КОМПАС-3D").pack(anchor=tk.W)
        row1 = ttk.Frame(frm)
        row1.pack(fill=tk.X, pady=6)
        ttk.Entry(row1, textvariable=self.compas_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row1, text="Обзор", command=self._pick_compas).pack(side=tk.LEFT, padx=6)

        ttk.Separator(frm).pack(fill=tk.X, pady=8)

        ttk.Label(frm, text="2) Название проекта").pack(anchor=tk.W)
        ttk.Entry(frm, textvariable=self.project_name).pack(fill=tk.X, pady=6)

        ttk.Label(frm, text="3) Режим").pack(anchor=tk.W)
        mode_row = ttk.Frame(frm)
        mode_row.pack(fill=tk.X)
        ttk.Radiobutton(mode_row, text="По изображению", variable=self.mode, value="image").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="По запросу", variable=self.mode, value="prompt").pack(side=tk.LEFT, padx=16)

        ttk.Label(frm, text="4A) Изображение чертежа").pack(anchor=tk.W, pady=(8, 0))
        row2 = ttk.Frame(frm)
        row2.pack(fill=tk.X, pady=6)
        ttk.Entry(row2, textvariable=self.image_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row2, text="Выбрать", command=self._pick_image).pack(side=tk.LEFT, padx=6)

        ttk.Label(frm, text="4B) Текстовый запрос").pack(anchor=tk.W)
        ttk.Entry(frm, textvariable=self.prompt_text).pack(fill=tk.X, pady=6)

        ttk.Button(frm, text="Сгенерировать пакет", command=self._run).pack(anchor=tk.W, pady=12)

        self.log = tk.Text(frm, height=14)
        self.log.pack(fill=tk.BOTH, expand=True)

    def _pick_compas(self) -> None:
        path = filedialog.askopenfilename(title="Выберите ярлык/EXE КОМПАС-3D")
        if path:
            self.compas_path.set(path)

    def _pick_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("All", "*.*")],
        )
        if path:
            self.image_path.set(path)

    def _run(self) -> None:
        compas = self.compas_path.get().strip()
        if not compas:
            messagebox.showerror("Ошибка", "Сначала выберите исполняемый файл КОМПАС-3D")
            return

        out_dir = Path.cwd() / "output"
        engine = DrawingEngine(compas_executable=Path(compas), output_dir=out_dir)

        if self.mode.get() == "image":
            image = self.image_path.get().strip()
            if not image:
                messagebox.showerror("Ошибка", "В режиме 'По изображению' нужно выбрать файл")
                return
            result = engine.build_from_image(Path(image), self.project_name.get().strip())
        else:
            prompt = self.prompt_text.get().strip()
            if not prompt:
                messagebox.showerror("Ошибка", "В режиме 'По запросу' заполните текст")
                return
            result = engine.build_from_prompt(prompt, self.project_name.get().strip())

        self.log.delete("1.0", tk.END)
        self.log.insert(tk.END, "Готово. Созданы файлы:\n")
        self.log.insert(tk.END, f"- {result.package_path}\n")
        self.log.insert(tk.END, f"- {result.specification_path}\n")
        self.log.insert(tk.END, f"- {result.macro_template_path}\n")
        if result.warnings:
            self.log.insert(tk.END, "\nПроверка стандартов (предупреждения):\n")
            for warning in result.warnings:
                self.log.insert(tk.END, f"- {warning}\n")


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
