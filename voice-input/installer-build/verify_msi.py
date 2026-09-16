"""verify_msi.py — open the built MSI and dump its key tables to prove validity."""
import sys
import msilib

msi = sys.argv[1]
db = msilib.OpenDatabase(msi, msilib.MSIDBOPEN_READONLY)


def query(sql):
    v = db.OpenView(sql)
    v.Execute(None)
    rows = []
    while True:
        r = v.Fetch()
        if r is None:
            break
        rows.append(tuple(r.GetString(i + 1) for i in range(r.GetFieldCount())))
    v.Close()
    return rows


print("=== Property ===")
for r in query("SELECT Property, Value FROM Property"):
    print("  ", r)

print("=== Summary Information ===")
si = db.GetSummaryInformation(0)
# PID: 2=Subject,3=Author,7=Template,9=RevNumber(PackageCode),14=PageCount,15=WordCount
for pid, name in [(2, "Subject"), (3, "Author"), (7, "Template"),
                  (9, "PackageCode"), (14, "PageCount(min MSI ver)"),
                  (15, "WordCount")]:
    try:
        print("  %-22s %s" % (name, si.GetProperty(pid)))
    except Exception as e:
        print("  %-22s <err %s>" % (name, e))

print("=== Directory (count) ===")
print("  rows:", len(query("SELECT Directory FROM Directory")))

print("=== Feature ===")
for r in query("SELECT Feature, Title FROM Feature"):
    print("  ", r)

print("=== Component (count + keypaths) ===")
comps = query("SELECT Component, Directory_, KeyPath FROM Component")
print("  rows:", len(comps))
for r in comps:
    print("  ", r)

print("=== Media ===")
for r in query("SELECT DiskId, LastSequence, Cabinet FROM Media"):
    print("  ", r)

print("=== Shortcut ===")
for r in query("SELECT Shortcut, Directory_, Name, Target, Arguments FROM Shortcut"):
    print("  ", r)

print("=== File (count) ===")
files = query("SELECT File, FileName FROM File")
print("  rows:", len(files))
for r in files[:6]:
    print("   sample:", r)

print("=== Registry ===")
for r in query("SELECT `Registry`, `Root`, `Key`, `Name`, `Value` FROM `Registry`"):
    print("  ", r)

print("\nVALID: database opened and all core tables queried successfully.")
