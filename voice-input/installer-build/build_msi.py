"""build_msi.py — build ALMAWARE-HebrewMic-Setup.msi from the staged payload.

Uses Python's stdlib `msilib` (available on Python 3.10-3.12). Produces a real,
valid per-user MSI that:
  * installs the payload tree to %LOCALAPPDATA%\\ALMAWARE\\HebrewMic
  * creates a Desktop shortcut  "ALMAWARE Hebrew Mic"
  * creates a Startup-folder shortcut (autostart at logon)
  * runs entirely per-user (InstallScope=perUser) so no admin / UAC is needed and
    the .venv + model cache the app writes at runtime are in a writable location.

Run with a Python that HAS msilib (3.10-3.12):
    python build_msi.py <payload_dir> <output_msi>
"""
import os
import sys
import uuid

import msilib
import msilib.schema
import msilib.sequence

PAYLOAD = sys.argv[1] if len(sys.argv) > 1 else None
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else None
if not PAYLOAD or not OUTPUT:
    print("usage: build_msi.py <payload_dir> <output_msi>")
    sys.exit(2)
PAYLOAD = os.path.abspath(PAYLOAD)
OUTPUT = os.path.abspath(OUTPUT)

PRODUCT_NAME = "ALMAWARE Hebrew Mic"
MANUFACTURER = "ALMAWARE"
VERSION = "1.0.0"
# Stable UpgradeCode so future versions upgrade in place (fixed, valid GUID);
# new ProductCode each build.
UPGRADE_CODE = "{A1B2C3D4-1111-4E55-9A11-0DEFACE00001}"
PRODUCT_CODE = "{" + str(uuid.uuid4()).upper() + "}"
PACKAGE_CODE = "{" + str(uuid.uuid4()).upper() + "}"

# launcher the shortcuts invoke (windowless pythonw via py launcher)
LAUNCHER = "ALMAWARE_HebMic.pyw"

if os.path.exists(OUTPUT):
    os.remove(OUTPUT)


def _ident(s):
    """Make a valid MSI Identifier (letters, digits, _, .) from any path piece."""
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
    """Generate a UNIQUE, valid MSI short (8.3) filename for `name`. MSI short
    names must be uppercase, <=8 chars base + <=3 char ext, drawn from a limited
    charset (NO braces, spaces, etc.). We derive from a numeric counter to keep
    them unique and always-valid."""
    # base = a stable hex from the File/Dir key (already unique), capped to 8.
    h = "%08X" % (abs(hash(key)) & 0xFFFFFFFF)
    base = h[:8]
    # extension from the real name, sanitized to <=3 valid chars
    ext = ""
    if "." in name:
        raw = name.rsplit(".", 1)[1].upper()
        ext = "".join(c for c in raw if c in _VALID83)[:3]
    short = base + ("." + ext if ext else "")
    # guarantee uniqueness
    i = 0
    cand = short
    while cand in _short_used:
        i += 1
        cand = ("%07X%X" % (abs(hash(key)) & 0xFFFFFFF, i))[:8] + (("." + ext) if ext else "")
    _short_used.add(cand)
    return cand


# ── collect payload files grouped by their relative directory ─────────────────
dirs = {}  # rel_dir -> list of filenames
for root, _, files in os.walk(PAYLOAD):
    rel = os.path.relpath(root, PAYLOAD)
    rel = "" if rel == "." else rel.replace("\\", "/")
    for fn in files:
        dirs.setdefault(rel, []).append(fn)

# ── create the database ───────────────────────────────────────────────────────
db = msilib.init_database(OUTPUT, msilib.schema, PRODUCT_NAME, PRODUCT_CODE,
                          VERSION, MANUFACTURER)
msilib.add_tables(db, msilib.sequence)

