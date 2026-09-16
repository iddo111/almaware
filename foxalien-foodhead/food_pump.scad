// ============================================================
// FoxAlien FOOD-PASTE PUMP  v1  — syringe extruder for the CNC
// Mounts where the spindle sits (52mm shank into the FoxAlien clamp).
// NEMA 17 turns a T8 leadscrew -> pushes the 60ml syringe plunger.
// Print PETG or PLA, 0.2mm, 4 walls, 40% infill. Food only touches the
// syringe + metal nozzle (food-grade); the plastic never meets the paste.
// ============================================================
$fn = 96;

// ---- measured / standard parameters (edit to your parts) ----
SHANK_D   = 52;    // FoxAlien spindle-clamp bore (400W spindle = 52mm)
SYR_D     = 27;    // 60ml luer-lock syringe barrel OD (BASIK ~27mm)
SYR_LEN   = 130;   // barrel length
NEMA      = 42.3;  // NEMA-17 body
NEMA_HOLE = 31;    // NEMA-17 bolt spacing
NEMA_BORE = 22.5;  // NEMA-17 pilot boss
SCREW_D   = 8;     // T8 leadscrew
NUT_D     = 10.2;  // T8 brass nut flange fits a POM/printed carrier
WALL      = 3;
PLATE     = 6;
TRAVEL    = 100;   // plunger stroke

// ---------------------------------------------------------------- top: NEMA plate
module nema_plate() {
  difference() {
    translate([-25,-25,0]) cube([50,50,PLATE]);
    translate([0,0,-1]) cylinder(d=NEMA_BORE, h=PLATE+2);        // shaft boss
    for (x=[-1,1]) for (y=[-1,1])
      translate([x*NEMA_HOLE/2, y*NEMA_HOLE/2, -1]) cylinder(d=3.4, h=PLATE+2);
  }
}

// ---------------------------------------------------------------- the shank into the clamp
module shank() {
  difference() {
    cylinder(d=SHANK_D, h=34);
    translate([0,0,-1]) cylinder(d=SHANK_D-2*6, h=36);           // hollow to save plastic
    // a slit so the clamp grips it tight
    translate([-1.2,0,-1]) cube([2.4, SHANK_D, 36]);
  }
}

// ---------------------------------------------------------------- syringe cradle (two rings)
module cradle_ring(z) {
  translate([0,0,z]) difference() {
    cube([SYR_D+2*WALL, SYR_D+2*WALL, 10], center=true);
    cylinder(d=SYR_D+0.6, h=12, center=true);
    translate([0,-(SYR_D+2*WALL)/2, -6]) cube([2.4, SYR_D, 12]); // snap gap
  }
}

// ---------------------------------------------------------------- plunger pusher (rides the nut)
module pusher() {
  difference() {
    union() {
      cube([SYR_D+2*WALL, SYR_D+2*WALL, 12], center=true);       // pushes the plunger flange
      translate([0,0,6]) cube([NUT_D+8, NUT_D+8, 10], center=true);
    }
    translate([0,0,6]) cylinder(d=NUT_D, h=12, center=true);     // captures the T8 nut
    for (a=[0:60:359]) translate([0,0,6]) rotate([0,0,a])
      translate([NUT_D/2,0,0]) cylinder(d=2.6, h=12, center=true); // nut set-screw ring
  }
}

// ---------------------------------------------------------------- assembly (exploded view)
module assembly() {
  color("SteelBlue") shank();
  translate([0,0,40])  color("Gainsboro") nema_plate();
  translate([0,0,-16]) color("SkyBlue")   cradle_ring(0);
  translate([0,0,-16-SYR_LEN+20]) color("SkyBlue") cradle_ring(0);
  translate([0,0,-16-30]) color("Khaki")  pusher();
  // the leadscrew, for reference
  translate([0,0,40]) color("Silver") cylinder(d=SCREW_D, h=-140);
}

// print the four parts flat, side by side, ready to slice
PRINT = true;
if (PRINT) {
  nema_plate();
  translate([70,0,0])  rotate([0,0,0]) cradle_ring(0);
  translate([140,0,0]) cradle_ring(0);
  translate([0,80,0])  pusher();
  translate([90,80,0]) shank();
} else assembly();
