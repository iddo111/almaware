"""
Disposable target window for keshev_intake.py's self-test. A fresh Tk window
every launch (no Windows-11-Notepad singleton/tab-reuse risk, no chance of
landing text in a real document). Ctrl+A/Ctrl+C are re-bound because Tk's
Text widget defaults to emacs-style bindings (Ctrl+A = start-of-line, not
select-all).
"""
import tkinter as tk

OUT_PATH = r"D:\CLAUDE\keshev-next\state\selftest_target_content.txt"

root = tk.Tk()
root.title("KESHEV-INTAKE-SELFTEST-TARGET")
root.geometry("520x320+120+120")

txt = tk.Text(root, font=("Segoe UI", 14))
txt.pack(fill="both", expand=True)
txt.focus_force()


def dump_content():
    try:
        content = txt.get("1.0", "end-1c")
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass
    root.after(100, dump_content)


root.after(100, dump_content)
root.after(200, lambda: (root.lift(), root.focus_force(), txt.focus_force()))
root.mainloop()
