-- Atlas data foundation — consumption layer (materialized views) on the clean,
-- 25y, corp-action-adjusted staging data. Apply AFTER backfill+compute+validate.
-- These are the surfaces the frontend reads (e.g. the Markets Today redesign's
-- breadth charts: counts of Nifty-500 stocks above 21/50/200-EMA, 25y history).
--
-- Refresh: `refresh materialized view concurrently foundation_staging.<name>;`
-- (a unique index per MV enables CONCURRENTLY — added below).

-- ── Nifty-500 breadth, daily, full history ────────────────────────────────
-- Counts (not %), per docs/markets-today-redesign.md §B/§C. Current membership
-- for all history (locked decision). instrument_id aligns with de_instrument.
drop materialized view if exists foundation_staging.mv_breadth_nifty500_daily;
create materialized view foundation_staging.mv_breadth_nifty500_daily as
select t.date,
       count(*)                                          as n_total,
       count(*) filter (where t.above_ema_21)            as n_above_21ema,
       count(*) filter (where t.above_ema_50)            as n_above_50ema,
       count(*) filter (where t.above_ema_200)           as n_above_200ema,
       count(*) filter (where t.ema_21  is not null)     as n_with_21ema,
       count(*) filter (where t.ema_200 is not null)     as n_with_200ema
from foundation_staging.technical_daily t
join public.de_instrument i on i.id = t.instrument_id
where t.asset_class = 'stock' and i.nifty_500
group by t.date;
create unique index if not exists ux_mv_breadth_date
    on foundation_staging.mv_breadth_nifty500_daily (date);

-- ── Latest snapshot per instrument (screeners / tables) ───────────────────
drop materialized view if exists foundation_staging.mv_instrument_latest;
create materialized view foundation_staging.mv_instrument_latest as
select distinct on (t.instrument_id)
       t.instrument_id, t.asset_class, t.symbol, t.date,
       o.close_adj, t.ema_21, t.ema_50, t.ema_200, t.rsi_14,
       t.ret_1d, t.ret_1m, t.ret_3m, t.ret_6m, t.ret_12m,
       t.rs_3m_n500, t.rs_6m_n500, t.rs_12m_n500,
       t.above_ema_21, t.above_ema_50, t.above_ema_200
from foundation_staging.technical_daily t
left join foundation_staging.ohlcv_stock o
       on o.instrument_id = t.instrument_id and o.date = t.date
order by t.instrument_id, t.date desc;
create unique index if not exists ux_mv_latest_iid
    on foundation_staging.mv_instrument_latest (instrument_id);
