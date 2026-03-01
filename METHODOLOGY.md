# Training Metrics Methodology

This document describes the sporting and physiological methodology used by the training engine. Every metric is computed from first principles using published formulae; no vendor black-box scores are used. The intent is that someone familiar with exercise science can read this document, verify the formulae against the source papers, and assess the outputs with confidence.

---

## 1. Training load: Banister HRr TRIMP

### What it measures

Training Impulse (TRIMP) quantifies the physiological stress of a single training session. It accounts for both the duration of exercise and the intensity relative to the individual's heart rate reserve (HRr).

### Formula

For each consecutive pair of HR measurements in a session:

```
TRIMP_contribution = Δt_min × HRr × A × exp(B × HRr)
```

where:

| Symbol | Definition |
|---|---|
| `Δt_min` | Elapsed time between consecutive HR samples, in minutes |
| `HRr` | Heart rate reserve fraction (see below) |
| `A`, `B` | Sex-specific empirical coefficients (male: 0.64, 1.92; female: 0.86, 1.67) |

**Heart rate reserve fraction:**

```
HRr = (HR_instant - HR_rest) / (HR_max - HR_rest)
```

`HRr` is clamped to [0, 1]. A value of 0 means working at resting heart rate; 1.0 means working at maximum.

**Session TRIMP total:**

```
TRIMP_total = Σ (Δt_min × HRr × A × exp(B × HRr))
```

### Physiological rationale

The exponential factor `A × exp(B × HRr)` reflects the non-linear relationship between exercise intensity and blood lactate accumulation. At low intensities lactate is cleared as fast as it is produced; at high intensities it accumulates rapidly. The exponential term gives disproportionately higher weight to high-intensity work, which is consistent with the physiological cost of lactate accumulation and clearance.

### Implementation note

This engine uses the **male** coefficients (A = 0.64, B = 1.92). Female coefficients (A = 0.86, B = 1.67) exist in the code as a comment. If physiology changes to warrant switching, the constants `TRIMP_A` and `TRIMP_B` in `scripts/garmin/ingest_fit.py` should be updated and a full rebuild run.

### Primary reference

Banister EW (1991). *Modeling elite athletic performance.* In: MacDougall JD, Wenger HA, Green HJ (eds). *Physiological Testing of the High-Performance Athlete*, 2nd ed. Human Kinetics, pp. 403–424.

See also: Morton RH, Fitz-Clarke JR, Banister EW (1990). *Modeling human performance in running.* J Appl Physiol 69(3):1171–1177.

---

## 2. Heart rate zones

### Definition

Five zones are defined as fractions of the **Lactate Threshold Heart Rate** (LTHR). Zones are stored as lower/upper bounds and are time-aware: the engine looks up the zone definitions in effect on the date of each activity.

### Default zone boundaries

| Zone | Lower (× LTHR) | Upper (× LTHR) | Character |
|---|---|---|---|
| Z1 | 0.67 | 0.84 | Recovery / easy aerobic |
| Z2 | 0.84 | 0.91 | Aerobic base |
| Z3 | 0.91 | 0.98 | Tempo |
| Z4 | 0.98 | 1.02 | Threshold |
| Z5 | 1.02 | 1.10 | VO₂max / anaerobic |

Zones are contiguous with no gaps: the upper bound of each zone equals the lower bound of the next.

### Why LTHR-relative?

LTHR (the heart rate at or near the lactate threshold, often approximated by a 30-minute maximal effort) is a stable, field-testable physiological anchor. Expressing zones as fractions of LTHR means the zone structure scales with the individual and remains valid after fitness changes that shift LTHR, without needing to manually re-enter absolute BPM boundaries for every zone.

### Time-aware physiology

LTHR, HRmax, and HRrest are stored with an `effective_from_date`. When computing TRIMP or zone seconds for an activity, the engine uses the most recent values with an effective date on or before the activity date. This preserves historical accuracy: if LTHR changes after a test, older activities are not retroactively re-scored.

### Reference

Friel J (2009). *The Triathlete's Training Bible*, 3rd ed. VeloPress. (Zone structure and LTHR-relative approach.)

---

## 3. Fitness-Fatigue model (ATL / CTL)

### Background

The Fitness-Fatigue (or "Banister") model represents the body's response to training as the balance of two opposing adaptations: fitness (a positive, slow-building effect) and fatigue (a negative, fast-building effect). The net performance potential at any moment is modelled as the difference between the two.

### Exponentially weighted moving averages

Both fitness and fatigue are estimated as exponentially weighted moving averages (EWMA) of daily training load:

```
new_EWMA = prev_EWMA + α × (load_today - prev_EWMA)
```

| Variable | Time constant | α = 2 / (n + 1) | Interpretation |
|---|---|---|---|
| **CTL** (Chronic Training Load) | 42 days | ≈ 0.0465 | Fitness proxy: slow to build, slow to decay |
| **ATL** (Acute Training Load) | 7 days | 0.25 | Fatigue proxy: fast to build, fast to clear |

Both are initialized at 0 at the start of the dataset. The model requires approximately one time-constant of data to converge: CTL values in the first ~42 days of the record should be interpreted with caution.

### Load input

