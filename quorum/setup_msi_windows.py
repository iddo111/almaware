from cx_Freeze import Executable, setup

source_files = [
    "quorum_app_windows.py", "quorum_app.py", "server.py",
    "config.py", "run_debate.py", "shakla.py", "ai_clients.py", "render.py",
    "registry.py", "rooms.py", "workers.py", "stateio.py",
    "run_quorum.vbs"
]

setup(
    name="ALMAWAREQuorum",
    version="0.2.0",
    description="Local Talmudic multi-model debate console",
    author="ALMAWARE",
    options={
        "build_exe": {
            "includes": ["asyncio", "http.server", "webbrowser"],
            # ui/ (rooms page) + worker/ (federation worker PWA) ride along so
            # the installed server can serve /room and /worker/.
            "include_files": source_files + [("ui", "ui"), ("worker", "worker")],
            "optimize": 1,
        },
        "bdist_msi": {
            "all_users": False,
            "initial_target_dir": r"[LocalAppDataFolder]\Programs\ALMAWARE\Quorum",
            "launch_on_finish": False,
            "output_name": "Quorum-Setup.msi",
            "upgrade_code": "{C8A6D688-5E85-4C0A-B5B0-80D60372B16D}",
        },
    },
    executables=[
        Executable(
            "quorum_app_windows.py",
            base="console",
            target_name="quorum.exe",
            shortcut_name="ALMAWARE Quorum",
            shortcut_dir="DesktopFolder",
        )
    ],
)
