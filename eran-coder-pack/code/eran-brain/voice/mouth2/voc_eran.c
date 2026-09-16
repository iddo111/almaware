/* voc_eran.c -- the fast C twin of MOUTH v2 (glottis.py + tract_core.py).
 *
 * THE REFERENCE IS THE TRUTH. This file is a line-for-line port of the
 * numeric loops in glottis.py (GlottalSource.render) and tract_core.py
 * (render + _dcblock). It must MATCH the reference, never improve it.
 * Every expression keeps the reference's operand grouping (Python/numpy
 * left-associative evaluation), because the parity gate is a bit-level
 * comparison, not a "sounds the same" comparison.
 *
 * NOISE CONTRACT (the design decision that buys bit-parity)
 * =========================================================
 * numpy's PCG64 is NOT reimplemented here. All random draws are made in
 * Python by fastcore.py using the exact streams of glottis.stream_rng
 * (seed + 1000*k; k: jitter 1, shimmer 2, drift 3, vibrato 4,
 * aspiration 5, turbulence 6) and passed in as arrays:
 *   - jit/shm/drf: per-period standard normals, consumed sequentially
 *     (verified: numpy block draws == repeated scalar draws, same stream)
 *   - vib_rate/vib_phase: the vibrato stream's two uniforms, pre-applied
 *   - flutter[n]: the aspiration stream's uniform (phase) already folded
 *     into the 0.2+0.02*sin(...) vector, computed in numpy so it is
 *     bit-identical to the reference's own vector computation
 *   - asp_white[n], turb_white[n]: the noise blocks themselves
 * This C core is therefore a PURE DETERMINISTIC FUNCTION of its inputs:
 * no RNG, no clock, no I/O, no global state.
 *
 * WHAT REMAINS INEXACT (honest list): libm exp/log/sin/pow here vs
 * numpy's vectorized transcendentals. Measured on the build hosts they
 * agree bitwise with libm; where they differ it is <=1 ulp, and the
 * ladder is passive (loss < 1) so ulp noise cannot grow. The parity
 * gate (validate/v_parity.py) reports the honest number.
 *
 * Float discipline: all internal math in double, exactly like the
 * reference; -ffp-contract=off REQUIRED (an FMA changes bits);
 * NO -ffast-math EVER. rint() is used where the reference uses Python
 * round() -- both are round-half-even under the default FP environment.
 *
 * Interface: mouth2_render_c() below. fastcore.py is the only caller.
 */

#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

/* indices into the packed constants vector `cst` (fastcore.py mirrors
 * these; every value is computed in Python with the reference's own
 * expressions so the doubles are bit-identical to what the reference
 * uses). */
enum {
    C_SR = 0,            /* fs, 48000.0                                   */
    C_JITTER,            /* GlottalSource.jitter                          */
    C_SHIMMER,           /* GlottalSource.shimmer                         */
    C_DRIFT_SIGMA,
    C_DRIFT_CLIP,
    C_DRIFT_POLE_HZ,
    C_VIB_SEMITONES,
    C_ASP_TILT_C,        /* exp(-2*pi*900/sr), the aspiration one-pole    */
    C_HF_A,              /* exp(-2*pi*HF_POLE_HZ/fs)                      */
    C_GLOTTAL_REFLECT,
    C_LIP_REFLECT,
    C_LOSS,              /* ROUND_TRIP_GAIN ** (1/(rt_per_sec*N))         */
    C_LOSS_N,            /* ROUND_TRIP_GAIN ** (1/(rt_per_sec*M))         */
    C_AREA_FLOOR,
    C_AREA_SEAL,
    C_VELUM_LEAK,
    C_BURST_GAIN,
    C_PRESSURE_RATE,
    C_BURST_DECAY,
    C_BURST_OPEN_REF,
    C_TURB_GAIN,
    C_TURB_C_LP,         /* exp(-2*pi*3000/fs)                            */
    C_TURB_C_HP,         /* exp(-2*pi*1000/fs)                            */
    C_DC_POLE,
    C_N_CONSTS
};

