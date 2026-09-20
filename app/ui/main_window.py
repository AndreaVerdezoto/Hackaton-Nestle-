import tkinter as tk
from tkinter import ttk


class MainWindow:

    def __init__(self):

        self.root = tk.Tk()

        self.root.title(
            "Sistema Inteligente de Gestión de Flota AGV"
        )

        self.root.geometry(
            "1100x700"
        )

        self.crear_interfaz()


    def crear_interfaz(self):

        titulo = ttk.Label(
            self.root,
            text="Gestión Inteligente de Flota AGV",
            font=("Arial", 22, "bold")
        )

        titulo.pack(
            pady=20
        )


    def ejecutar(self):

        self.root.mainloop()


if __name__ == "__main__":

    app = MainWindow()

    app.ejecutar()