# NOTE: init_database() already inserts ProductName/ProductCode/ProductVersion/
# Manufacturer into the Property table — re-adding them = duplicate-key error.
# Only add the EXTRA properties here.
props = [
    ("UpgradeCode", UPGRADE_CODE),
    # per-user install: no admin, no UAC, writable install dir for the venv/model.
    # (Omitting ALLUSERS entirely = per-user/per-machine decided by MSIINSTALLPERUSER
    #  + the per-user summary word-count; an empty Value is rejected by the schema.)
    ("MSIINSTALLPERUSER", "1"),
    ("ARPNOMODIFY", "1"),
    ("ARPNOREPAIR", "1"),
    ("ARPPRODUCTICON", "MicIcon"),
    # keep the install reasonably visible in Programs list
    ("ARPCONTACT", "iddoperez.ai"),
]
msilib.add_data(db, "Property", props)

# Summary information stream (so msiexec/validators see a proper package).
si = db.GetSummaryInformation(20)
si.SetProperty(msilib.PID_TITLE, "ALMAWARE Hebrew Mic Installer")
si.SetProperty(msilib.PID_SUBJECT, PRODUCT_NAME)
si.SetProperty(msilib.PID_AUTHOR, MANUFACTURER)
si.SetProperty(msilib.PID_TEMPLATE, "x64;1033")  # 64-bit, English
si.SetProperty(msilib.PID_REVNUMBER, PACKAGE_CODE)
si.SetProperty(msilib.PID_KEYWORDS, "Installer,ALMAWARE,Hebrew,Mic")
si.SetProperty(msilib.PID_COMMENTS, "Per-user installer for the ALMAWARE Hebrew Mic.")
# word count 2 => per-user-capable, elevated not required
si.SetProperty(msilib.PID_WORDCOUNT, 2)
si.SetProperty(msilib.PID_PAGECOUNT, 200)  # min Windows Installer version 2.00
si.Persist()

# ── Directory table ───────────────────────────────────────────────────────────
# TARGETDIR -> LocalAppDataFolder -> ALMAWARE -> HebrewMic (INSTALLDIR) + subdirs.
directory_rows = [
    ("TARGETDIR", None, "SourceDir"),
    ("LocalAppDataFolder", "TARGETDIR", "."),
    ("ALMAWAREDIR", "LocalAppDataFolder", "ALMAWARE"),
    ("INSTALLDIR", "ALMAWAREDIR", "HebrewMic"),
    ("DesktopFolder", "TARGETDIR", "."),
    ("StartupFolder", "TARGETDIR", "."),
]
# Expand to ALL directory levels, including intermediate dirs that hold only
# subdirs (e.g. "profiles" when only "profiles/default" has files). Otherwise an
# intermediate parent is missing and its child re-parents to INSTALLDIR, breaking
# the tree.
all_rel_dirs = set()
for d in dirs:
    if not d:
        continue
    parts = d.split("/")
    for i in range(1, len(parts) + 1):
        all_rel_dirs.add("/".join(parts[:i]))

# map rel_dir -> MSI Directory key
dirkey = {"": "INSTALLDIR"}
# create directory entries for every subdir, parent-first (shallowest first)
for rel in sorted(all_rel_dirs, key=lambda p: p.count("/")):
    parent_rel = "/".join(rel.split("/")[:-1])
    parent_key = dirkey.get(parent_rel, "INSTALLDIR")
    key = _ident("d_" + rel.replace("/", "_"))
    dirkey[rel] = key
    leaf = rel.split("/")[-1]
    # short|long default-dir form with a VALID 8.3 short name.
    directory_rows.append((key, parent_key, _short83(leaf, key) + "|" + leaf))
msilib.add_data(db, "Directory", directory_rows)

# ── Feature table ─────────────────────────────────────────────────────────────
msilib.add_data(db, "Feature", [
    ("MainFeature", None, PRODUCT_NAME, "The Hebrew Mic application", 1, 1,
     "INSTALLDIR", 0),
])

# ── Components + Files (one component per directory; cab the files) ───────────
cab = msilib.CAB("HebMic")
components = []   # (Component, ComponentId, Directory_, Attributes, Condition, KeyPath)
feature_comp = []  # (Feature_, Component_)
file_rows = []   # (File, Component_, FileName, FileSize, Version, Lang, Attributes, Sequence)
seq = 0

