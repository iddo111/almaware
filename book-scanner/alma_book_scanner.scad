// =====================================================================
//  ALMA BOOK SCANNER v1  --  manual V-cradle book scanner
//  Parametric master model.  לזכרה של עלמה ז"ל.
//
//  EVERY PART IS MODELLED IN ITS PRINT ORIENTATION.
//  Z = 0 is the printer bed, so each exported STL drops straight into
//  the slicer with no rotation.  Printer = Creality K2 Plus (350^3);
//  every part fits inside 330 x 330 x 340 with room to spare.
//
//  Render one part:
//    openscad -o stl/rail_carriage.stl -D 'part="rail_carriage"' alma_book_scanner.scad
//
//  MACHINE AXES (assembly, not print):
//    X = left-right.  The two cradle halves separate along X.
//        The 2020 base rail runs along X.
//    Y = front-back.  Operator stands at -Y.  THE FRONT IS SACRED:
//        no part of this machine crosses the front of the cradle.
//    Z = up.
//    Book spine runs along Y.  Pages open to -X and +X.
//    Page width (240) is measured UP THE SLOPE, page height (320)
//    along Y.  Hence glass_w=260 runs up the slope, glass_h=340 along Y.
// =====================================================================

// ---------------------------------------------------------------------
//  PRINTED PARTS - solid volumes MEASURED off the exported STLs, not
//  estimated. "printed" assumes 4 perimeters / 30% infill (~60% of solid)
//  in PLA or PETG at 1.24 g/cm3.
//
//   part                     qty   solid cm3   printed g ea   footprint mm
//   cradle_wing_bracket       4       79.48        59        110.0 x  99.9 x  18
//   rail_carriage             2      170.90       127        110.0 x 190.0 x  26.4
//   platen_hinge_arm        1+1      277.18       206        310.0 x  86.0 x  26
//   glass_edge_clamp          4       32.69        24         26.6 x  44.0 x  50
//   camera_mount (2 pieces) 1+1      100.96        75        126.3 x  46.0 x 110
//   light_bar_bracket       1+1      134.95       100         85.5 x 111.2 x  50
//   thumbscrew_knob           4       11.85         9         35.1 x  36.0 x  13
//   spine_support             1       45.66        34         44.0 x  90.0 x  20.8
//   camera_mount_phone_jaw    2       22.50        17         78.0 x  22.0 x  18
//   TOTAL solid, all quantities: 1954.7 cm3.
//   At 4 perimeters / 30% infill (~0.60 of solid) that is ~1.45 kg of PLA
//   and roughly 27 h of machine time at 0.2 mm on a K2 Plus.
//   "1+1" means a HANDED PAIR: print the module AND its _mirror, not two
//   of the same. Applies to platen_hinge_arm, camera_mount, light_bar_bracket.
//  Largest part is 310 mm long: 20 mm of margin on a 330 mm envelope and
//  40 mm on the real K2 Plus bed. NOTHING needs support material.
//
//  HARDWARE (all M3 or M5, nothing else)
//   2020 extrusion : 1x 500 base rail, 2x ~300 rear posts,
//                    2x ~600 camera posts, 2x ~400 light side rails
//   M3 heat-set inserts  28   (16 wing bracket - 2 panel + 2 foot each,
//                              8 arm, 4 light. NONE in the carriage: its
//                              4 deck holes are clearance, the screws go
//                              UP from underneath into the bracket feet.)
//   M3 screws            28   (8x 20 mm carriage->bracket foot,
//                              8x 16 mm panel, 8x 12 mm glass clamps,
//                              4x 12 mm LED channel)
//   M5 T-nuts             6   (2 carriage locks, 2 camera collars, 2 lights)
//   M5 bolts              8   (16 mm and 30 mm) + 4 M5 nuts for the knobs
//   8 mm smooth rod    480 mm + 4x 8 mm shaft collars
//   glass                2x 260 x 340 x 4 mm float, edges seamed
//   silicone strip       1 mm x ~1.5 m, or split fuel hose
//   plywood              2x 260 x 300 x 6 mm wing panels
//   1/4-20 nuts           2
// ---------------------------------------------------------------------

/* ---- FIXED PARAMETERS -- spec contract, do not rename -------------- */
book_w       = 240;          // max page width, mm
book_h       = 320;          // max page height, mm
book_t_max   = 80;           // max total book thickness, mm
cradle_angle = 100;          // the V angle, degrees (each wing 50 deg off vertical)
glass_w      = 260;          // each glass pane, mm
glass_h      = 340;
glass_t      = 4;            // 4 mm float glass
rail         = 20;           // 2020 aluminium extrusion, 20x20 mm
rail_len     = 500;          // base rail length
wall         = 3.2;          // 4 perimeters at 0.4 nozzle
m5           = 5.3;  m5_head = 9.6;    // clearance holes for M5 (T-nuts into the extrusion)
m3           = 3.3;  m3_insert = 4.6;  // M3 heat-set insert OD
clr          = 0.35;         // print clearance on mating parts

/* ---- DERIVED ------------------------------------------------------- */
eps       = 0.02;                  // anti-coincident-face epsilon
wing_off  = cradle_angle / 2;      // 50 deg off vertical
wing_rise = 90 - wing_off;         // 40 deg above horizontal  <- panel slope
slot_w    = 6.0;                   // 2020 side-slot mouth width
slot_key  = slot_w - 2*clr;        // 5.3  printed key that runs in the slot
slot_key_d= 1.4;                   // how deep the key enters the slot mouth
nut5_af   = 8.1;                   // M5 nut across flats + fit
nut5_cd   = nut5_af / cos(30);     // hex circumscribed dia
nut_q_af  = 11.5;                  // 1/4-20 nut across flats + fit
nut_q_cd  = nut_q_af / cos(30);
rod_d     = 8;                     // platen hinge rod, 8 mm smooth steel

$fn = 64;                          // plenty for M3/M5 holes; bumped locally where it matters

