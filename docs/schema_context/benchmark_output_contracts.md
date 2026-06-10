# Benchmark Output Contracts

The evaluator compares tabular outputs, not just final natural-language answers.
Generated SQL should preserve the requested output shape.

## Column Names

If the question lists required columns, return every listed column and preserve
the exact aliases. Do not replace `zip` with `shipping_zip_code`, `order_month`
with `calendar_month`, or `*_pct` with a decimal-rate alias.

## Percent And Rate Metrics

Columns named with `_pct`, or questions asking for percentage, share, or rate,
should return percent scale:

```sql
ROUND(100.0 * numerator / NULLIF(denominator, 0), 4)
```

Do not return decimal fractions such as `0.089` when the expected metric is
`8.9`.

## Month Labels

For benchmark month outputs, use text labels in `YYYY-MM` format:

```sql
TO_CHAR(DATE_TRUNC('month', date_column), 'YYYY-MM') AS order_month
```

Do not return a timestamp or date such as `2016-05-01`.

## Numeric Rounding

Money and average order value outputs should usually be rounded to 2 decimals.
Rates and shares should usually be rounded to 4 decimals unless the prompt says
otherwise.

## Table Row Counts

Table questions may legitimately return more than 100 rows. Cohort and monthly
series outputs should not be truncated to the first 100 rows.

## Ordering

When the question describes ranking, order by the ranked metric and add a stable
tie-breaker. When the question describes a time series, order chronologically by
the formatted period label.
