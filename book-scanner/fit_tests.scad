// Fit tests for ALMA BOOK SCANNER v1.
// Each test INTERSECTS a printed part with the real thing it must accept.
// A passing test renders an EMPTY object. Anything non-empty is interference.
//   openscad -o t.stl -D 'test="carriage_on_rail"' fit_tests.scad
include <alma_book_scanner.scad>
part = "none";      // last assignment wins: stops the master selector
                    // from also rendering the exploded layout into the test

// A real 2020: 20x20 with a 6 mm slot mouth, 5 mm deep, on all four faces.
module rail_2020(len){
    difference(){
        translate([-len/2, -rail/2, 0]) cube([len, rail, rail]);
        for (s = [-1,1]){
            translate([-len/2 - 1, s*rail/2 - (s > 0 ? 5 : 0), rail/2 - 3])
                cube([len + 2, 5, 6]);
            translate([-len/2 - 1, -3, s < 0 ? 0 : rail - 5])
                cube([len + 2, 6, 5]);
        }
    }
}

// Same 2020 stood on end: length along +Z centred on 0, section X -10..10,
// Y 0..20. Written as an explicit matrix because chained rotate() calls put
// it on the wrong axis twice and quietly turned a fit test into a lie.
module rail_along_z(len)
    multmatrix([[0,1,0,0],[0,0,1,0],[1,0,0,0],[0,0,0,1]]) rail_2020(len);

test = "none";

// 1. the rail must pass through the carriage, keys in the slots, no touch.
//    Rail sat hard up against the deck - the worst case for the keys.
if (test == "carriage_on_rail")
    intersection(){
        rail_carriage();
        translate([0, 0, car_deck]) rail_2020(140);
    }

// 2. 4 mm glass must enter the clamp channel past the silicone ribs.
else if (test == "clamp_on_glass")
    intersection(){
        glass_edge_clamp();
        translate([gc_M[0], gc_M[1], -5]) rotate([0,0,-wing_rise])
            translate([0.5, -glass_t/2, 0]) cube([30, glass_t, 60]);
    }

// 3. the 6 mm wing panel must enter the bracket slot and lie on the face.
else if (test == "bracket_on_panel")
    intersection(){
        cradle_wing_bracket();
        translate([brk_A[0], brk_A[1], -5]) rotate([0,0,wing_rise])
            cube([130, 6, 28]);
    }

// 4. the vertical post must pass through the camera mount collar.
else if (test == "camera_on_post")
    intersection(){
        camera_mount();
        translate([-40, -10, 22.5]) rail_along_z(80);
    }

// 5. the horizontal side rail must enter the light bracket U.
//    (in this part print-Z runs along the rail, so the same stood-up 2020)
else if (test == "light_on_rail")
    intersection(){
        light_bar_bracket();
        translate([lb_bore/2, clr, lb_len/2]) rail_along_z(90);
    }
