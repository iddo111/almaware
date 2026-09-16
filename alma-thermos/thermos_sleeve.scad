// ============================================================
// ALMA THERMOS SLEEVE  v1  — printed double-wall jacket
// You drink from a stainless bottle; the printed part never touches the drink.
// Insulation = trapped air gap + (you add) aluminised mylar wrap.
// Print PETG, 0.2mm, 2 walls, 10% infill, NO supports (all vertical).
// ============================================================
$fn = 96;

BOTTLE_D = 73;    // <-- measure YOUR bottle diameter (mm)
BOTTLE_H = 260;   // <-- bottle height
JACKET_H = 210;   // how far up the jacket goes (neck stays free)
CLR      = 0.8;   // slip fit
W_IN     = 1.6;   // inner shell wall
GAP      = 8.0;   // *** the air gap = the insulation ***
W_OUT    = 2.0;   // outer shell wall
FLOOR    = 3.0;
RIBS     = 6;     // spacer ribs keep the gap honest
GRIP     = true;  // finger grooves outside

r_in   = BOTTLE_D/2 + CLR;
r_in_o = r_in + W_IN;
r_out  = r_in_o + GAP;
r_out_o= r_out + W_OUT;

module shell() {
  difference() {
    union() {
      // outer wall
      cylinder(r=r_out_o, h=JACKET_H);
      // base disc
      cylinder(r=r_out_o, h=FLOOR);
    }
    // outer cavity (the air gap) - open at top so it can be printed & wiped
    translate([0,0,FLOOR]) cylinder(r=r_out, h=JACKET_H);
    // finger grooves
    if (GRIP)
      for (z=[JACKET_H*0.35, JACKET_H*0.45, JACKET_H*0.55])
        translate([0,0,z]) rotate_extrude() translate([r_out_o-0.9,0]) circle(r=2.2);
  }
  // inner shell (holds the bottle) - joined only at the floor => low thermal bridge
  translate([0,0,FLOOR])
    difference() {
      cylinder(r=r_in_o, h=JACKET_H-FLOOR);
      translate([0,0,-1]) cylinder(r=r_in, h=JACKET_H);
    }
  // spacer ribs, thin on purpose (less heat path)
  for (a=[0:360/RIBS:359])
    rotate([0,0,a]) translate([r_in_o-0.2, -1.2, FLOOR])
      cube([GAP+0.4, 2.4, JACKET_H-FLOOR-6]);
  // top rim ties the two shells (printable bridge, 2mm)
  translate([0,0,JACKET_H-2])
    difference() { cylinder(r=r_out_o, h=2); translate([0,0,-1]) cylinder(r=r_in, h=4); }
}
shell();
