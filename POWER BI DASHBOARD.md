# Power BI Dashboard — Build Reference

Personal coaching dashboard for ultra-marathon training. Data source: `db/training.db` via ODBC DSN `Training DB`. Canvas: 1280×720px (16:9 landscape).

Theme file: `ultra-training-dark.json`

---

## Build Progress

| #   | Page                         | Status                    |
| --- | ---------------------------- | ------------------------- |
| —   | Theme                        | ✅ Done                    |
| 1   | Status Today                 | ✅ Done                    |
| 2   | Performance Management (PMC) | ✅ Done                    |
| 3   | Weekly Load                  | ✅ Done                    |
| 4   | Zone Analysis                | 🔲 Pending                |
| 5   | Activity Log                 | 🔲 Pending                |
| 6   | Physiology                   | 🔲 Pending (low priority) |

---

## Theme

File: `ultra-training-dark.json` — import via View → Themes → Browse for themes.

### Palette

| Role                    | Hex       |
| ----------------------- | --------- |
| Page background         | `#0D1117` |
| Card / panel background | `#161B22` |
| Card border (subtle)    | `#30363D` |
| Primary text            | `#E6EDF3` |
| Secondary text / labels | `#8B949E` |

### Accent colours

| Role                                | Hex       |
| ----------------------------------- | --------- |
| CTL / Fitness / primary             | `#58A6FF` |
| Positive / good / aerobic (Z2)      | `#3FB950` |
| Warning / amber (Z3)                | `#D29922` |
| Danger / overreached (Z5)           | `#F85149` |
| ATL / Fatigue / high load (Z4)      | `#F0883E` |
| Fresh / neutral / undertrained (Z1) | `#79C0FF` |

### HR Zone colours

| Zone | Name         | Hex       |
| ---- | ------------ | --------- |
| Z1   | Recovery     | `#4A9EFF` |
| Z2   | Aerobic base | `#3FB950` |
| Z3   | Tempo        | `#D29922` |
| Z4   | Threshold    | `#F0883E` |
| Z5   | VO2max / max | `#F85149` |

### Form status bands (CTL − ATL)

| Form       | State         | Colour    |
| ---------- | ------------- | --------- |
| < −30      | Very Fatigued | `#F85149` |
| −30 to −10 | Building      | `#F0883E` |
| −10 to +5  | Optimal       | `#3FB950` |
| > +5       | Fresh         | `#79C0FF` |

### AC Ratio bands (ultra-runner calibrated)

| AC Ratio  | State               | Colour    |
| --------- | ------------------- | --------- |
| < 0.8     | Detrained           | `#79C0FF` |
| 0.8 – 1.5 | Building well       | `#3FB950` |
| 1.5 – 2.2 | High load — monitor | `#D29922` |
| > 2.2     | Very high — risk    | `#F85149` |

*Note: standard Gabbett (2016) threshold of 1.3 is not meaningful for ultra-marathon training. These ranges are calibrated to this athlete's data.*

### Ramp Rate bands (CTL change over 7 days)

| \|ramp rate\| | State              | Colour    |
| ------------- | ------------------ | --------- |
| ≤ 8           | Safe               | `#3FB950` |
| 8 – 15        | Elevated — monitor | `#D29922` |
| > 15          | High risk          | `#F85149` |

---

## DAX Measures

### Table: `daily_metrics`

```dax
_m: Today CTL =
VAR _maxDate = MAXX(ALL(daily_metrics), daily_metrics[date])
RETURN CALCULATE(MAX(daily_metrics[ctl]), daily_metrics[date] = _maxDate)
```

```dax
_m: Today ATL =
VAR _maxDate = MAXX(ALL(daily_metrics), daily_metrics[date])
RETURN CALCULATE(MAX(daily_metrics[atl]), daily_metrics[date] = _maxDate)
```

```dax
_m: Today Form =
VAR _maxDate = MAXX(ALL(daily_metrics), daily_metrics[date])
RETURN CALCULATE(MAX(daily_metrics[form]), daily_metrics[date] = _maxDate)
```

```dax
_m: Today AC Ratio =
VAR _maxDate = MAXX(ALL(daily_metrics), daily_metrics[date])
RETURN CALCULATE(MAX(daily_metrics[ac_ratio]), daily_metrics[date] = _maxDate)
```

```dax
_m: Today Ramp Rate =
VAR _maxDate = MAXX(ALL(daily_metrics), daily_metrics[date])
RETURN CALCULATE(MAX(daily_metrics[ramp_rate]), daily_metrics[date] = _maxDate)
```

