# Docs

> ...

## Script

```sql
SELECT 
   avg(VALUE),
   max(VALUE),
   (max(VALUE) / 1000) / 60,
   count(*) CANT
FROM latency l
WHERE TIME  between '2026-03-15 00:00:00' and '2026-03-16 00:00:00'
--GROUP BY ROUTE
ORDER BY CANT DESC
```