The load fed into the model is `load_points`, which is currently defined as `TRIMP_total` (one row per calendar day, summing all activities on that day). Rest days contribute 0.

### Time constants

The 7-day and 42-day time constants are the conventional parameterisation for endurance sports, as popularised by Coggan and Allen. They represent a practical balance between responsiveness (short window for ATL) and stability (long window for CTL). The underlying model does not prescribe specific time constants; they are adjustable parameters.

### Primary reference

Banister EW, Calvert TW, Savage MV, Bach TM (1975). *A systems model of training for athletic performance.* Aust J Sports Med 7:57–61.

See also: Busso T (2003). *Variable dose-response relationship between exercise training and performance.* Med Sci Sports Exerc 35(7):1188–1195.

---

## 4. Form (Training Stress Balance)

### Formula

```
Form = CTL - ATL
```

### Interpretation

| Form | Meaning |
|---|---|
| Strongly positive (> +15) | Very fresh; possibly detrained if sustained |
| Moderately positive (+5 to +15) | Peak / race-ready state |
| Near zero (−5 to +5) | Maintenance; neutral fatigue |
| Negative (−5 to −30) | Productive training block; some fatigue present |
| Deeply negative (< −30) | High fatigue; risk of overreaching |

Form is the primary taper and readiness indicator. A structured training plan typically involves a period of negative form (high training load) followed by a taper that allows form to rise before a target event.

---

## 5. AC ratio (ATL / CTL)

### Formula

```
AC_ratio = ATL / CTL   (undefined when CTL = 0)
```

### Interpretation

The AC ratio expresses acute load relative to chronic load — i.e., how much recent training compares to the established baseline.

| AC ratio | Interpretation |
|---|---|
| < 0.8 | Undertraining or significant taper |
| 0.8 – 1.3 | Optimal progressive training zone |
| > 1.3 | Acute spike; elevated injury risk |

### Reference

Gabbett TJ (2016). *The training-injury prevention paradox: should athletes be training smarter and harder?* Br J Sports Med 50(5):273–280.

---

## 6. Ramp rate

### Formula

```
Ramp_rate = CTL_today - CTL_7_days_ago
```

### Interpretation

Ramp rate measures how quickly fitness (CTL) is increasing over a rolling 7-day window. Rapid increases in training load are a known injury risk factor independent of absolute load.

Commonly cited safe ramp rates for runners are in the region of 5–10% of CTL per week, or roughly 3–8 TRIMP-equivalent points per week depending on the athlete's absolute training load. Values above this threshold warrant monitoring.

Ramp rate is undefined (`NULL`) for the first 7 days of the record.

### Reference

Gabbett TJ (2016). *The training-injury prevention paradox: should athletes be training smarter and harder?* Br J Sports Med 50(5):273–280.

---

## 7. Foster monotony and strain

### Background

Carl Foster's session-RPE model uses simple arithmetic on daily training loads to detect patterns associated with overreaching and illness. This engine applies the same formulae using TRIMP-based load in place of session RPE × duration.

### Formulae

All calculations use a rolling 7-day window of daily loads.

**Monotony** — how uniform training is day-to-day:

```
Monotony = mean(7-day loads) / population_stdev(7-day loads)
```

Monotony is undefined (`NULL`) when all loads are identical (stdev = 0) or when fewer than 2 data points are available.

**Strain** — total weekly stress weighted by its uniformity:

```
Strain = sum(7-day loads) × Monotony
```

### Interpretation

| Monotony | Interpretation |
|---|---|
| < 1.5 | Good variation; adequate recovery stimulus |
| 1.5 – 2.0 | Borderline; consider adding variation |
| > 2.0 | Insufficient variation; elevated overtraining risk |

High monotony alone is not harmful — but high monotony combined with high strain (large weekly load × low variation) is the pattern Foster associates with illness and performance decline.

### Reference

Foster C, Florhaug JA, Franklin J, et al. (2001). *A new approach to monitoring exercise training.* J Strength Cond Res 15(1):109–115.

---

## 8. Limitations and assumptions

The following design choices should be understood before drawing strong conclusions from the dashboard:

| Assumption | Effect |
|---|---|
| **Male TRIMP coefficients** | TRIMP values will be slightly underestimated relative to female physiology. The exponential shape is correct but the scaling differs. |
| **HR-only load model** | Activities without heart rate data (e.g. gym sessions, swims without HR strap) produce no TRIMP and contribute zero to ATL/CTL. |
| **Single load currency** | `load_points = TRIMP_total`. All sports are treated identically. A 60-minute easy run and a 60-minute swim at the same HRr produce the same load, regardless of modality-specific differences in systemic stress. |
| **Cold-start initialization** | ATL and CTL both start at 0. Early values (first ~42 days for CTL, first ~7 days for ATL) will be underestimates until the EWMA converges. |
| **Fixed EWMA time constants** | The 7-day and 42-day windows are conventional, not individually calibrated. Actual fatigue clearance and fitness accumulation rates vary by athlete, age, and training history. |
| **LTHR as zone anchor** | Zones are expressed relative to LTHR, which is itself estimated (either from a test or from Garmin's estimate). Errors in LTHR shift all zone boundaries proportionally. |