```dax
_m: Today Monotony =
VAR _maxDate = MAXX(ALL(daily_metrics), daily_metrics[date])
RETURN CALCULATE(MAX(daily_metrics[monotony]), daily_metrics[date] = _maxDate)
```

```dax
_m: Today Strain =
VAR _maxDate = MAXX(ALL(daily_metrics), daily_metrics[date])
RETURN CALCULATE(MAX(daily_metrics[strain]), daily_metrics[date] = _maxDate)
```

```dax
_m: Today Date = FORMAT(TODAY(), "DDD DD MMM YYYY", "en-GB")
```

```dax
_m: Form Status Label =
VAR _form = [_m: Today Form]
RETURN
SWITCH(
    TRUE(),
    _form < -30, "Very Fatigued",
    _form < -10, "Building",
    _form <= 5,  "Optimal",
    "Fresh"
)
```

```dax
_m: Form Colour =
VAR _form = [_m: Today Form]
RETURN
SWITCH(
    TRUE(),
    _form < -30, "#F85149",
    _form < -10, "#F0883E",
    _form <= 5,  "#3FB950",
    "#79C0FF"
)
```

```dax
_m: AC Ratio Colour =
VAR _r = [_m: Today AC Ratio]
RETURN
IF(_r < 0.8,  "#79C0FF",
IF(_r <= 1.5, "#3FB950",
IF(_r <= 2.2, "#D29922",
              "#F85149")))
```

```dax
_m: Ramp Rate Colour =
VAR _r = [_m: Today Ramp Rate]
RETURN
IF(ABS(_r) <= 8,  "#3FB950",
IF(ABS(_r) <= 15, "#D29922",
                  "#F85149"))
```

```dax
_m: Monotony Colour =
VAR _m = [_m: Today Monotony]
RETURN
IF(_m <= 1.5, "#3FB950",
IF(_m <= 2.0, "#D29922",
              "#F85149"))
```

```dax
_m: WTD Load =
VAR _weekStart = TODAY() - WEEKDAY(TODAY(), 2) + 1
RETURN
CALCULATE(
    SUM(daily_metrics[load_points]),
    FILTER(
        ALL(daily_metrics),
        daily_metrics[date] >= _weekStart
            && daily_metrics[date] <= TODAY()
    )
)
```

```dax
_m: Last Week Load =
VAR _weekStart = TODAY() - WEEKDAY(TODAY(), 2) + 1
VAR _lwStart   = _weekStart - 7
VAR _lwEnd     = _weekStart - 1
RETURN
CALCULATE(
    SUM(daily_metrics[load_points]),
    FILTER(
        ALL(daily_metrics),
        daily_metrics[date] >= _lwStart
            && daily_metrics[date] <= _lwEnd
    )
)
```

```dax
_m: Form Bar =
VAR _f = SUM(daily_metrics[form])
RETURN _f
```

```dax
_m: Form Bar Colour =
VAR _f = SUM(daily_metrics[form])
RETURN
SWITCH(
    TRUE(),
    _f < -30, "#F85149",
    _f < -10, "#F0883E",
    _f <= 5,  "#3FB950",
    "#79C0FF"
)
```

### Table: `activity_metrics`

```dax
_m: Load 4W Current =
VAR _start = TODAY() - 28
RETURN
CALCULATE(
    SUM(activity_metrics[load_points]),
    FILTER(ALL(activities), activities[Date] >= _start && activities[Date] <= TODAY())
)
```

```dax
_m: Load 4W Previous =
VAR _start = TODAY() - 56
VAR _end   = TODAY() - 29
RETURN
CALCULATE(
    SUM(activity_metrics[load_points]),
    FILTER(ALL(activities), activities[Date] >= _start && activities[Date] <= _end)
)
```

```dax
_m: Load 4W Change % =
DIVIDE(
    [_m: Load 4W Current] - [_m: Load 4W Previous],
    [_m: Load 4W Previous]
)
```

```dax
_m: Avg Weekly Load (16W) =
VAR _start     = TODAY() - 112
VAR _totalLoad = CALCULATE(
    SUM(activity_metrics[load_points]),
    FILTER(ALL(activities), activities[Date] >= _start && activities[Date] <= TODAY())
)
RETURN DIVIDE(_totalLoad, 16)
```

```dax
_m: Week Total Load =
CALCULATE(
    SUM(activity_metrics[load_points]),
    ALL(activities[sport])
)
```

