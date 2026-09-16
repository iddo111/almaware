# לזכרה של עלמה ז״ל
"""build_msi.py — build Quorum-Setup.msi from staged payload using Python's msilib."""

import os
import sys
import shutil
import uuid
import msilib
import msilib.schema
import msilib.sequence

PRODUCT_NAME = "ALMAWARE Quorum"
MANUFACTURER = "ALMAWARE"
VERSION = "0.1.0"
UPGRADE_CODE = "{C8A6D688-5E85-4C0A-B5B0-80D60372B16D}"
PRODUCT_CODE = "{" + str(uuid.uuid4()).upper() + "}"
PACKAGE_CODE = "{" + str(uuid.uuid4()).upper() + "}"

# Launcher shortcut details
VBS = "launch.vbs"

# Stage payload files
HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(HERE, "dist", "payload")
OUTPUT = os.path.join(HERE, "Quorum-Setup.msi")

if os.path.exists(PAYLOAD):
    shutil.rmtree(PAYLOAD)
os.makedirs(PAYLOAD)

# Files to package
FILES_TO_PACKAGE = [
    "ai_clients.py",
    "config.py",
    "quorum_app_windows.py",
    "render.py",
    "run_debate.py",
    "server.py",
    "shakla.py",
    "launch.vbs"
]

for fn in FILES_TO_PACKAGE:
    src = os.path.join(HERE, fn)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(PAYLOAD, fn))
    else:
        print(f"Warning: file {fn} not found in {HERE}")

if os.path.exists(OUTPUT):
    os.remove(OUTPUT)

def _ident(s):
    out = []
    for ch in s:
        out.append(ch if (ch.isalnum() or ch in "._") else "_")
    r = "".join(out)
    if r and r[0].isdigit():
        r = "_" + r
    return r[:62] or "_"

_VALID83 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_^$~!#%&-{}@'`()")
_short_used = set()

def _short83(name, key):
    h = "%08X" % (abs(hash(key)) & 0xFFFFFFFF)
    base = h[:8]
    ext = ""
    if "." in name:
        raw = name.rsplit(".", 1)[1].upper()
        ext = "".join(c for c in raw if c in _VALID83)[:3]
    short = base + ("." + ext if ext else "")
    i = 0
    cand = short
    while cand in _short_used:
        i += 1
        cand = ("%07X%X" % (abs(hash(key)) & 0xFFFFFFF, i))[:8] + (("." + ext) if ext else "")
    _short_used.add(cand)
    return cand

# Collect payload files
dirs = {"": sorted(os.listdir(PAYLOAD))}

db = msilib.init_database(OUTPUT, msilib.schema, PRODUCT_NAME, PRODUCT_CODE, VERSION, MANUFACTURER)
msilib.add_tables(db, msilib.sequence)

props = [
    ("UpgradeCode", UPGRADE_CODE),
    ("MSIINSTALLPERUSER", "1"),
    ("ARPNOMODIFY", "1"),
    ("ARPNOREPAIR", "1"),
    ("ARPCONTACT", "iddoperez.ai"),
]
msilib.add_data(db, "Property", props)

si = db.GetSummaryInformation(20)
si.SetProperty(msilib.PID_TITLE, "ALMAWARE Quorum Installer")
si.SetProperty(msilib.PID_SUBJECT, PRODUCT_NAME)
si.SetProperty(msilib.PID_AUTHOR, MANUFACTURER)
si.SetProperty(msilib.PID_TEMPLATE, "x64;1033")
si.SetProperty(msilib.PID_REVNUMBER, PACKAGE_CODE)
si.SetProperty(msilib.PID_KEYWORDS, "Installer,ALMAWARE,Quorum,Debate")
si.SetProperty(msilib.PID_COMMENTS, "Per-user installer for the ALMAWARE Quorum multi-model debate console.")
si.SetProperty(msilib.PID_WORDCOUNT, 2)
si.SetProperty(msilib.PID_PAGECOUNT, 200)
si.Persist()

directory_rows = [
    ("TARGETDIR", None, "SourceDir"),
    ("LocalAppDataFolder", "TARGETDIR", "."),
    ("ALMAWAREDIR", "LocalAppDataFolder", "ALMAWARE"),
    ("INSTALLDIR", "ALMAWAREDIR", "Quorum"),
    ("DesktopFolder", "TARGETDIR", "."),
]
msilib.add_data(db, "Directory", directory_rows)

msilib.add_data(db, "Feature", [
    ("MainFeature", None, PRODUCT_NAME, "The Quorum application", 1, 1, "INSTALLDIR", 0),
])

cab = msilib.CAB("Quorum")
components = []
feature_comp = []
file_rows = []
seq = 0

dkey = "INSTALLDIR"
comp = "c_root"
comp_guid = "{" + str(uuid.uuid4()).upper() + "}"
keypath = None
comp_files = []

for fn in sorted(dirs[""]):
    seq += 1
    abspath = os.path.join(PAYLOAD, fn)
    size = os.path.getsize(abspath)
    file_key = _ident("f_%d_%s" % (seq, fn))
    filename = _short83(fn, file_key) + "|" + fn
    cab.append(abspath, fn, file_key)
    file_rows.append((file_key, comp, filename, size, None, None, 0, seq))
    comp_files.append(file_key)
    if keypath is None:
        keypath = file_key

components.append((comp, comp_guid, dkey, 0, None, keypath))
feature_comp.append(("MainFeature", comp))

SHORTCUT_COMP = "c_shortcuts"
SHORTCUT_GUID = "{" + str(uuid.uuid4()).upper() + "}"
components.append((SHORTCUT_COMP, SHORTCUT_GUID, "INSTALLDIR", 4, None, "RegKeyPath"))
feature_comp.append(("MainFeature", SHORTCUT_COMP))

msilib.add_data(db, "Component", components)
msilib.add_data(db, "FeatureComponents", feature_comp)
msilib.add_data(db, "File", file_rows)

msilib.add_data(db, "Registry", [
    ("RegKeyPath", 1, r"Software\ALMAWARE\Quorum", "Installed", "1", SHORTCUT_COMP),
])

shortcut_rows = [
    ("DesktopSC", "DesktopFolder", "QUORUM", SHORTCUT_COMP,
     "[System64Folder]wscript.exe", '"[INSTALLDIR]%s"' % VBS,
     "Local Talmudic multi-model debate console", None, None, 0, 1, "INSTALLDIR"),
]
msilib.add_data(db, "Shortcut", shortcut_rows)

cab.commit(db)
db.Commit()

print("OK wrote %s  (%d files, %d components)" % (OUTPUT, len(file_rows), len(components)))
