"""Always-on-top Codex + Yigal companion widget for Windows."""

from __future__ import annotations

import ctypes
import json
import os
import threading
import tkinter as tk
import urllib.request
import webbrowser

from PIL import Image, ImageTk


HERE = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = "http://127.0.0.1:8790/"
AVATARS = os.path.join(HERE, "avatars")


def _single_instance() -> bool:
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ALMAWARE_AVATAR_WIDGET_V1")
    return bool(mutex) and ctypes.windll.kernel32.GetLastError() != 183


class AvatarWidget:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("ALMAWARE companions")
        self.root.configure(bg="#f6f8fb")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-toolwindow", True)
        self.root.geometry(self._position(248, 146))
        self.drag_x = 0
        self.drag_y = 0
        self.images: list[tk.PhotoImage] = []
        self.yigal_frames: list[ImageTk.PhotoImage] = []
        self.yigal_image_label: tk.Label | None = None
        self.animation_step = 0

        shell = tk.Frame(self.root, bg="#f6f8fb", bd=1, relief="solid")
        shell.pack(fill="both", expand=True)
        bar = tk.Frame(shell, bg="#183a55", height=25)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="ALMAWARE", bg="#183a55", fg="white",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=8)
        tk.Button(bar, text="×", command=self.root.destroy, bg="#183a55", fg="white",
                  activebackground="#b42318", activeforeground="white", bd=0,
                  font=("Segoe UI", 11), width=3).pack(side="right")
        tk.Button(bar, text="↗", command=lambda: webbrowser.open(DASHBOARD),
                  bg="#183a55", fg="white", activebackground="#285b7c",
                  activeforeground="white", bd=0, font=("Segoe UI", 10), width=3).pack(side="right")
        bar.bind("<ButtonPress-1>", self._drag_start)
        bar.bind("<B1-Motion>", self._drag_move)

        people = tk.Frame(shell, bg="#f6f8fb")
        people.pack(fill="both", expand=True, padx=7, pady=7)
        self.yigal_state = self._person(people, "codex-avatar.png", "Codex", "איתך", "#1b7f5a")
        self.yigal_state = self._person(people, "yigal-avatar.png", "יגאל", "לומד", "#0d9488")
        for child in people.winfo_children():
            child.bind("<Double-Button-1>", lambda _e: webbrowser.open(DASHBOARD))

        self.root.after(300, self._refresh_async)
        self.root.after(120, self._animate_yigal)

    def _position(self, width: int, height: int) -> str:
        # A fixed safe inset avoids mixed-DPI desktops placing the widget off-screen.
        return f"{width}x{height}+20+160"

    def _person(self, parent: tk.Frame, filename: str, name: str,
                state: str, dot: str) -> tk.Label:
        item = tk.Frame(parent, bg="white", bd=1, relief="solid", width=108, height=98)
        item.pack(side="left", padx=4, fill="both", expand=True)
        item.pack_propagate(False)
        if filename == "yigal-avatar.png":
            sheet = Image.open(os.path.join(AVATARS, "yigal-expressions.png")).convert("RGB")
            tile_w, tile_h = sheet.width // 3, sheet.height // 2
            for col, row in ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)):
                tile = sheet.crop((col * tile_w, row * tile_h,
                                   (col + 1) * tile_w, (row + 1) * tile_h))
                self.yigal_frames.append(ImageTk.PhotoImage(tile.resize((48, 72), Image.Resampling.LANCZOS)))
            image = self.yigal_frames[0]
            self.yigal_image_label = tk.Label(item, image=image, bg="white")
            self.yigal_image_label.pack(side="left", padx=(5, 2), pady=8)
        else:
            image = tk.PhotoImage(file=os.path.join(AVATARS, filename)).subsample(24, 24)
            self.images.append(image)
            tk.Label(item, image=image, bg="white").pack(side="left", padx=(5, 2), pady=8)
        text = tk.Frame(item, bg="white")
        text.pack(side="left", fill="both", expand=True, pady=22)
        tk.Label(text, text="●", bg="white", fg=dot, font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(text, text=name, bg="white", fg="#183a55",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        status = tk.Label(text, text=state, bg="white", fg="#667085", font=("Segoe UI", 8))
        status.pack(anchor="w")
        return status

    def _animate_yigal(self) -> None:
        if self.yigal_image_label and self.yigal_frames:
            sequence = ([0] * 24 + [1] * 2 + [0] * 18 + [5] * 7 +
                        [0] * 22 + [2] * 8 + [0] * 16)
            frame = sequence[self.animation_step % len(sequence)]
            self.yigal_image_label.configure(image=self.yigal_frames[frame])
            self.animation_step += 1
        self.root.after(120, self._animate_yigal)

    def _drag_start(self, event: tk.Event) -> None:
        self.drag_x = event.x
        self.drag_y = event.y

    def _drag_move(self, event: tk.Event) -> None:
        x = self.root.winfo_x() + event.x - self.drag_x
        y = self.root.winfo_y() + event.y - self.drag_y
        self.root.geometry(f"+{x}+{y}")

    def _refresh_async(self) -> None:
        threading.Thread(target=self._fetch_state, daemon=True).start()
        self.root.after(12000, self._refresh_async)

    def _fetch_state(self) -> None:
        label = "לומד"
        try:
            with urllib.request.urlopen(DASHBOARD + "api/state", timeout=3) as response:
                state = json.load(response).get("siblings", {}).get("yigael", {})
            if state.get("training"):
                label = "מתאמן"
            elif state.get("online") is False:
                label = "לא מחובר"
        except Exception:
            label = "ממתין"
        self.root.after(0, lambda: self.yigal_state.configure(text=label))

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__" and _single_instance():
    AvatarWidget().run()