### Table: `activities`

```dax
_m: Days Since Last Activity =
INT(TODAY() - MAXX(ALL(activities), activities[Date]))
```

```dax
_m: Weekly Hours =
DIVIDE(SUM(activities[duration_s]), 3600)
```

### Calculated columns

**Table: `activities`**

```dax
_c: Duration HH:MM =
VAR _h   = INT(activities[duration_s] / 3600)
VAR _m   = INT(MOD(activities[duration_s], 3600) / 60)
RETURN FORMAT(_h, "0") & ":" & FORMAT(_m, "00")
```

```dax
_c: Distance km =
IF(
    activities[distance_m] = 0,
    BLANK(),
    ROUND(activities[distance_m] / 1000, 2)
)
```

**Table: `Dates`**

```dax
_c: In 16W Window = Dates[Date] >= TODAY() - 112
```

```dax
-- Full Dates table definition (replace the calculated table):
Dates =
VAR minDate = MINX(
    ALL(activities),
    DATE(YEAR(activities[start_time_utc]),MONTH(activities[start_time_utc]),DAY(activities[start_time_utc]))
)
VAR maxDate = TODAY()
RETURN
ADDCOLUMNS(
    CALENDAR(minDate,maxDate),
    "Year",YEAR([Date]),
    "Month Number",MONTH([Date]),
    "Month",FORMAT([Date],"MMMM","en-GB"),
    "Year-Month",FORMAT([Date],"YYYY-MM"),
    "Week Number",WEEKNUM([Date]),
    "Day",DAY([Date]),
    "End of Week",[Date] + (7 - WEEKDAY([Date], 2))
)
```

---

## Pages

### Page 1 — Status Today ✅

Daily 60-second coach check-in.

| Visual              | x    | y   | w   | h   | Notes                                                        |
| ------------------- | ---- | --- | --- | --- | ------------------------------------------------------------ |
| Title textbox       | 16   | 16  | 900 | 40  | "Status — Today", 18px bold                                  |
| Date card           | 1064 | 16  | 200 | 40  | `_m: Today Date`, 13px muted                                 |
| Form Status card    | 16   | 64  | 800 | 220 | `_m: Form Status Label`, bg conditional on `_m: Form Colour` |
| AC Ratio gauge      | 824  | 64  | 440 | 220 | Min=0, Max=3.0, no target line                               |
| CTL card            | 16   | 292 | 306 | 130 | `_m: Today CTL`, callout `#58A6FF`                           |
| ATL card            | 330  | 292 | 306 | 130 | `_m: Today ATL`, callout `#F0883E`                           |
| Form card           | 644  | 292 | 306 | 130 | `_m: Today Form`, callout conditional                        |
| Ramp Rate card      | 958  | 292 | 306 | 130 | `_m: Today Ramp Rate`, callout conditional                   |
| Last 7 Days bars    | 16   | 430 | 764 | 274 | Column chart, visual filter: last 7 days                     |
| WTD Load card       | 788  | 430 | 232 | 130 | `_m: WTD Load`                                               |
| Last Week card      | 1028 | 430 | 236 | 130 | `_m: Last Week Load`                                         |
| Last Activity table | 788  | 568 | 476 | 136 | Top N=1 filter, no headers                                   |

---

### Page 2 — Performance Management (PMC) ✅

Long-term training load trends.

| Visual            | x    | y   | w    | h   | Notes                                    |
| ----------------- | ---- | --- | ---- | --- | ---------------------------------------- |
| Title textbox     | 16   | 16  | 800  | 36  | "Performance Management", 18px bold      |
| PMC combo chart   | 16   | 60  | 1248 | 440 | See series table below                   |
| Date range slicer | 16   | 508 | 1248 | 44  | Between style, Dates[Date]               |
| Ramp rate chart   | 16   | 560 | 800  | 144 | ±8 green, ±15 amber constant lines       |
| Monotony card     | 824  | 560 | 200  | 144 | `_m: Today Monotony`, conditional colour |
| Strain card       | 1032 | 560 | 232  | 144 | `_m: Today Strain`, muted grey           |

**PMC series:**

| Series          | Field                            | Type   | Axis      | Colour                              |
| --------------- | -------------------------------- | ------ | --------- | ----------------------------------- |
| CTL             | `daily_metrics[ctl]`             | Line   | Primary   | `#58A6FF` 3px                       |
| ATL             | `daily_metrics[atl]`             | Line   | Primary   | `#F0883E` 2px                       |
| CTL Season Best | `daily_metrics[ctl_season_best]` | Line   | Primary   | `#8B949E` 1px dotted                |
| Form            | `_m: Form Bar`                   | Column | Secondary | Conditional → `_m: Form Bar Colour` |