/* ---- SHARED GEOMETRY (both the carriage and the brackets use these) - */
car_len   = 110;                   // carriage bearing length along the rail (X)
car_wid   = 190;                   // carriage deck width across the rail (Y)
car_deck  = 6;                     // deck thickness
car_leg   = 4.0;                   // leg wall thickness
car_bore  = rail + 2*clr;          // 20.70  sliding fit across the rail
car_lift  = rail + clr;            // 20.35  sliding fit over the rail
brk_pitch = 130;                   // Y spacing between the front and back wing brackets
brk_bolt  = 70;                    // X spacing of the 2 M3 bolts in one bracket foot
brk_len   = 110;                   // bracket footprint along X  (= car_len)
brk_th    = 18;                    // bracket thickness along Y

/* ---- SMALL HELPERS -------------------------------------------------- */
// through hole along +Z
module zhole(d, h, z=0) translate([0,0,z-eps]) cylinder(d=d, h=h+2*eps);

// hole along +Y (used for every horizontally-printed hole)
module yhole(d, h, p=[0,0,0]) translate(p) rotate([-90,0,0]) cylinder(d=d, h=h, center=true);

// M5 nut pocket, opening +Z
module nut5(depth, z=0) translate([0,0,z-eps]) cylinder(d=nut5_cd, h=depth+eps, $fn=6);

// =====================================================================
// 1. cradle_wing_bracket()            PRINT 4x
// ---------------------------------------------------------------------
// WHAT: sets the 100 deg V. Two per side (front + back). The foot is bolted
//   to the rail_carriage deck by 2x M3 driven UP FROM UNDER THE CARRIAGE
//   into heat-set inserts in this foot; the inclined top face carries the user-cut
//   6 mm wing panel. The panel LOWER edge slides into a 6.5 mm slot,
//   15 mm deep, then is screwed down onto the face through 2x M3
//   heat-set inserts in this bracket.
// PRINT: on its side - the whole shape is a flat 2D profile extruded
//   18 mm in Z. Lay it exactly as modelled: footprint 110 x 104 mm,
//   18 mm tall. NO SUPPORT ANYWHERE: every wall is vertical; the two
//   insert holes and the two foot holes are small horizontal bores
//   (3.3 / 4.6 mm) that self-bridge.
// ASSEMBLY: drill 2x 3.5 mm holes in the plywood at the marked insert
//   positions (40 mm and 80 mm up the slope from the closed end of the
//   slot). Panel = 6 mm ply or foam board, 260 wide x 300 long. The
//   bracket supports the first 130 mm of the 260 mm slope; the rest
//   cantilevers, which is what keeps the front of the machine open.
// =====================================================================
brk_ft   = 10;                 // foot thickness
brk_A    = [10, 16];           // where the panel face starts (profile coords)
brk_slot = 6.5;                // panel slot width (6 mm panel + fit)
brk_deep = 15;                 // panel slot depth
brk_ins  = [40, 80];           // insert positions, measured up the slope
brk_ins_d= 9;                  // depth of the 2 foot inserts (3 mm floor under them)
brk_top  = brk_A[1] + (brk_len - brk_A[0]) * tan(wing_rise);   // 99.9 mm

module cradle_wing_bracket(){
    difference(){
        linear_extrude(height = brk_th) {
            difference(){
                union(){
                    // main body: foot + the 40 deg wedge
                    polygon([[0,0],[brk_len,0],[brk_len,brk_top],brk_A,[0,brk_A[1]]]);
                    // slot lip and its closed end, built on the panel face
                    translate(brk_A) rotate(wing_rise){
                        translate([0, brk_slot]) square([brk_deep, 4]);
                        translate([-4, 0])       square([4, brk_slot + 4]);
                    }
                    // solid bosses around the two heat-set inserts.
                    // They sit 8 mm BELOW the panel face and are 6.5 mm in
                    // radius, so they stay 1.5 mm clear of the face: a boss
                    // that broke the surface would both lift the panel off
                    // its seat and seal the insert hole into a closed void.
                    for (x = brk_ins)
                        translate(brk_A) rotate(wing_rise)
                            translate([x, -8]) circle(r = 6.5);
                }
                // lightening window (79.6 cm3 solid -> ~59 g printed)
                polygon([[16,12],[brk_len-14,12],[brk_len-14,52]]);
            }
        }
        // 2x M3 HEAT-SET INSERTS opening on the bottom (deck) face.
        // These used to be m3 clearance bores 10 mm long, on the theory that a
        // screw came DOWN through the foot into the carriage. Two things were
        // wrong with that. (a) The solid here is 12 mm deep, not brk_ft=10 -
        // the lightening window starts at y=12 - so the bore dead-ended in
        // 1.97 mm of plastic and no screw could pass. (b) Even bored through,
        // the 40 deg wedge stands directly over both bolt columns, so no
        // driver could ever reach a screw head from above. The joint is
        // therefore made the other way round: inserts here, clearance holes
        // in the carriage deck, screw driven UP from under the deck where
        // there is nothing but open air. Bore 9 mm deep leaves a 3 mm floor.
        for (x = [(brk_len-brk_bolt)/2, (brk_len+brk_bolt)/2])
            translate([x, -eps, brk_th/2]) rotate([-90,0,0])
                cylinder(d = m3_insert, h = brk_ins_d + eps);
        // 2x M3 heat-set inserts, normal to the panel face
        for (x = brk_ins)
            translate([brk_A[0], brk_A[1], brk_th/2]) rotate([0,0,wing_rise])
                translate([x, 0.5, 0]) rotate([90,0,0])
                    cylinder(d = m3_insert, h = 10.5);
    }
}

