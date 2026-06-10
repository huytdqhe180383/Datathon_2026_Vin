# Table Output Comparison

- Suite id: `sql-rag-table-output-20260608T043329Z-rechecked`
- Reference SQL engine: `PostgreSQL reference CSV copied from PandasAI artifacts`
- Questions run: `20`
- Ordered matches: `1`
- Unordered matches: `7`
- Ordering-only mismatches: `6`
- Mismatches or errors after unordered comparison: `13`

## Task Results
- Q01: match=`False` unordered_match=`False` status=`ok` reason=`column_mismatch` classification=`column_mismatch`
- Q02: match=`False` unordered_match=`False` status=`ok` reason=`value_mismatch` classification=`value_mismatch`
- Q03: match=`False` unordered_match=`True` status=`ok` reason=`value_mismatch` classification=`ordering_only` (matches after sorting rows)
- Q04: match=`False` unordered_match=`False` status=`ok` reason=`value_mismatch` classification=`value_mismatch`
- Q05: match=`False` unordered_match=`False` status=`ok` reason=`column_mismatch` classification=`column_mismatch`
- Q06: match=`False` unordered_match=`True` status=`ok` reason=`value_mismatch` classification=`ordering_only` (matches after sorting rows)
- Q07: match=`False` unordered_match=`True` status=`ok` reason=`value_mismatch` classification=`ordering_only` (matches after sorting rows)
- Q08: match=`False` unordered_match=`True` status=`ok` reason=`value_mismatch` classification=`ordering_only` (matches after sorting rows)
- Q09: match=`False` unordered_match=`False` status=`ok` reason=`value_mismatch` classification=`value_mismatch`
- Q10: match=`False` unordered_match=`False` status=`ok` reason=`value_mismatch` classification=`value_mismatch`
- Q11: match=`False` unordered_match=`False` status=`ok` reason=`shape_mismatch` classification=`shape_mismatch`
- Q12: match=`False` unordered_match=`False` status=`ok` reason=`shape_mismatch` classification=`shape_mismatch`
- Q13: match=`False` unordered_match=`False` status=`ok` reason=`value_mismatch` classification=`value_mismatch`
- Q14: match=`False` unordered_match=`True` status=`ok` reason=`value_mismatch` classification=`ordering_only` (matches after sorting rows)
- Q15: match=`False` unordered_match=`False` status=`ok` reason=`value_mismatch` classification=`value_mismatch`
- Q16: match=`False` unordered_match=`True` status=`ok` reason=`value_mismatch` classification=`ordering_only` (matches after sorting rows)
- Q17: match=`True` unordered_match=`True` status=`ok` reason=`exact_after_normalization` classification=`match`
- Q18: match=`False` unordered_match=`False` status=`ok` reason=`column_mismatch` classification=`column_mismatch`
- Q19: match=`False` unordered_match=`False` status=`ok` reason=`value_mismatch` classification=`value_mismatch`
- Q20: match=`False` unordered_match=`False` status=`ok` reason=`shape_mismatch` classification=`shape_mismatch`

## Mismatch Breakdown
- Ordering-only: `6`
- Value mismatch: `7`
- Column mismatch: `3`
- Shape mismatch: `3`
- Match: `1`