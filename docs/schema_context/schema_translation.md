# Schema Translation Notes

The validation SQL uses source-style table names, while the SQL-RAG agent runs
against normalized PostgreSQL `core` tables. Apply these translations.

## Orders

- source `orders.zip` maps to `core.orders.shipping_zip_code`
- source `orders.payment_method` maps to `core.payments.payment_method` joined by
  `order_id`
- source order status values map directly to `core.orders.order_status`
- source `orders.device_type` maps to `core.orders.device_type`
- source `orders.order_source` maps to `core.orders.order_source`

## Customers

- source `customers.gender` maps to `core.customers.gender`
- source `customers.age_group` maps to `core.customers.age_group`
- source `customers.acquisition_channel` maps to `core.customers.acquisition_channel`
- source `customers.zip` maps to `core.customers.zip_code`

## Order Items And Promo Codes

- source `order_items.quantity`, `unit_price`, and `discount_amount` map directly
  to `core.order_items`
- source `order_items.promo_id` and `promo_id_2` are normalized into
  `core.order_item_promotions`
- join promo usage with:

```sql
core.orders -> core.order_items -> core.order_item_promotions
```

Do not use `discount_amount > 0` as a promo proxy.
