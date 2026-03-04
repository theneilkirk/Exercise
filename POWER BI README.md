# Power BI Dashboard

This file is to help you understand the data in the Power BI Dashboard. The dashboard uses the training engine DB directly as it's source; no other sources.

**Notes**

- In DAX, I use the following prefixes to help organise calculated columns and measures:
  - Columns: `_c: Column Name`
  - Measures: `_m: Measure Name`
- The dashbaord is meant to be personal to me. Therefore it should reflect the type of training expected of an ultra marathoner. A dashboard for a 5k runner would likely be quite different.

## Power BI Info

- Canvas size: standard 16:9 (720x1280px)

Last updated: 2026-03-04

## Tables

### activities

```powerquery
let
    Source = Odbc.DataSource("dsn=Training DB", [HierarchicalNavigation=true]),
    activities_Table = Source{[Name="activities",Kind="Table"]}[Data],
    #"Removed Columns" = Table.RemoveColumns(activities_Table,{"activity_metrics"}),
    #"Changed Type" = Table.TransformColumnTypes(#"Removed Columns",{{"start_time_utc", type datetime}, {"duration_s", Int64.Type}, {"elev_gain_m", Int64.Type}, {"distance_m", Int64.Type}, {"avg_hr", Int64.Type}, {"avg_power", Int64.Type}}),
    #"Inserted Date" = Table.AddColumn(#"Changed Type", "Date", each DateTime.Date([start_time_utc]), type date)
in
    #"Inserted Date"
```

**Columns & Measures**

### activity_hr_zone_summary

```powerquery
let
    Source = Odbc.DataSource("dsn=Training DB", [HierarchicalNavigation=true]),
    activity_hr_zone_summary_Table = Source{[Name="activity_hr_zone_summary",Kind="Table"]}[Data],
    #"Changed Type" = Table.TransformColumnTypes(activity_hr_zone_summary_Table,{{"seconds_in_zone", Int64.Type}})
in
    #"Changed Type"
```

**Columns & Measures**

TBC

### activity_metrics

```powerquery
let
    Source = Odbc.DataSource("dsn=Training DB", [HierarchicalNavigation=true]),
    activity_metrics_Table = Source{[Name="activity_metrics",Kind="Table"]}[Data],
    #"Changed Type" = Table.TransformColumnTypes(activity_metrics_Table,{{"trimp_total", Int64.Type}, {"load_points", Int64.Type}})
in
    #"Changed Type"
```

**Columns & Measures**

TBC

### daily_metrics

```powerquery
let
    Source = Odbc.DataSource("dsn=Training DB", [HierarchicalNavigation=true]),
    daily_metrics_Table = Source{[Name="daily_metrics",Kind="Table"]}[Data],
    #"Changed Type" = Table.TransformColumnTypes(daily_metrics_Table,{{"load_points", Int64.Type}, {"ctl", Int64.Type}, {"atl", Int64.Type}, {"form", Int64.Type}, {"ac_ratio", type number}, {"date", type date}}),
    #"Inserted End of Week" = Table.AddColumn(#"Changed Type", "End of Week", each Date.EndOfWeek([date]), type date)
in
    #"Inserted End of Week"
```

**Columns & Measures**

TBC

### Dates

Creates a table of all possible dates in the activity range, and other date-related columns.

```dax
Dates = 
VAR minDate = MINX(
    ALL(activities),
    DATE(YEAR(activities[start_time_utc]),MONTH(activities[start_time_utc]),DAY(activities[start_time_utc]))
)
VAR maxDate = MAXX(
    ALL(activities),
    DATE(YEAR(activities[start_time_utc]),MONTH(activities[start_time_utc]),DAY(activities[start_time_utc]))
)
RETURN
ADDCOLUMNS(
    CALENDAR(minDate,maxDate),
    "Year",YEAR([Date]),
    "Month Number",MONTH([Date]),
    "Month",FORMAT([Date],"MMMM","en-GB"),
    "Year-Month",FORMAT([Date],"YYYY-MM"),
    "Week Number",WEEKNUM([Date]),
    "Day",DAY([Date])
)
```

**Columns & Measures**

- `_c: In 4-Week Window = Dates[Date]>=[_m: 4 Weeks Ago]`
- `_m: 4 Weeks Ago = TODAY()-28`

### physiology_history

```powerquery
let
    Source = Odbc.DataSource("dsn=Training DB", [HierarchicalNavigation=true]),
    physiology_history_Table = Source{[Name="physiology_history",Kind="Table"]}[Data],
    #"Changed Type" = Table.TransformColumnTypes(physiology_history_Table,{{"value", Int64.Type}})
in
    #"Changed Type"
```

**Columns & Measures**

TBC

### physiology_observed

Not in use.

### zones_hr_history

```powerquery
let
    Source = Odbc.DataSource("dsn=Training DB", [HierarchicalNavigation=true]),
    zones_hr_history_Table = Source{[Name="zones_hr_history",Kind="Table"]}[Data],
    #"Changed Type" = Table.TransformColumnTypes(zones_hr_history_Table,{{"lower_pct", Percentage.Type}, {"upper_pct", Percentage.Type}})
in
    #"Changed Type"
```

**Columns & Measures**

TBC