for rel in sorted(dirs.keys(), key=lambda p: p.count("/")):
    dkey = dirkey[rel]
    comp = _ident("c_" + (rel.replace("/", "_") if rel else "root"))
    comp_guid = "{" + str(uuid.uuid4()).upper() + "}"
    keypath = None
    comp_files = []
    for fn in sorted(dirs[rel]):
        seq += 1
        abspath = os.path.join(PAYLOAD, *(rel.split("/") if rel else []), fn)
        size = os.path.getsize(abspath)
        file_key = _ident("f_%d_%s" % (seq, fn))
        # short|long filename form with a VALID 8.3 short name.
        filename = _short83(fn, file_key) + "|" + fn
        # cab member's logical name == File-table key so extraction maps 1:1.
        cab.append(abspath, fn, file_key)
        file_rows.append((file_key, comp, filename, size, None, None, 0, seq))
        comp_files.append(file_key)
        if keypath is None:
            keypath = file_key
    components.append((comp, comp_guid, dkey, 0, None, keypath))
    feature_comp.append(("MainFeature", comp))

# A dedicated component for the shortcuts, with a per-user registry keypath
# (per-user components that write to HKCU need a registry keypath, not a file).
SHORTCUT_COMP = "c_shortcuts"
SHORTCUT_GUID = "{" + str(uuid.uuid4()).upper() + "}"
components.append((SHORTCUT_COMP, SHORTCUT_GUID, "INSTALLDIR", 4, None, "RegKeyPath"))
feature_comp.append(("MainFeature", SHORTCUT_COMP))

msilib.add_data(db, "Component", components)
msilib.add_data(db, "FeatureComponents", feature_comp)
msilib.add_data(db, "File", file_rows)

# Registry keypath for the per-user shortcut component (Attributes=4 => HKCU).
msilib.add_data(db, "Registry", [
    ("RegKeyPath", 1,  # 1 = HKCU
     r"Software\ALMAWARE\HebrewMic", "Installed", "1", SHORTCUT_COMP),
])

# ── Icon for ARP + shortcuts ──────────────────────────────────────────────────
ico_src = os.path.join(PAYLOAD, "mic.ico")
if os.path.isfile(ico_src):
    msilib.add_data(db, "Icon", [("MicIcon", msilib.Binary(ico_src))])

# ── Shortcuts (Desktop + Startup) ─────────────────────────────────────────────
# Target = wscript.exe (STABLE system path on every Windows machine) running
# launch.vbs, which resolves a windowless Python (pyw) at runtime and starts
# ALMAWARE_HebMic.pyw with NO console flash. This is far more portable than
# hardcoding pyw.exe's path, which varies per machine.
# [System64Folder] resolves to C:\Windows\System32 on 64-bit Windows.
VBS = "launch.vbs"
shortcut_rows = [
    # Shortcut, Directory_, Name, Component_, Target, Arguments, Description,
    # Hotkey, Icon_, IconIndex, ShowCmd, WkDir
    ("DesktopSC", "DesktopFolder", "ALMAWARE Hebrew Mic", SHORTCUT_COMP,
     "[System64Folder]wscript.exe", '"[INSTALLDIR]%s"' % VBS,
     "Always-on Hebrew/English dictation mic", None, "MicIcon", 0, 1, "INSTALLDIR"),
    ("StartupSC", "StartupFolder", "ALMAWARE Hebrew Mic", SHORTCUT_COMP,
     "[System64Folder]wscript.exe", '"[INSTALLDIR]%s"' % VBS,
     "Start the ALMAWARE Hebrew Mic at logon", None, "MicIcon", 0, 7, "INSTALLDIR"),
]
msilib.add_data(db, "Shortcut", shortcut_rows)

# ── commit cab + media ────────────────────────────────────────────────────────
# CAB.commit() itself inserts the Media row + embeds the cab stream and commits.
cab.commit(db)

db.Commit()
print("OK wrote %s  (%d files, %d components)" % (OUTPUT, len(file_rows), len(components)))