// =====================================================================
// 2. rail_carriage()                  PRINT 2x   <-- THE CRITICAL PART
// ---------------------------------------------------------------------
// WHAT: slides along the 2020 base rail so each half of the cradle moves
//   independently as the weight of the book shifts from one side to the
//   other. Captures the extrusion on 3 faces (top + both sides) with clr
//   on every mating surface, and is keyed into BOTH side slots by a
//   printed rib. That rib is what stops the carriage rolling outward
//   under the overhung weight of the wing - a plain 3-face clamp would
//   rock. Locks with a single M5 thumbscrew (part 7) that PULLS the
//   carriage against the rail through a T-nut in the side slot: it
//   clamps, it never jacks the carriage up and it cannot rack it.
// WHY IT WILL NOT BIND: bearing length 110 mm on a 20 mm rail = 5.5:1.
//   Past about 3:1 a slider cannot cock and jam. Nothing touches the
//   bottom face of the rail, so a bowed extrusion cannot preload it.
// PRINT: UPSIDE DOWN exactly as modelled - deck flat on the bed, legs
//   pointing up. That is the whole trick: not one overhang, not one
//   bridge, no support anywhere. Footprint 110 x 190 mm, 26.4 mm tall.
//   4 perimeters, >= 30% infill (this part carries the book).
// ASSEMBLY: the face that was on the bed points UP in the machine and is
//   the seat for the two wing brackets. The 4 M3 holes are CLEARANCE, not
//   inserts - the inserts are in the bracket feet and the screws go up
//   from underneath. Slide the carriage on from the END of the rail (the
//   slot keys mean it cannot drop on from above), with the M5 T-nut
//   already in the rail side slot.
// =====================================================================
car_key_z  = car_deck + 10;             // rail side-slot centreline
car_rib_x  = [-50,-26, 26, 50];         // deck stiffeners, clear of the knob swing
car_ins_x  = 35;                        // M3 inserts for the wing brackets
car_lockw  = 26;                        // window in the key that houses the T-nut

module car_key(y_in){                   // tapered rib that runs in the side slot
    hull(){
        translate([-(car_len/2 - 8), y_in, car_key_z - slot_key/2])
            cube([car_len - 16, slot_key_d, slot_key]);
        translate([-car_len/2, y_in, car_key_z - 0.005])
            cube([car_len, slot_key_d, 0.01]);
    }
}

module rail_carriage(){
    difference(){
        union(){
            // ---- deck, rounded corners ----
            hull() for (x = [-1,1], y = [-1,1])
                translate([x*(car_len/2 - 6), y*(car_wid/2 - 6), 0])
                    cylinder(r = 6, h = car_deck);
            // ---- the two legs: 3-face capture on the extrusion ----
            for (s = [-1,1])
                translate([-car_len/2, s*(car_bore/2) - (s < 0 ? car_leg : 0), car_deck])
                    cube([car_len, car_leg, car_lift]);
            // ---- slot keys: anti-roll, anti-lift ----
            difference(){
                union(){
                    car_key(car_bore/2 - slot_key_d);      // +Y leg
                    car_key(-car_bore/2);                  // -Y leg
                }
                translate([-car_lockw/2, car_bore/2 - slot_key_d - eps, car_key_z - slot_key])
                    cube([car_lockw, slot_key_d + 2*eps, 2*slot_key]);
            }
            // ---- deck stiffeners, split so they never enter the rail channel ----
            for (x = car_rib_x, s = [-1,1])
                translate([x - 1.5,
                           s > 0 ? car_bore/2 + car_leg : -(car_wid/2 - 4),
                           car_deck])
                    cube([3, car_wid/2 - car_bore/2 - car_leg - 4, 12]);
            // ---- heat-set insert bosses for the wing brackets ----
            for (x = [-car_ins_x, car_ins_x], y = [-brk_pitch/2, brk_pitch/2])
                translate([x, y, 0]) cylinder(d = 11, h = car_deck + 6);
            // ---- boss around the M5 lock ----
            translate([-car_lockw/2 - 3, car_bore/2 + car_leg - eps, car_deck + 2])
                cube([car_lockw + 6, 6, 18]);
        }
        // ---- M3 CLEARANCE, right through the deck and its boss ----
        // Was a blind 4.6 insert bore 11 mm into a 12 mm boss - a 1.01 mm
        // floor, and it faced the wrong way: it needed a screw coming down
        // through the wing bracket, which the bracket's own wedge blocks.
        // Now the screw runs the other way: up from under the deck (open air
        // at y = +/-65) through this hole and into an insert in the bracket
        // foot. The head seats on the 11 mm boss face. M3 x 20.
        for (x = [-car_ins_x, car_ins_x], y = [-brk_pitch/2, brk_pitch/2])
            translate([x, y, -eps]) cylinder(d = m3, h = car_deck + 6 + 2*eps);
        // ---- M5 thumbscrew -> T-nut in the rail side slot ----
        translate([0, car_bore/2 + car_leg + 6 + eps, car_key_z]) rotate([90,0,0])
            cylinder(d = m5, h = car_leg + 6 + 2*eps);
        // ---- lead-in chamfers so it starts onto the rail cleanly ----
        for (s = [-1,1])
            translate([s*car_len/2, 0, car_deck + car_lift + 0.5]) rotate([0,45,0])
                cube([14, car_wid + 2, 14], center = true);
    }
}

