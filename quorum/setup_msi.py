"""Build the official per-user Windows MSI for QUORUM with cx_Freeze."""

from cx_Freeze import Executable, setup


setup(
    name="ALMAWAREQuorum",
    version="0.1.0",
    description="Local Talmudic multi-model debate console",
    author="ALMAWARE",
    options={
        "build_exe": {
            "includes": ["asyncio", "http.server", "webbrowser"],
            "optimize": 1,
        },
        "bdist_msi": {
            "all_users": False,
            "initial_target_dir": r"[LocalAppDataFolder]\Programs\ALMAWARE\Quorum",
            "launch_on_finish": True,
            "output_name": "Quorum-Setup.msi",
            "upgrade_code": "{C8A6D688-5E85-4C0A-B5B0-80D60372B16D}",
        },
    },
    executables=[
        Executable(
            "quorum_app.py",
            base="console",
            target_name="Quorum.exe",
            shortcut_name="QUORUM",
            shortcut_dir="DesktopFolder",
        )
    ],
)
