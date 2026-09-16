"""Read-only ext4 enumeration of E: drive (PhysicalDrive2) via pytsk3.
Output: C:\\Users\\iddo1\\Desktop\\E-drive-files.txt

Requires admin (raw disk access).
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

try:
    import pytsk3
except ImportError:
    print("FATAL: pytsk3 not installed. Run: pip install pytsk3", file=sys.stderr)
    sys.exit(1)

DRIVE = r'\\.\PhysicalDrive2'
OUT = Path(r'C:\Users\<user>\Desktop\E-drive-files.txt')

print(f"Opening raw disk: {DRIVE}")
print(f"Output: {OUT}")
print()

try:
    img = pytsk3.Img_Info(DRIVE)
except OSError as e:
    print(f"FATAL: cannot open {DRIVE} - {e}", file=sys.stderr)
    print("Run this script ELEVATED (Administrator).", file=sys.stderr)
    sys.exit(2)

try:
    vol = pytsk3.Volume_Info(img)
except Exception as e:
    print(f"FATAL: cannot read partition table - {e}", file=sys.stderr)
    sys.exit(3)

print("Partitions found:")
target = None
for part in vol:
    desc = part.desc.decode('utf-8', errors='replace') if isinstance(part.desc, bytes) else str(part.desc)
    print(f"  addr={part.addr}  start={part.start}  len={part.len}  desc={desc}")
    if part.len > 100_000_000:
        target = part

if target is None:
    print("FATAL: no large partition found", file=sys.stderr)
    sys.exit(4)

print(f"\nUsing partition: addr={target.addr} start={target.start} len={target.len}")
print(f"  Size: {target.len * 512 / 1024**3:.1f} GiB")

try:
    fs = pytsk3.FS_Info(img, offset=target.start * 512)
except Exception as e:
    print(f"FATAL: cannot open filesystem - {e}", file=sys.stderr)
    sys.exit(5)

fs_type_id = fs.info.ftype
print(f"  Filesystem type: {fs_type_id}")

print(f"\nWalking files - writing to {OUT}")
OUT.parent.mkdir(parents=True, exist_ok=True)
fh = OUT.open('w', encoding='utf-8', newline='\n')
fh.write(f"# E: drive (PhysicalDrive2) full file inventory\n")
fh.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
fh.write(f"# Partition: addr={target.addr} size={target.len * 512 / 1024**3:.1f}GiB\n")
fh.write(f"# Filesystem type ID: {fs_type_id}\n")
fh.write(f"#\n")
fh.write(f"# Columns: SIZE_BYTES\\tMTIME_UNIX\\tPATH\n")
fh.write(f"#\n\n")

count = 0
err_count = 0
total_bytes = 0

def walk(directory, path_prefix):
    global count, err_count, total_bytes
    for entry in directory:
        try:
            name = entry.info.name.name.decode('utf-8', errors='replace')
            if name in ('.', '..'):
                continue
            full_path = path_prefix + '/' + name
            meta = entry.info.meta
            if meta is None:
                continue
            mtime = meta.mtime if meta.mtime else 0
            size = meta.size
            type_ = meta.type
            if type_ == pytsk3.TSK_FS_META_TYPE_DIR:
                fh.write(f"DIR\t{mtime}\t{full_path}/\n")
                count += 1
                try:
                    sub = entry.as_directory()
                    walk(sub, full_path)
                except Exception:
                    err_count += 1
            elif type_ == pytsk3.TSK_FS_META_TYPE_REG:
                fh.write(f"{size}\t{mtime}\t{full_path}\n")
                count += 1
                total_bytes += size
            else:
                fh.write(f"OTHER({type_})\t{mtime}\t{full_path}\n")
                count += 1
            if count % 5000 == 0:
                print(f"  {count:,} entries / {total_bytes/1024**3:.1f} GiB / {err_count} errors")
                fh.flush()
        except Exception as e:
            err_count += 1

root = fs.open_dir('/')
walk(root, '')

fh.write(f"\n# DONE - {count} entries, {total_bytes/1024**3:.2f} GiB total, {err_count} errors\n")
fh.close()

print()
print(f"DONE")
print(f"  Total entries: {count:,}")
print(f"  Total size:    {total_bytes/1024**3:.2f} GiB")
print(f"  Errors:        {err_count}")
print(f"  Output:        {OUT}  ({OUT.stat().st_size/1024**2:.1f} MiB)")