// =====================================================================
// 3. platen_hinge_arm()               PRINT 2x  (the 2nd is mirrored)
// ---------------------------------------------------------------------
// WHAT: the two side beams that carry the glass V. Each arm stands
//   OUTBOARD of its glass pane, so the arm, the pivot boss and the
//   counterweight are never in the light path and never fight the glass.
//   The pane hangs off the INBOARD face on two glass_edge_clamps. The
//   whole platen pivots on one 8 mm smooth rod through the rear bosses
//   and lifts like a lid.
// WHY IT CLEARS THE CRADLE: the rod sits behind and above the rear edge
//   of the glass, and every point of the platen is FORWARD of the rod,
//   so lifting swings the panes up and rearward - away from the wings,
//   never into them. Only the last 25 mm of pane behind the rod dips,
//   and it dips into open air above the rear posts.
// PRINT: flat on its side, exactly as modelled - a 2D profile extruded
//   16 mm, plus a 26 mm pivot boss standing proud on the OUTBOARD face
//   (which faces UP on the bed). Footprint 310 x 86 mm, 26 mm tall.
//   NO SUPPORT: every wall is vertical, the counterweight pocket opens
//   straight up, and the 4 M3 insert holes are vertical blind holes in
//   the bed face.
//   The bed face becomes the INBOARD face, so the two arms are mirror
//   images: print one as modelled and one with slicer mirror-X, or
//   render -D 'part="platen_hinge_arm_mirror"'.
// ASSEMBLY: 8 mm rod through both bosses, retained by two hardware-store
//   8 mm shaft collars outboard of each arm; the rod is carried by the
//   two rear 2020 posts. Set each pane so its OUTER 14 mm sits in the
//   clamps - 260 - 14 = 246 mm of clear glass over a 240 mm page.
//
// COUNTERWEIGHT - the honest numbers (this is a TRIM, not a balance):
//   pocket = 24 x 54 x 11 mm = 14.3 cm3 (~14.0 cm3 with the corner radii).
//   Packed solid with steel washers that is ~112 g; loose coins ~70-80 g.
//   Its lever is 29 mm behind the pivot, so it returns about 3 kg.mm
//   against the ~128 kg.mm the pane applies. It cannot balance the
//   platen and nothing that fits here could.
//   That is fine - you do not want a balanced platen. 4 mm glass at
//   260 x 340 is 884 g per pane, and ~0.9 kg resting on a page is what
//   flattens it. What you want to kill is the SLAM. Use the 5 mm spring
//   anchor in the tail: one light extension spring or a doubled rubber
//   band to the rear post takes 30-40% out of the fall and makes the lid
//   settle instead of drop. For a genuinely light platen use 3 mm
//   acrylic panes (315 g each) instead of 4 mm float glass.
// =====================================================================
arm_len    = 310;
arm_th     = 16;
arm_h      = 70;
arm_piv    = [265, 45];            // pivot centre, profile coords
arm_boss_d = 28;
arm_boss_h = 26;                   // long bearing on the 8 mm rod
arm_bore   = rod_d + 2*clr;        // 8.70 running fit
arm_clamp  = [25, 230];            // where the two glass clamps land (u)
arm_ins_v  = [20, 54];             // the two insert heights per clamp (34 apart)
arm_pkt    = [282, 8, 306, 62];    // counterweight pocket x0,y0,x1,y1
arm_pkt_z  = 5;                    // pocket floor thickness

module rrect(x0, y0, x1, y1, r)    // 2D rounded rectangle
    hull() for (x = [x0+r, x1-r], y = [y0+r, y1-r]) translate([x,y]) circle(r=r);

module platen_hinge_arm(){
    difference(){
        union(){
            linear_extrude(height = arm_th){
                difference(){
                    union(){
                        square([arm_len, arm_h]);                  // main beam
                        translate([288, arm_h]) square([22, 16]);  // spring-anchor tab
                        translate(arm_piv) circle(d = arm_boss_d);
                    }
                    rrect( 60, 20, 130, 50, 8);                    // lightening
                    rrect(145, 20, 215, 50, 8);
                }
            }
            translate([arm_piv[0], arm_piv[1], 0])
                cylinder(d = arm_boss_d, h = arm_boss_h);          // long bearing boss
        }
        // pivot bore, 8 mm rod
        translate([arm_piv[0], arm_piv[1], -eps])
            cylinder(d = arm_bore, h = arm_boss_h + 2*eps, $fn = 96);
        // counterweight pocket - opens upward on the bed, so nothing bridges
        hull() for (x = [arm_pkt[0]+6, arm_pkt[2]-6], y = [arm_pkt[1]+6, arm_pkt[3]-6])
            translate([x, y, arm_pkt_z]) cylinder(r = 6, h = arm_th);
        // spring anchor
        translate([299, arm_h + 8, -eps]) cylinder(d = 5, h = arm_th + 2*eps);
        // 4x M3 heat-set inserts in the bed face = the INBOARD face
        for (u = arm_clamp, v = arm_ins_v)
            translate([u, v, -eps]) cylinder(d = m3_insert, h = 9);
    }
}

module platen_hinge_arm_mirror() mirror([1,0,0]) platen_hinge_arm();

// =====================================================================
// 4. glass_edge_clamp()               PRINT 4x
// ---------------------------------------------------------------------
// WHAT: grips the outer edge of one pane without stressing it. The
//   channel is 6.4 mm wide with a 1 mm retaining rib down each wall,
//   leaving a 4.4 mm mouth: line the channel with 1 mm silicone strip
//   (or split fuel hose) and the 4 mm glass rides on rubber - never on
//   plastic, never on a hard corner. 16 mm of glass sits in the clamp.
// PRINT: standing on its foot face exactly as modelled - a 2D profile
//   extruded 50 mm up. Footprint 27 x 44 mm, 50 mm tall.
//   NO SUPPORT: the channel opens sideways, so nothing bridges.
// ASSEMBLY: 2x M3 x 12 through the foot into the hinge-arm inserts, one
//   high and one low, 34 mm apart, so the PAIR takes the glass moment
//   instead of one bolt slowly working loose. The Ø8 counterbores give
//   both heads a flat seat and let a 2.5 mm hex key in. Fit the silicone
//   first, then slide the pane in from the apex side. The jaw covers the
//   outermost ~20 mm of the pane, so put all of the pane margin at the
//   outer edge and the 240 mm page stays completely clear of it.
// =====================================================================
gc_len   = 50;       // length along the glass edge
gc_foot  = 8;        // foot thickness against the arm
gc_ftall = 44;       // foot height
gc_M     = [10, 30]; // closed end of the channel, profile coords
gc_deep  = 16;       // glass engagement, closed end -> outer face
gc_slot  = 6.4;      // channel width before the silicone
gc_mouth = 4.4;      // gap at the ribs = the glass slot
gc_bolts = [6, 40];  // bolt heights in the foot (34 apart)
gc_rib   = (gc_slot - gc_mouth)/2 + 0.6;   // 1 mm proud + 0.6 mm buried in the wall