Secondary axis: min −60, max +40. Constant line at Form=0 (dashed, `#8B949E`).

---

### Page 3 — Weekly Load ✅

Rolling load patterns by week and sport. 16-week rolling window.

| Visual                | x   | y   | w    | h   | Notes                                      |
| --------------------- | --- | --- | ---- | --- | ------------------------------------------ |
| Title textbox         | 16  | 16  | 800  | 36  | "Weekly Load", 18px bold                   |
| Weekly combo chart    | 16  | 60  | 1248 | 350 | Stacked columns by sport + hours line      |
| 4W Current Load card  | 16  | 418 | 302  | 130 | `_m: Load 4W Current`, Theme color 7       |
| 4W Previous Load card | 326 | 418 | 302  | 130 | `_m: Load 4W Previous`, Theme color 8      |
| 4W Change % card      | 16  | 556 | 302  | 148 | `_m: Load 4W Change %`, conditional colour |
| Avg Weekly Load card  | 326 | 556 | 302  | 148 | `_m: Avg Weekly Load (16W)`, Theme color 8 |
| Sport donut (4W)      | 640 | 418 | 624  | 286 | Filtered to 4-week window                  |

**Weekly combo chart series:**

| Role              | Field                           | Notes                                                  |
| ----------------- | ------------------------------- | ------------------------------------------------------ |
| X-axis            | `Dates[End of Week]`            | Sunday end of each ISO week                            |
| Columns (stacked) | `activity_metrics[load_points]` | Per sport segment                                      |
| Column legend     | `activities[sport]`             | Power Query maps training+fitness_equipment → Strength |
| Line              | `_m: Weekly Hours`              | Secondary axis, near-white (`#E6EDF3`)                 |
| Tooltip           | `_m: Week Total Load`           | Shows week total across all sports                     |

**Visual-level filter:** `Dates[_c: In 16W Window]` = TRUE
*(Relative date filters act on the axis field and exclude the current partial week since Sunday is in the future. Filter on the underlying date column instead.)*

**Sport colours:**

| Sport    | Theme name    |
| -------- | ------------- |
| Running  | Theme color 7 |
| Walking  | Theme color 6 |
| Cycling  | Theme color 2 |
| Strength | Theme color 3 |
| Racket   | Theme color 8 |

---

### Page 4 — Zone Analysis 🔲

HR zone distribution and training intensity quality. *(Spec to be added when built.)*

---

### Page 5 — Activity Log 🔲

Browsable activity history with filters. *(Spec to be added when built.)*

---

### Page 6 — Physiology 🔲 *(low priority)*

LTHR, HRmax, resting HR trends over time. *(Spec to be added when built.)*

---

## Design Decisions

| Decision                                             | Rationale                                                                                                                                                                                     |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dark theme                                           | Consistent with elite sport tools (TrainingPeaks, WHOOP, Garmin). Data pops on dark backgrounds.                                                                                              |
| AC ratio thresholds: 1.5 amber / 2.2 red             | Gabbett's 1.3 is for general athletes. Ultra runners regularly and intentionally exceed 1.3 during training blocks.                                                                           |
| Ramp rate thresholds: ±8 green / ±15 amber           | Methodology cites ±8 as the standard safe zone. ±15 extended ceiling for ultra training blocks and long runs.                                                                                 |
| No target line on AC Ratio gauge                     | No meaningful single target value for ultra runners — depends on training phase. Colour zones alone are sufficient.                                                                           |
| `BLANK()` for zero distance                          | Strength/indoor activities have no GPS distance. Blank reads more cleanly than 0.00.                                                                                                          |
| "Don't summarize" aggregation for CTL/ATL fields     | Prevents inflated values if the date hierarchy groups at month level rather than day level.                                                                                                   |
| Sport mapping in Power Query, not DB                 | training + fitness_equipment → Strength handled in Power Query. DB stays as raw ingested data.                                                                                                |
| `_c: In 16W Window` column, not relative date filter | Relative date filters on a weekly chart act on the axis field (End of Week). Since this week's Sunday is in the future, it gets excluded. Filtering by the underlying Date column fixes this. |
| `Dates[maxDate]` = TODAY()                           | Extends the calendar to today so PMC and weekly charts don't have a trailing gap on rest days.                                                                                                |
