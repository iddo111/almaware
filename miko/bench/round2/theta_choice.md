# Why theta = 0, and the number that argues against it

Validation sweep (300 steps, seed 0, val MAE, lower is better):

    theta = 0      0.2330    always 2-1: the outlier is ALWAYS discarded
    theta = 0.25   0.2391
    theta = 0.5    0.2389
    theta = 1      0.2372
    theta = 2      0.2372
    theta = 1e9    0.2295    <- the CONTROL: this is exactly the plain mean of three

The sweep contained its own control at both ends on purpose, and THE CONTROL WON.
theta -> infinity is not a decisive court at all - it is the mean rule, which is already
a separate arm in the five-way comparison. Selecting it for the "decisive" arm would have
produced two identical arms and left Iddo instruction unmeasured.

So theta is chosen as the best value AMONG THE SETTINGS THAT ACTUALLY DECIDE:
theta = 0, the most decisive one - the outlier is discarded every time.

The fact that not-deciding scored better here is reported as a finding, not hidden.
Caveats that keep it from being conclusive on its own: one seed, 300 steps, and a total
spread of 0.0096 MAE across the whole sweep. The five-way run with 3 seeds settles it.