module glass_edge_clamp(){
    difference(){
        linear_extrude(height = gc_len){
            union(){
                difference(){
                    hull(){
                        square([gc_foot, gc_ftall]);                       // foot
                        translate(gc_M) rotate(-wing_rise)
                            translate([gc_deep/2 - 2, 0])
                                square([gc_deep + 4, gc_slot + 7.2], center = true);
                    }
                    // the channel, run long so it breaks cleanly out of the jaw
                    translate(gc_M) rotate(-wing_rise)
                        translate([0, -gc_slot/2]) square([gc_deep + 6, gc_slot]);
                }
                // The two 1 mm silicone-retaining ribs, put back INTO the
                // channel. Each rib is grown 0.6 mm INTO its channel wall:
                // if it merely touched the wall along an edge it would come
                // out of CGAL as a separate floating solid, not part of the
                // clamp. Overlap, never abut.
                translate(gc_M) rotate(-wing_rise) for (s = [-1,1])
                    translate([gc_deep - 6, s*(gc_mouth/2 + gc_rib/2)])
                        square([4, gc_rib], center = true);
            }
        }
        // 2x M3 clearance + flat-seat counterbore, foot -> hinge-arm inserts
        for (v = gc_bolts){
            translate([-eps, v, gc_len/2]) rotate([0,90,0])
                cylinder(d = m3, h = gc_foot + 14);
            translate([gc_foot, v, gc_len/2]) rotate([0,90,0])
                cylinder(d = 8, h = gc_foot + 14);
        }
    }
}

// =====================================================================
// 5. camera_mount()                   PRINT 2x  (the 2nd is mirrored)
//    ONE STL, TWO SEPARATE PIECES side by side on the plate:
//      A - post collar + tilt ear      B - camera platform (the L)
// ---------------------------------------------------------------------
// WHAT: A closed collar slides down a 2020 vertical post and locks with
//   one M5 into a T-nut in the post slot. Its front wall runs up into a
//   tilt ear carrying an M5 pivot and a concentric arc slot. The camera
//   platform bolts to the ear with 2x M5 (pivot + arc) and carries a
//   6.5 mm through-hole with a captive 1/4-20 nut. NO THREADS MODELLED.
// TILT: the arc is NOT centred on vertical - it runs 15 to 65 deg, i.e.
//   the page normal (40 deg) PLUS/MINUS 25 deg. At mid-arc the platform
//   sits parallel to the page and the lens looks straight down the page
//   normal, which is the only aiming that keeps a rectangular page
//   rectangular. Lock both M5 and it does not creep.
// WHERE TO PUT THE POST (this is the geometry that makes it work):
//   post 300 mm out from the machine centreline, platform ~295 mm above
//   the cradle apex. That puts the lens ~300 mm from the page centre
//   along the page normal. A 26 mm-equivalent phone camera (69.4 x 49.6
//   deg) then covers 415 x 277 mm at that distance - a 240 x 320 page
//   with the long sensor axis along the page height, ~15-30% margin.
//   Anything closer than 260 mm cannot fit the page in.
//   The glass frame lives outboard of the pane edge, 20 mm outside the
//   page area, so at this standoff no part of it enters the frame.
// PRINT: exactly as modelled, both pieces flat on the bed. Piece A
//   stands with the post bore vertical - a clean square through-hole,
//   no bridging. Piece B is an L printed corner-down: flat leg on the
//   bed, upright leg rising, hex pocket opening UP.
//   Footprint about 120 x 50 mm, 110 mm tall. NO SUPPORT.
// LOAD: this is a single-shear ear. Good for a phone or a compact
//   (<= 500 g). Do not hang a DSLR on it.
// ASSEMBLY: 2x M5x30 + thumbscrew_knob for pivot and arc; 1x M5x16 +
//   T-nut for the post. The second mount is the mirror image - slicer
//   mirror-X, or -D 'part="camera_mount_mirror"'.
// =====================================================================
cm_bore   = rail + 2*clr;      // 20.70 sliding fit on the post
cm_wall   = 4;
cm_col_h  = 45;                // collar height
cm_ear_t  = 8;                 // ear thickness
cm_ear_x0 = -14;
cm_ear_x1 = 36;
cm_ear_h  = 110;
cm_piv    = [0, 90];           // pivot centre in the ear (x,z)
cm_arc_r  = 30;
cm_arc_a  = [15, 65];          // page normal 40 deg, +/-25 deg
cm_plate  = [50, 46, 10];      // camera platform, x y z
cm_up_h   = 60;                // upright leg height

// Arc slot + pivot, bored along Y. Built as ONE 2D annulus sector and
// extruded - a swept union of 50 cylinders is the obvious way to write
// this and it takes CGAL minutes to resolve. One sector takes a second.
module cm_arc_cut(){
    translate([cm_piv[0], cm_bore/2 + cm_ear_t + eps, cm_piv[1]])
        rotate([90,0,0]) linear_extrude(height = cm_ear_t + 1)
            union(){
                circle(d = m5);                                  // pivot
                intersection(){
                    difference(){
                        circle(d = 2*cm_arc_r + m5, $fn = 120);
                        circle(d = 2*cm_arc_r - m5, $fn = 120);
                    }
                    polygon(concat([[0,0]],
                        [for (i = [0:4])
                            let (a = cm_arc_a[0] + i*(cm_arc_a[1]-cm_arc_a[0])/4)
                            [(cm_arc_r + m5 + 20)*sin(a), -(cm_arc_r + m5 + 20)*cos(a)]]));
                }
                for (a = cm_arc_a)                               // rounded ends
                    translate([cm_arc_r*sin(a), -cm_arc_r*cos(a)]) circle(d = m5);
            }
}

module camera_mount_collar(){
    difference(){
        union(){
            translate([-(cm_bore/2 + cm_wall), -(cm_bore/2 + cm_wall), 0])
                cube([cm_bore + 2*cm_wall, cm_bore + 2*cm_wall, cm_col_h]);
            translate([cm_ear_x0, cm_bore/2, 0])
                cube([cm_ear_x1 - cm_ear_x0, cm_ear_t, cm_ear_h]);
        }
        // the post
        translate([-cm_bore/2, -cm_bore/2, -eps])
            cube([cm_bore, cm_bore, cm_col_h + 2*eps]);
        // M5 -> T-nut in the post slot
        translate([0, -(cm_bore/2 + cm_wall + eps), 22]) rotate([-90,0,0])
            cylinder(d = m5, h = cm_wall + 2*eps);
        cm_arc_cut();
    }
}

