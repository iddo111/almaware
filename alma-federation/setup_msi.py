from cx_Freeze import setup, Executable
setup(
    name="AlmaFederationWorker",
    version="0.1.0",
    description="Alma Federation - worker node (join the grid, contribute compute for the general good)",
    author="ALMAWARE",
    executables=[Executable("worker.py", base=None, target_name="alma-worker.exe")],
    options={
        "build_exe": {"optimize": 2},
        "bdist_msi": {"initial_target_dir": r"[ProgramFilesFolder]\AlmaFederation"},
    },
)