/* glottis.py _lf_params, verbatim algebra (PT Glottis.setupWaveform). */
typedef struct {
    double alpha, E0, epsilon, shift, Delta, Te, omega;
} LFParams;

static void lf_params(double tenseness, LFParams *p)
{
    double Rd = 3.0 * (1.0 - tenseness);
    if (Rd < 0.5) Rd = 0.5;
    if (Rd > 2.7) Rd = 2.7;
    {
        double Ra = -0.01 + 0.048 * Rd;
        double Rk = 0.224 + 0.118 * Rd;
        double Rg = (Rk / 4.0) * (0.5 + 1.2 * Rk)
                    / (0.11 * Rd - Ra * (0.5 + 1.2 * Rk));
        double Ta = Ra;
        double Tp = 1.0 / (2.0 * Rg);
        double Te = Tp + Tp * Rk;

        double epsilon = 1.0 / Ta;
        double shift = exp(-epsilon * (1.0 - Te));
        double Delta = 1.0 - shift;

        double rhs_integral = ((1.0 / epsilon) * (shift - 1.0)
                               + (1.0 - Te) * shift) / Delta;
        double total_lower = -(Te - Tp) / 2.0 + rhs_integral;
        double total_upper = -total_lower;

        double omega = M_PI / Tp;
        double s = sin(omega * Te);
        double y = -M_PI * s * total_upper / (Tp * 2.0);
        double z = log(y);
        double alpha = z / (Tp / 2.0 - Te);
        double E0 = -1.0 / (s * exp(alpha * Te));

        p->alpha = alpha; p->E0 = E0; p->epsilon = epsilon;
        p->shift = shift; p->Delta = Delta; p->Te = Te; p->omega = omega;
    }
}