module camera_mount_plate(){
    difference(){
        union(){
            cube(cm_plate);                                        // flat leg
            translate([0, cm_plate[1] - cm_ear_t, 0])
                cube([cm_plate[0], cm_ear_t, cm_plate[2] + cm_up_h]);
        }
        // 1/4-20 through-hole + captive nut pocket, pocket opens UP
        translate([cm_plate[0]/2, (cm_plate[1] - cm_ear_t)/2, -eps])
            cylinder(d = 6.5, h = cm_plate[2] + 2*eps);
        translate([cm_plate[0]/2, (cm_plate[1] - cm_ear_t)/2, cm_plate[2] - 6])
            cylinder(d = nut_q_cd, h = 6 + eps, $fn = 6);
        // pivot + lock, 30 mm apart to match the arc radius
        for (z = [cm_plate[2] + 18, cm_plate[2] + 48])
            translate([cm_plate[0]/2, cm_plate[1] + eps, z]) rotate([90,0,0])
                cylinder(d = m5, h = cm_ear_t + 2*eps);
    }
}

module camera_mount(){
    translate([-40, 0, 0]) camera_mount_collar();
    translate([ 22, -cm_plate[1]/2, 0]) camera_mount_plate();
}

module camera_mount_mirror() mirror([1,0,0]) camera_mount();

// =====================================================================
// 5b. camera_mount_phone_jaw()        PRINT 2x (only if using phones)
// ---------------------------------------------------------------------
// WHAT: the alternate jaw. Bolts onto the camera platform with the SAME
//   1/4-20 bolt (through the platform, up into the nut captive in this
//   jaw) and turns it into a phone cradle: an 11 mm slot that takes a
//   7-11 mm phone with or without a case, 78 mm of support along the
//   phone edge, and a groove round both lips for a rubber band that
//   holds the phone in. No moving parts, nothing to slip mid-scan.
// PRINT: exactly as modelled, base on the bed, slot opening UP.
//   Footprint 78 x 22 mm, 18 mm tall. NO SUPPORT - the nut pocket opens
//   upward and the lips are plain vertical walls.
// ASSEMBLY: drop the 1/4-20 nut into the pocket in the slot floor, then
//   bolt up from under the camera platform. Phone lens must clear the
//   lip - stand the phone with the lens above the jaw, not inside it.
// =====================================================================
pj_len   = 78;
pj_slot  = 11;      // phone thickness range 7-11 mm
pj_lip   = 5.5;
pj_base  = 10;
pj_liph  = 8;

module camera_mount_phone_jaw(){
    difference(){
        union(){
            translate([-pj_len/2, -(pj_slot/2 + pj_lip), 0])
                cube([pj_len, pj_slot + 2*pj_lip, pj_base]);
            for (s = [-1,1])
                translate([-pj_len/2, s*(pj_slot/2) - (s < 0 ? pj_lip : 0), pj_base])
                    cube([pj_len, pj_lip, pj_liph]);
        }
        // 1/4-20 clearance + captive nut, pocket opens up into the slot floor
        translate([0,0,-eps]) cylinder(d = 6.5, h = pj_base + 2*eps);
        translate([0,0,pj_base - 6]) cylinder(d = nut_q_cd, h = 6 + eps, $fn = 6);
        // Rubber-band groove round the OUTSIDE of both lips.
        // A cube always grows in +Y, so the old single offset put the +Y
        // groove correctly on the outer face but buried the -Y one 1 mm
        // INSIDE the lip - a sealed 2 x 3 mm tunnel no rubber band could
        // ever enter. Centre the cut on each lip's outer face instead, so
        // both grooves are open and 1.5 mm deep into a 5.5 mm lip.
        for (s = [-1,1])
            translate([0, s*(pj_slot/2 + pj_lip), pj_base + 5.5])
                cube([pj_len + 2*eps, 3, 3], center = true);
    }
}

// =====================================================================
// 6. light_bar_bracket()              PRINT 2x  (the 2nd is mirrored)
// ---------------------------------------------------------------------
// WHAT: holds an LED strip (or a 12 mm aluminium LED channel) at 45 deg
//   to the page, aimed from the SIDE and slightly above - never from the
//   front, never square-on. Side-raking light at 45 deg is what kills
//   the specular reflection of the lamp in the glass: the reflection
//   goes to the far side of the cradle instead of into the lens.
//   The fork in front of the LEDs takes a 25 mm polarising sheet; with a
//   second polariser over the lens you can null the last of the sheen.
// MOUNTS ON: a HORIZONTAL 2020 side rail running front-to-back, outboard
//   and above the cradle. The U drops over it from above and one M5
//   pulls down into a T-nut in the rail top slot. 3-face capture.
// PRINT: exactly as modelled - a 2D profile extruded 50 mm up. The U
//   opens sideways on the bed, the fork slots run vertically.
//   Footprint 85.5 x 111.2 mm, 50 mm tall. NO SUPPORT.
// ASSEMBLY: 2x M3 heat-set inserts down the centre of the pad hold the
//   LED channel. Feed the 25 x 3 mm polariser in from either end of the
//   fork; the prongs grip 3 mm of it on each side.
//   The 2nd bracket is the mirror image (slicer mirror-X, or
//   -D 'part="light_bar_bracket_mirror"').
// =====================================================================
lb_len   = 50;                  // along the LED strip
lb_bore  = rail + 2*clr;        // 20.70
lb_wall  = 4;
lb_P     = [55, -60];           // LED pad centre, profile coords
lb_padw  = 46;                  // pad width  (local x)
lb_padt  = 12;                  // pad thickness (local y)
lb_prong = 10;                  // fork prong width
lb_deep  = 18;                  // fork depth in front of the LED face
lb_filt  = 3.4;                 // polarising sheet slot (3 mm sheet + fit)
lb_filt_y= 9;                   // slot stands 9 mm in front of the LEDs
// The prongs were originally set to the edges of the 46 mm pad, which left a
// 26 mm gap between them while the slot cut spanned 36 mm. A spec-size 25 mm
// sheet therefore sat entirely inside the 26 mm gap and was gripped by
// NOTHING - it fell straight out. The fork is now sized from the sheet:
// the gap is narrower than the sheet, so each prong grips lb_eng of it.
lb_filt_w= 25;                  // polarising sheet WIDTH - spec: a 25 x 3 mm slot
lb_eng   = 3;                   // how far each prong grips the sheet
lb_gap   = lb_filt_w - 2*lb_eng;   // 19 mm clear aperture between the prongs
lb_cut   = lb_filt_w/2 + 2;        // 14.5 half-length of the slot cut

