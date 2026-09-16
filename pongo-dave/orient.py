"""Orient Dave's U-clip for the K2 Plus (Pongo Shirts job).

Rotation +90 deg about X: (x,y,z) -> (x, -z, y).
The 70 mm channel axis becomes vertical, the U profile lies in the bed plane.
=> every layer is the same closed U ring: NO supports, NO overhangs, and the
spring stress when the arms spread runs IN-PLANE with the layers.
Then the part is dropped to z=0 and centred on the 350x350 bed.
"""
import struct, sys, os

BED = (350.0, 350.0)

def read_stl(p):
    with open(p, 'rb') as f:
        head = f.read(80)
        n = struct.unpack('<I', f.read(4))[0]
        tris = []
        for _ in range(n):
            d = struct.unpack('<12fH', f.read(50))
            tris.append(d)
    return head, tris

def rot(v):                      # +90 deg about X
    x, y, z = v
    return (x, -z, y)

def write_stl(p, tris):
    with open(p, 'wb') as f:
        f.write(b'PONGO/Dave U-clip - K2 Plus print orientation (ALMAWARE)'.ljust(80, b' '))
        f.write(struct.pack('<I', len(tris)))
        for t in tris:
            f.write(struct.pack('<12fH', *t))

def main(src, dst):
    head, tris = read_stl(src)
    out = []
    for t in tris:
        nx, ny, nz = rot(t[0:3])
        vs = [rot(t[3:6]), rot(t[6:9]), rot(t[9:12])]
        out.append((nx, ny, nz, *vs[0], *vs[1], *vs[2], t[12]))
    xs = [c for t in out for c in (t[3], t[6], t[9])]
    ys = [c for t in out for c in (t[4], t[7], t[10])]
    zs = [c for t in out for c in (t[5], t[8], t[11])]
    dx = BED[0]/2 - (min(xs)+max(xs))/2
    dy = BED[1]/2 - (min(ys)+max(ys))/2
    dz = -min(zs)
    moved = []
    for t in out:
        moved.append((t[0], t[1], t[2],
                      t[3]+dx, t[4]+dy, t[5]+dz,
                      t[6]+dx, t[7]+dy, t[8]+dz,
                      t[9]+dx, t[10]+dy, t[11]+dz, t[12]))
    write_stl(dst, moved)
    xs2 = [c for t in moved for c in (t[3], t[6], t[9])]
    ys2 = [c for t in moved for c in (t[4], t[7], t[10])]
    zs2 = [c for t in moved for c in (t[5], t[8], t[11])]
    print('%s -> %s' % (os.path.basename(src), os.path.basename(dst)))
    print('  triangles %d' % len(moved))
    print('  bbox X %.2f..%.2f  Y %.2f..%.2f  Z %.2f..%.2f' %
          (min(xs2), max(xs2), min(ys2), max(ys2), min(zs2), max(zs2)))
    print('  size %.2f x %.2f x %.2f mm' %
          (max(xs2)-min(xs2), max(ys2)-min(ys2), max(zs2)-min(zs2)))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
