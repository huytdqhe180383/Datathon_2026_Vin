# Benchmark Metric Contracts

These contracts define the ecommerce benchmark's preferred metric semantics. Use
them before generic analytics intuition.

## Net Revenue And Order Value

For benchmark questions, `net revenue`, `delivered net revenue`,
`lifetime net revenue`, `order net value`, and `average order value` normally mean
order-item value after item discounts:

```sql
SUM(core.order_items.quantity * core.order_items.unit_price - core.order_items.discount_amount)
```

In source-style shorthand this is `quantity * unit_price - discount_amount`.

Do not subtract `core.returns.refund_amount` and do not use
`core.payments.payment_value` unless the question explicitly asks about payments,
refunds, refunded amount, or final revenue after refunds.

`delivered net revenue` additionally filters:

```sql
core.orders.order_status = 'delivered'
```

## Promo Usage

Promo metrics are based on promo-code usage, not discount amount. In normalized
PostgreSQL, an order used a promo when one or more joined rows exist in
`core.order_item_promotions` for its order items. Do not infer promo usage from
`discount_amount > 0`.

## Returned Orders And Return Rate

When a benchmark question asks for `return rate`, `returned orders`, or
`returned quantity` without saying refund records, use:

```sql
core.orders.order_status = 'returned'
```

Use `core.returns` only for questions that explicitly mention refunds, refunded
amount, return records, returned products from the returns table, or refund dates.

## Repeat-Customer Rates

Repeat-customer rates are calculated among ordering customers, not all registered
customers. Count orders per customer after joining to `core.orders`, then divide
customers with more than one order by ordering customers.

## Top-Decile Customer Revenue Share

For top 10% customer revenue share, rank customers by lifetime item-level net
revenue with `ROW_NUMBER`, compute `CEIL(total_customers * 0.1)`, and include
exactly that many top-ranked customers. Do not use `NTILE(10)` for this benchmark.

## Order-Size Buckets

Order-size bucket labels and ranges are fixed:

- `1`: total units = 1
- `2-3`: total units between 2 and 3
- `4-6`: total units between 4 and 6
- `7-10`: total units between 7 and 10
- `11+`: total units >= 11

## Average Unit Price

When a table asks for `avg_unit_price`, use simple average line-item unit price
for the requested grain unless the question explicitly asks for weighted average
selling price.