module light_bar_bracket(){
    difference(){
        linear_extrude(height = lb_len){
            difference(){
                union(){
                    // ---- U-clamp on the horizontal 2020, opening downward ----
                    difference(){
                        translate([-lb_wall, 0]) square([lb_bore + 2*lb_wall, lb_bore + lb_wall]);
                        translate([0, -eps]) square([lb_bore, lb_bore + eps]);
                    }
                    // ---- arm down to the lamp pad ----
                    hull(){
                        translate([lb_bore, 0]) square([lb_wall, 10]);
                        translate(lb_P) rotate(45) translate([-lb_padw/2, 0])
                            square([lb_padw, lb_padt]);
                    }
                    // ---- fork that carries the polariser ----
                    // inner faces at +/-lb_gap/2 so the sheet is captured
                    translate(lb_P) rotate(45) for (s = [-1,1])
                        translate([s > 0 ? lb_gap/2 : -(lb_gap/2 + lb_prong), -lb_deep])
                            square([lb_prong, lb_deep]);
                }
                // polariser slot: cuts into both prongs, open at both ends of the
                // print. 2*lb_cut = 29 mm of cut across a 10 mm prong that starts
                // at 9.5, so 5 mm of each prong survives and the fork stays one body.
                translate(lb_P) rotate(45)
                    translate([-lb_cut, -lb_filt_y - lb_filt]) square([2*lb_cut, lb_filt]);
            }
        }
        // M5 down through the top wall -> T-nut in the rail top slot
        translate([lb_bore/2, lb_bore + lb_wall + eps, lb_len/2]) rotate([90,0,0])
            cylinder(d = m5, h = lb_wall + 2*eps);
        // 2x M3 heat-set inserts for the LED channel, normal to the 45 deg pad
        for (z = [12, 38])
            translate([lb_P[0], lb_P[1], z]) rotate([0,0,45])
                translate([0, -0.5, 0]) rotate([-90,0,0]) cylinder(d = m3_insert, h = 10.5);
    }
}

module light_bar_bracket_mirror() mirror([1,0,0]) light_bar_bracket();

// =====================================================================
// 7. thumbscrew_knob()                PRINT 4x  (print 6, you will lose one)
// ---------------------------------------------------------------------
// WHAT: the printed knob for every M5 in the machine that a human turns
//   by hand - the two carriage locks and the two camera tilt locks.
//   36 mm across the lobes: enough torque from two fingers to clamp a
//   carriage, not enough to strip a T-nut.
// PRINT: flat on the bed exactly as modelled, nut pocket UP.
//   Footprint 36 x 36 mm, 13 mm tall. NO SUPPORT (the hex pocket opens
//   upward, the bottom edge is chamfered against elephant foot).
// ASSEMBLY: press an M5 nut into the pocket - it is 8.1 mm across flats
//   against a 8.0 mm nut, so it is a light interference fit; add a drop
//   of thread-lock or superglue at the rim, NOT in the threads. Then run
//   the M5 bolt up through the 5.3 mm bore and jam it against the nut.
// =====================================================================
kn_d     = 36;
kn_h     = 13;
kn_lobes = 6;
kn_lobe_d= 10;

module thumbscrew_knob(){
    difference(){
        union(){
            cylinder(d1 = kn_d - 1.6, d2 = kn_d, h = 0.8);   // anti-elephant-foot chamfer
            translate([0,0,0.8]) cylinder(d = kn_d, h = kn_h - 0.8);
        }
        for (i = [0 : kn_lobes - 1])
            rotate([0, 0, i * 360/kn_lobes])
                translate([kn_d/2 + kn_lobe_d/2 - 2.2, 0, -eps])
                    cylinder(d = kn_lobe_d, h = kn_h + 2*eps);
        translate([0,0,-eps]) cylinder(d = m5, h = kn_h + 2*eps);       // M5 shank
        translate([0,0,kn_h - 4.5]) cylinder(d = nut5_cd, h = 4.5 + eps, $fn = 6);
    }
}

// =====================================================================
// 8. spine_support()                  PRINT 1x
// ---------------------------------------------------------------------
// WHAT: the little wedge that lives in the bottom of the V and stops the
//   spine of a thick book dropping into the gap between the two wing
//   panels. Its two flanks are cut at the wing angle so it beds down on
//   both panels; its flat top carries the spine. Stick a strip of felt
//   on the flat face.
// IT BRIDGES: with the two carriages run in to their closest (a 10 mm
//   gap between them) the inboard edges of the two wing panels are
//   30 mm apart. At 44 mm across, this wedge lands 7 mm onto each panel
//   and cannot fall through. Run the carriages further out for a thicker
//   book and the gap opens - print a wider one by raising spine_hw; the
//   height follows the width through the wing angle automatically.
// PRINT: exactly as modelled - flat face DOWN on the bed, ridge UP. A
//   90 mm prism, footprint 44 x 90 mm, 20.8 mm tall. The flanks rise at
//   40 deg from the bed, which is a 50 deg overhang and prints clean
//   without support on any normal profile.
// SUPPORT: none.
//
// IT MUST NOT FOUL THE GLASS - here is the actual rule:
//   Closing the platen on a book of thickness t lifts the glass apex
//   above the cradle apex by (t/2)/sin(50 deg) = 1.305 * t/2.
//   This wedge stands 20.8 mm proud of the cradle apex, so you need
//   1.305 * t/2 > 22.8 mm  ->  t > ~35 mm.
//   USE IT ONLY ON BOOKS THICKER THAN ~35 mm. Under that a spine does
//   not sag anyway, and leaving the wedge in would hold the glass off
//   the page - which is exactly the fault it is supposed to prevent.
// =====================================================================
spine_hw   = 22;                                  // half width
spine_side = 2.3;                                 // vertical side wall
spine_h    = spine_side + spine_hw * tan(wing_rise);   // 20.76 mm proud
spine_len  = 90;

