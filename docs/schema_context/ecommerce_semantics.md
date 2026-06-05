# Ecommerce Schema Semantic Context

## Order Status Vocabulary

The database uses British spelling for canceled orders:

- User words `canceled`, `cancelled`, `cancel`, and `cancellation` map to `core.orders.order_status = 'cancelled'`.
- User words `returned`, `return`, `refund`, and `refunded` can refer to `core.returns` rows and can also relate to `core.orders.order_status = 'returned'`.

Known `core.orders.order_status` values observed in PostgreSQL:

- `cancelled`
- `created`
- `delivered`
- `paid`
- `returned`
- `shipped`

## Refund And Return Logic

Refund amount is stored on `core.returns.refund_amount`.

Join returns to orders through line items:

```sql
core.returns.order_item_id -> core.order_items.order_item_id
core.order_items.order_id -> core.orders.order_id
```

For questions about refunded customers, count distinct `core.orders.customer_id` after joining returns to order items and orders.

For questions that ask about canceled orders, use `core.orders.order_status = 'cancelled'`, not `canceled`.

## Table Roles

- `core.orders`: order header, order date, customer, and order status.
- `core.order_items`: line item bridge between orders, products, and returns.
- `core.returns`: return records and refund amounts at line-item grain.
- `core.customers`: customer dimension.
