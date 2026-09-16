// ============================================================
// ALMAWARE  WATER NEURON  v1  — printable analog neuron
// לזכרה של עלמה ז"ל
// y = ReLU( w1*x1 + w2*x2 + w3*x3 - theta )
//   chamber = summation      spout height = threshold
//   inlet needle valves = weights (external aquarium valves)
//   bottom drain = decay / negative weight
// Print: PETG (watertight), 0.2mm, 3 walls, 25% infill, NO supports
// ============================================================
$fn = 64;

// ---- parameters (change these, everything follows) ----
D_in      = 40;    // inner chamber diameter (mm)  -> A = 12.6 cm^2
H         = 90;    // chamber inner height (mm)
WALL      = 2.4;   // wall thickness (3 perimeters @0.4 => watertight)
BASE      = 3.0;   // floor thickness
PORT_ID   = 4.0;   // silicone tube inner diameter 4mm
PORT_OD   = 7.0;   // barb outer body
PORT_L    = 14;    // port length outside the wall
THETA     = 45;    // *** THRESHOLD *** spout centre height above floor (mm)
INLET_Z   = 78;    // inlets enter high, above max water line
DRAIN_ID  = 2.0;   // decay drain (small = slow forgetting)
RULER     = true;  // mm ticks up the side
STACK     = true;  // feet + top notch so neurons stack into layers

module barb(id=PORT_ID, od=PORT_OD, len=PORT_L) {
  difference() {
    union() {
      cylinder(d=od, h=len);
      // three grip rings so the tube cannot pop off under head pressure
      for (z=[len*0.35, len*0.6, len*0.85])
        translate([0,0,z]) cylinder(d1=od+1.4, d2=od, h=2.2);
    }
    translate([0,0,-1]) cylinder(d=id, h=len+2);
  }
}

module chamber() {
  difference() {
    union() {
      cylinder(d=D_in+2*WALL, h=H+BASE);
      if (STACK) cylinder(d=D_in+2*WALL+8, h=4);          // foot flange
    }
    translate([0,0,BASE]) cylinder(d=D_in, h=H+1);          // the bowl
    // ---- 3 inlets (the dendrites), 120 deg apart, entering high ----
    for (a=[0,120,240])
      rotate([0,0,a]) translate([0,0,INLET_Z])
        rotate([0,90,0]) cylinder(d=PORT_ID, h=D_in);
    // ---- the axon: overflow spout at THETA ----
    rotate([0,0,60]) translate([0,0,THETA])
      rotate([0,90,0]) cylinder(d=PORT_ID, h=D_in);
    // ---- decay drain at the floor ----
    rotate([0,0,180]) translate([0,0,BASE+3])
      rotate([0,90,0]) cylinder(d=DRAIN_ID, h=D_in);
    // ---- ruler ticks: read the "number" with your eye ----
    if (RULER)
      for (z=[5:5:H-5])
        rotate([0,0,30]) translate([D_in/2+WALL-1.2, -4, BASE+z])
          cube([1.2, (z%10==0)?8:4, 0.8]);
  }
  // ---- external barbs ----
  for (a=[0,120,240])
    rotate([0,0,a]) translate([D_in/2-2, 0, INLET_Z]) rotate([0,90,0]) barb(len=PORT_L+WALL+2);
  rotate([0,0,60]) translate([D_in/2-2, 0, THETA]) rotate([0,90,0]) barb(len=PORT_L+WALL+2);
  rotate([0,0,180]) translate([D_in/2-2, 0, BASE+3]) rotate([0,90,0]) barb(id=DRAIN_ID, od=5, len=10+WALL+2);
}

chamber();