module spine_support(){
    rotate([90,0,0]) linear_extrude(height = spine_len, center = true)
        polygon([[-spine_hw, 0],
                 [ spine_hw, 0],
                 [ spine_hw, spine_side],
                 [ 0,        spine_h],
                 [-spine_hw, spine_side]]);
}

// =====================================================================
//  ASSEMBLY GEOMETRY - the numbers the machine actually stands on.
//  Datum: baseboard top = Z 0, machine centreline = X 0, spine along Y,
//  operator at -Y.
//    rail top            Z = 20
//    carriage deck top   Z = 26
//    carriages at their closest: centres at X = +/-60, 10 mm apart
//    wing panel inboard edges then sit 30 mm apart
//    virtual V apex      Z = 37.3   (where the two panel planes meet)
//    platen pivot rod    Z = 237, Y = +145, X = +/-220
//  Nothing crosses Y = -170. The front is sacred.
// =====================================================================
asm_t      = 40;                                   // demo book thickness
asm_deck_z = rail + car_deck;
asm_car_x  = 60;
asm_brk_x  = asm_car_x - brk_len/2;
asm_face   = [asm_brk_x + brk_A[0], asm_deck_z + brk_A[1]];
asm_n      = [-sin(wing_rise), 0, cos(wing_rise)];  // panel up-normal
asm_d      = [ cos(wing_rise), 0, sin(wing_rise)];  // up the slope
asm_pane0  = [asm_face[0], 0, asm_face[1]] + (6 + asm_t/2)*asm_n + 8*asm_d;
asm_pane_o = asm_pane0 + glass_w*asm_d + (glass_t/2)*asm_n;
asm_xface  = asm_pane_o[0] + gc_M[0];              // arm inboard face
asm_z0     = asm_pane_o[2] - gc_M[1];              // clamp datum
asm_arm_z  = asm_z0 - 14;
asm_arm_y  = -120;
asm_apex_z = (asm_face[1] + 6*cos(wing_rise))
             - (asm_face[0] - 6*sin(wing_rise)) * tan(wing_rise);

module asm_half(){
    color("SteelBlue")
        translate([asm_car_x, 0, asm_deck_z]) rotate([180,0,0]) rail_carriage();
    color("DarkOrange")
        for (y = [-1,1])
            translate([asm_brk_x, y*brk_pitch/2 + brk_th/2, asm_deck_z])
                rotate([90,0,0]) cradle_wing_bracket();
    // user-cut 6 mm wing panel
    %translate([asm_face[0], -150, asm_face[1]])
        rotate([0,-wing_rise,0]) cube([glass_w, 300, 6]);
    // one half of the book
    %translate([asm_face[0], -book_h/2, asm_face[1]])
        rotate([0,-wing_rise,0]) translate([2,0,6]) cube([book_w, book_h, asm_t/2]);
    // 4 mm glass pane
    %translate(asm_pane0) rotate([0,-wing_rise,0])
        translate([0,-glass_h/2,0]) cube([glass_w, glass_h, glass_t]);
    color("SeaGreen")
        translate([asm_xface, asm_arm_y, asm_arm_z])
            rotate([0,0,90]) rotate([90,0,0]) platen_hinge_arm();
    color("Crimson")
        for (u = arm_clamp)
            translate([asm_xface, asm_arm_y + u - gc_len/2, asm_z0])
                rotate(180,[0,1,1]) glass_edge_clamp();
}

module assembly_preview(){
    %translate([-280,-210,-12]) cube([560, 420, 12]);            // baseboard
    %translate([-rail_len/2, -rail/2, 0]) cube([rail_len, rail, rail]);
    for (s = [0,1]) mirror([s,0,0]) asm_half();
    color("Gold") translate([0, 0, asm_apex_z + spine_h])
        rotate([180,0,0]) spine_support();
    // rear posts carrying the 8 mm pivot rod
    %for (s = [-1,1]) translate([s*220 - rail/2, 145 - rail/2, 0])
        cube([rail, rail, 237]);
    %translate([-240, 145, 237]) rotate([0,90,0]) cylinder(d = rod_d, h = 480);
}

// =====================================================================
//  EXPLODED LAYOUT - every printed part, each on its own bed footprint,
//  all in true print orientation. This is the eyeball check: if a part
//  looks wrong here, it will print wrong.
// =====================================================================
module exploded(){
    translate([   0,    0, 0]) platen_hinge_arm();
    translate([   0,  120, 0]) cradle_wing_bracket();
    translate([ 200,  120, 0]) camera_mount();
    translate([ 350,  120, 0]) camera_mount_phone_jaw();
    translate([  60,  360, 0]) rail_carriage();
    translate([ 250,  350, 0]) light_bar_bracket();
    translate([ 420,  300, 0]) spine_support();
    for (i = [0:3]) translate([i*60 +  20, 520, 0]) thumbscrew_knob();
    for (i = [0:3]) translate([i*50 + 280, 500, 0]) glass_edge_clamp();
}

// =====================================================================
//  PART SELECTOR
//    openscad -o stl/<name>.stl -D 'part="<name>"' alma_book_scanner.scad
// =====================================================================
part = "all";

if      (part == "cradle_wing_bracket")     cradle_wing_bracket();
else if (part == "rail_carriage")           rail_carriage();
else if (part == "platen_hinge_arm")        platen_hinge_arm();
else if (part == "platen_hinge_arm_mirror") platen_hinge_arm_mirror();
else if (part == "glass_edge_clamp")        glass_edge_clamp();
else if (part == "camera_mount")            camera_mount();
else if (part == "camera_mount_mirror")     camera_mount_mirror();
else if (part == "camera_mount_phone_jaw")  camera_mount_phone_jaw();
else if (part == "light_bar_bracket")       light_bar_bracket();
else if (part == "light_bar_bracket_mirror")light_bar_bracket_mirror();
else if (part == "thumbscrew_knob")         thumbscrew_knob();
else if (part == "spine_support")           spine_support();
else if (part == "assembly")                assembly_preview();
else if (part == "all")                     exploded();
else echo(str("UNKNOWN part: ", part));