static double clipd(double x, double lo, double hi)
{
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

/* The whole render: glottis (LF pulse train + aspiration) -> branched KL
 * ladder with seal/pressure/burst + turbulence -> DC blockers.
 * Outputs lip_out/nose_out at the internal rate (48 kHz); the caller
 * decimates and normalizes in numpy, identically for both backends.
 * Returns 0 on success, <0 on error. */
EXPORT int mouth2_render_c(
    int n, int n_blocks, int block_len, int N, int M, int jn, int i0c,
    const double *area_track,   /* n_blocks * N, row-major             */
    const double *velum_track,  /* n_blocks                            */
    const double *nasal_areas,  /* M (index 0 replaced per block)      */
    const double *log_f0,       /* n, GlottalSource.log_f0             */
    const double *ten_env,      /* n, GlottalSource.ten_env (clipped)  */
    const double *int_env,      /* n, GlottalSource.int_env (clipped)  */
    const double *flutter,      /* n, precomputed in numpy             */
    const double *jit_draws,    /* max_p per-period draws              */
    const double *shm_draws,
    const double *drf_draws,
    int max_p,
    double vib_rate, double vib_phase,
    const double *asp_white,    /* n */
    const double *turb_white,   /* n */
    const double *cst, int n_cst,
    double *lip_out, double *nose_out)  /* n each */
{
    if (n_cst != C_N_CONSTS) return -1;
    if (n <= 0 || N < 3 || M < 2 || jn < 1 || jn > N - 2) return -2;

    const double sr = cst[C_SR];
    const double jitter = cst[C_JITTER];
    const double shimmer = cst[C_SHIMMER];
    const double DRIFT_SIGMA = cst[C_DRIFT_SIGMA];
    const double DRIFT_CLIP = cst[C_DRIFT_CLIP];
    const double DRIFT_POLE_HZ = cst[C_DRIFT_POLE_HZ];
    const double VIB_ST = cst[C_VIB_SEMITONES];
    const double c_asp = cst[C_ASP_TILT_C];
    const double hf_a = cst[C_HF_A];
    const double hf_g = 1.0 - hf_a;
    const double GLOTTAL_REFLECT = cst[C_GLOTTAL_REFLECT];
    const double LIP_REFLECT = cst[C_LIP_REFLECT];
    const double loss = cst[C_LOSS];
    const double loss_n = cst[C_LOSS_N];
    const double AREA_FLOOR = cst[C_AREA_FLOOR];
    const double AREA_SEAL = cst[C_AREA_SEAL];
    const double VELUM_LEAK = cst[C_VELUM_LEAK];
    const double BURST_GAIN = cst[C_BURST_GAIN];
    const double PRESSURE_RATE = cst[C_PRESSURE_RATE];
    const double BURST_DECAY = cst[C_BURST_DECAY];
    const double BURST_OPEN_REF = cst[C_BURST_OPEN_REF];
    const double TURB_GAIN = cst[C_TURB_GAIN];
    const double c_lp = cst[C_TURB_C_LP];
    const double c_hp = cst[C_TURB_C_HP];
    const double DC_POLE = cst[C_DC_POLE];

    /* work arrays */
    double *voiced = (double *)calloc((size_t)n, sizeof(double));
    double *aspir = (double *)calloc((size_t)n, sizeof(double));
    double *nmod = (double *)calloc((size_t)n, sizeof(double));
    double *turb = (double *)malloc((size_t)n * sizeof(double));
    double *scratch = (double *)malloc(
        (size_t)(6 * N + 4 * M + 8) * sizeof(double));
    if (!voiced || !aspir || !nmod || !turb || !scratch) {
        free(voiced); free(aspir); free(nmod); free(turb); free(scratch);
        return -3;
    }

    /* ================= glottis.py GlottalSource.render ================= */
    {
        int i = 0, pc = 0;
        double drift_state = 0.0;
        while (i < n) {
            double t0 = (double)i / sr;
            double f0_base = exp(log_f0[i]);
            double ten = ten_env[i];
            double g_jit, g_shm, g_drf;
            double period_guess, a_d, drift_fac, vib_fac, f0;
            int n_p, n_use, k;
            LFParams P;
            double amp;

            if (pc >= max_p) {                 /* out of pre-drawn noise */
                free(voiced); free(aspir); free(nmod); free(turb);
                free(scratch);
                return -4;
            }
            /* per-period draws -- ONE from each stream, reference order */
            g_jit = jit_draws[pc];
            g_shm = shm_draws[pc];
            g_drf = drf_draws[pc];
            pc++;

            period_guess = 1.0 / fmax(f0_base, 1.0);
            a_d = exp(-2.0 * M_PI * DRIFT_POLE_HZ * period_guess);
            drift_state = a_d * drift_state
                          + sqrt(fmax(0.0, 1.0 - a_d * a_d)) * g_drf;
            drift_fac = clipd(1.0 + DRIFT_SIGMA * drift_state,
                              1.0 - DRIFT_CLIP, 1.0 + DRIFT_CLIP);
            vib_fac = pow(2.0, (VIB_ST / 12.0)
                          * sin(2.0 * M_PI * vib_rate * t0 + vib_phase));
            f0 = f0_base * drift_fac * vib_fac * (1.0 + jitter * g_jit);
            n_p = (int)rint(sr / fmax(f0, 1.0));   /* round-half-even */
            if (n_p < 4) n_p = 4;
            n_use = (n_p < n - i) ? n_p : (n - i);

            lf_params(ten, &P);
            amp = (1.0 + shimmer * g_shm) * pow(ten, 0.25);
            for (k = 0; k < n_use; k++) {
                double t = (double)k / (double)n_p;
                double w;
                if (t > P.Te)
                    w = (-exp(-P.epsilon * (t - P.Te)) + P.shift) / P.Delta;
                else
                    w = P.E0 * exp(P.alpha * t) * sin(P.omega * t);
                voiced[i + k] = amp * w;
                {   /* PT getNoiseModulator */
                    double s = sin(2.0 * M_PI * t);
                    double v_cyc = 0.1 + 0.2 * fmax(0.0, s);
                    double ten_int = ten_env[i + k] * int_env[i + k];
                    nmod[i + k] = ten_int * v_cyc + (1.0 - ten_int) * 0.3;
                }
            }
            i += n_p;
        }
        /* voiced *= int_env */
        for (i = 0; i < n; i++)
            voiced[i] *= int_env[i];
        /* aspiration: one-pole tilt then PT scaling * flutter */
        {
            double acc = 0.0, g = 1.0 - c_asp;
            int t;
            for (t = 0; t < n; t++) {
                acc = g * asp_white[t] + c_asp * acc;
                /* (((int_env*(1-sqrt(ten)))*nmod)*flutter)*tilted */
                aspir[t] = ((int_env[t] * (1.0 - sqrt(ten_env[t])))
                            * nmod[t] * flutter[t]) * acc;
            }
        }
    }

    /* turbulence bandpass: LP then subtract-lower (tract_core.py) */
    {
        double acc = 0.0, g = 1.0 - c_lp;
        int t;
        for (t = 0; t < n; t++) {
            acc = g * turb_white[t] + c_lp * acc;
            turb[t] = acc;                       /* low */
        }
        acc = 0.0; g = 1.0 - c_hp;
        for (t = 0; t < n; t++) {
            double low = turb[t];
            acc = g * low + c_hp * acc;
            turb[t] = low - acc;                 /* low - LP(low) */
        }
    }

    /* ==================== tract_core.py render ==================== */
    {
        double *R = scratch;                 /* N   */
        double *L = R + N;                   /* N   */
        double *jR = L + N;                  /* N   */
        double *jL = jR + N;                 /* N+1 */
        double *r_prev = jL + N + 1;         /* N-1 */
        double *r_new = r_prev + N;          /* N-1 (padded) */
        double *nR = r_new + N;              /* M   */
        double *nL = nR + M;                 /* M   */
        double *nr_prev = nL + M;            /* M-1 */
        double *nr_new = nr_prev + M;        /* M-1 (padded) */
        double a[64], na[64], njR[64], njL[65];
        double j3_prev[3], j3_new[3];
        double lp_lip = 0.0, lp_nose = 0.0, lp_glot = 0.0;
        double pressure = 0.0;
        int bursting = 0, seal_cons = -1, sealed_prev;
        int b, j;

        if (N > 63 || M > 63) {
            free(voiced); free(aspir); free(nmod); free(turb); free(scratch);
            return -5;
        }
        memset(scratch, 0,
               (size_t)(6 * N + 4 * M + 8) * sizeof(double));

        /* first-block coefficients (reference: before the loop) */
        for (j = 0; j < N; j++)
            a[j] = fmax(area_track[j], AREA_FLOOR);
        for (j = 0; j < N - 1; j++)
            r_prev[j] = (a[j] - a[j + 1]) / (a[j] + a[j + 1]);
        {   /* _junction3(a0, jn, velum_track[0]) */
            double A_L = fmax(a[jn], AREA_FLOOR);
            double A_R = fmax(a[(jn + 1 < N - 1) ? jn + 1 : N - 1],
                              AREA_FLOOR);
            double A_N = fmax(velum_track[0], 0.0);
            double s = A_L + A_R + A_N;
            j3_prev[0] = (2.0 * A_L - s) / s;
            j3_prev[1] = (2.0 * A_R - s) / s;
            j3_prev[2] = (2.0 * A_N - s) / s;
        }
        for (j = 0; j < M; j++)
            na[j] = fmax(nasal_areas[j], AREA_FLOOR);
        na[0] = fmax(fmax(velum_track[0], AREA_FLOOR), AREA_FLOOR);
        for (j = 0; j < M - 1; j++)
            nr_prev[j] = (na[j] - na[j + 1]) / (na[j] + na[j + 1]);
        {
            double amin = a[0];
            for (j = 1; j < N; j++)
                if (a[j] < amin) amin = a[j];
            sealed_prev = (amin < AREA_SEAL);
        }

        for (b = 0; b < n_blocks; b++) {
            int i0 = b * block_len;
            int i1 = (n < i0 + block_len) ? n : (i0 + block_len);
            int nb, k, cons, inj, binj, sealed, velum_open;
            double vel, cons_area, d_pt, thin, openn, turb_amp, g_open;

            if (i0 >= n) break;
            for (j = 0; j < N; j++)
                a[j] = fmax(area_track[(size_t)b * N + j], AREA_FLOOR);
            for (j = 0; j < N - 1; j++)
                r_new[j] = (a[j] - a[j + 1]) / (a[j] + a[j + 1]);
            vel = velum_track[b];
            {   /* _junction3(a, jn, vel) */
                double A_L = fmax(a[jn], AREA_FLOOR);
                double A_R = fmax(a[(jn + 1 < N - 1) ? jn + 1 : N - 1],
                                  AREA_FLOOR);
                double A_N = fmax(vel, 0.0);
                double s = A_L + A_R + A_N;
                j3_new[0] = (2.0 * A_L - s) / s;
                j3_new[1] = (2.0 * A_R - s) / s;
                j3_new[2] = (2.0 * A_N - s) / s;
            }
            for (j = 0; j < M; j++)
                na[j] = fmax(nasal_areas[j], AREA_FLOOR);
            na[0] = fmax(fmax(vel, AREA_FLOOR), AREA_FLOOR);
            for (j = 0; j < M - 1; j++)
                nr_new[j] = (na[j] - na[j + 1]) / (na[j] + na[j + 1]);

            /* constriction search: band [i0c, N), first-minimum argmin */
            cons = i0c;
            for (j = i0c + 1; j < N; j++)
                if (a[j] < a[cons]) cons = j;
            cons_area = a[cons];
            d_pt = sqrt(fmax(cons_area, 0.0));
            thin = clipd(8.0 * (0.7 - d_pt), 0.0, 1.0);
            openn = clipd(30.0 * (d_pt - 0.3), 0.0, 1.0);
            turb_amp = TURB_GAIN * thin * openn;
            inj = (cons + 1 < N - 2) ? cons + 1 : N - 2;

            sealed = (cons_area < AREA_SEAL);
            velum_open = (vel > VELUM_LEAK);
            if (sealed) {
                seal_cons = cons;
                bursting = 0;
            }
            if (sealed_prev && !sealed && pressure > 1e-4)
                bursting = 1;
            sealed_prev = sealed;
            if (seal_cons >= 0)
                g_open = fmin(a[seal_cons] / BURST_OPEN_REF, 1.0);
            else
                g_open = 1.0;
            binj = (seal_cons >= 0) ? seal_cons : cons;
            if (binj > N - 2) binj = N - 2;

            nb = i1 - i0;
            for (k = 0; k < nb; k++) {
                int t = i0 + k;
                double lm = ((double)k + 1.0) / (double)nb;
                double rL3 = j3_prev[0] * (1.0 - lm) + j3_new[0] * lm;
                double rR3 = j3_prev[1] * (1.0 - lm) + j3_new[1] * lm;
                double rN3 = j3_prev[2] * (1.0 - lm) + j3_new[2] * lm;
                double src, jR0, jLN, nose_in0, njR0, njLM;

                /* injections into the OLD state (PT order) */
                if (turb_amp > 0.0) {
                    double tn = turb_amp * turb[t] * nmod[t];
                    R[inj] += 0.5 * tn;
                    L[inj] += 0.5 * tn;
                }
                if (bursting) {
                    double bamp = BURST_GAIN * pressure * g_open;
                    R[binj] += 0.5 * bamp;
                    L[binj] += 0.5 * bamp;
                    pressure *= 1.0 - g_open * (1.0 - BURST_DECAY);
                    if (pressure <= 1e-4) {
                        pressure = 0.0;
                        bursting = 0;
                    }
                }

                src = voiced[t] + aspir[t];
                if (sealed && !velum_open) {
                    double p2 = pressure + PRESSURE_RATE * fabs(src);
                    pressure = fmin(p2, 1.0);
                }

                /* glottal + lip ends, HF one-pole inside the reflection */
                lp_glot = hf_g * (GLOTTAL_REFLECT * L[0]) + hf_a * lp_glot;
                jR0 = lp_glot + src;
                lp_lip = hf_g * (LIP_REFLECT * R[N - 1]) + hf_a * lp_lip;
                jLN = lp_lip;

                /* interior junction pass, from OLD R, L */
                jR[0] = jR0;
                jL[N] = jLN;
                for (j = 1; j < N; j++) {
                    double r = r_prev[j - 1] * (1.0 - lm)
                               + r_new[j - 1] * lm;
                    double w = r * (R[j - 1] + L[j]);
                    jR[j] = R[j - 1] - w;
                    jL[j] = L[j] + w;
                }

                /* 3-way velum junction overwrites index jn (PT verbatim) */
                nose_in0 = nL[0];
                jL[jn] = rL3 * R[jn - 1]
                         + (1.0 + rL3) * (nose_in0 + L[jn]);
                jR[jn] = rR3 * L[jn]
                         + (1.0 + rR3) * (R[jn - 1] + nose_in0);
                njR0 = rN3 * nose_in0
                       + (1.0 + rN3) * (L[jn] + R[jn - 1]);

                for (j = 0; j < N; j++) {
                    R[j] = jR[j] * loss;
                    L[j] = jL[j + 1] * loss;
                }
                lip_out[t] = R[N - 1];

                /* nasal branch */
                lp_nose = hf_g * (LIP_REFLECT * nR[M - 1]) + hf_a * lp_nose;
                njLM = lp_nose;
                njR[0] = njR0;
                njL[M] = njLM;
                for (j = 1; j < M; j++) {
                    double nrj = nr_prev[j - 1] * (1.0 - lm)
                                 + nr_new[j - 1] * lm;
                    double wn = nrj * (nR[j - 1] + nL[j]);
                    njR[j] = nR[j - 1] - wn;
                    njL[j] = nL[j] + wn;
                }
                for (j = 0; j < M; j++) {
                    nR[j] = njR[j] * loss_n;
                    nL[j] = njL[j + 1] * loss_n;
                }
                nose_out[t] = nR[M - 1];
            }

            memcpy(r_prev, r_new, (size_t)(N - 1) * sizeof(double));
            j3_prev[0] = j3_new[0];
            j3_prev[1] = j3_new[1];
            j3_prev[2] = j3_new[2];
            memcpy(nr_prev, nr_new, (size_t)(M - 1) * sizeof(double));
        }

        /* DC blockers, one per output (tract_core._dcblock) */
        {
            double x1 = 0.0, y1 = 0.0;
            int t;
            for (t = 0; t < n; t++) {
                y1 = lip_out[t] - x1 + DC_POLE * y1;
                x1 = lip_out[t];
                lip_out[t] = y1;
            }
            x1 = 0.0; y1 = 0.0;
            for (t = 0; t < n; t++) {
                y1 = nose_out[t] - x1 + DC_POLE * y1;
                x1 = nose_out[t];
                nose_out[t] = y1;
            }
        }
    }

    free(voiced); free(aspir); free(nmod); free(turb); free(scratch);
    return 0;
}

/* build-stamp so fastcore can verify it loaded the right ABI */
EXPORT int mouth2_abi_version(void) { return 2; }
