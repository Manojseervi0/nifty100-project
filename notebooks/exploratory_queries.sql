-- 1
SELECT COUNT(*) FROM companies;

-- 2
SELECT COUNT(*) FROM profitandloss;

-- 3
SELECT COUNT(*) FROM balancesheet;

-- 4
SELECT COUNT(*) FROM cashflow;

-- 5
SELECT company_id, MAX(year)
FROM profitandloss
GROUP BY company_id;

-- 6
SELECT company_id, sales
FROM profitandloss
ORDER BY sales DESC
LIMIT 10;

-- 7
SELECT company_id, net_profit
FROM profitandloss
ORDER BY net_profit DESC
LIMIT 10;

-- 8
SELECT company_id, total_assets
FROM balancesheet
ORDER BY total_assets DESC
LIMIT 10;

-- 9
SELECT company_id, net_cash_flow
FROM cashflow
ORDER BY net_cash_flow DESC
LIMIT 10;

-- 10
SELECT broad_sector, COUNT(*)
FROM sectors
GROUP BY broad_sector;