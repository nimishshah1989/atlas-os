"""RankPolicy — rank-driven system strategies over Atlas's own scores.

Four modes (Atlas Desk spec, docs/superpowers/specs/2026-07-04-atlas-desk-design.md):
  sector_leaders    top n_sectors by aggregate constituent conviction → top
                    n_per_sector names in each
  conviction        top n_names by composite market-wide, ≤ sector_cap per sector
  quality_momentum  conviction ∩ (RS 3m vs N500 ≥ 0) ∩ above the 200-EMA
  rotation          sectors improving fastest from a below-median strength base →
                    top names within them

Membership semantics with HYSTERESIS: a name ENTERS when it qualifies for the
target set; once in, it STAYS until it falls past the exit buffer (rank
n_names+exit_buffer, sector out of the buffered leader set, or a hard filter
breaks). That is the daily-trader behavior deterministically: winners run,
marginal churn (and its STCG drag) is avoided.

Unlike crossover strategies (which trade TRANSITIONS — day-one state is not an
event), rank strategies trade MEMBERSHIP: the first valid session's qualifying
set emits entries. Execution is still next-session-close, so no lookahead.

ponytail: a name that leaves the scored universe entirely emits no exit and is
carried at last close — add a delisting sweep if that ever bites.
"""

from __future__ import annotations

import pandas as pd

_MODES = ("sector_leaders", "conviction", "quality_momentum", "rotation")


_RISK_OFF = ("Risk-Off", "DISLOCATION_SUSPENDED")


class RankPolicy:
    key = "rank_policy"
    needs_composite = True
    needs_sector = True
    needs_regime = True  # spec: no NEW entries in Risk-Off/dislocation (exits unaffected)
    membership = True  # runner passes floor= instead of filtering events by date

    def __init__(
        self,
        mode: str,
        n_names: int = 10,
        n_sectors: int = 3,
        n_per_sector: int = 3,
        exit_buffer: int = 5,
        sector_cap: int = 3,
        lookback: int = 63,
    ):
        if mode not in _MODES:
            raise ValueError(f"unknown rank_policy mode {mode!r}; known: {_MODES}")
        self.mode = mode
        self.n_names = int(n_names)
        self.n_sectors = int(n_sectors)
        self.n_per_sector = int(n_per_sector)
        self.exit_buffer = int(exit_buffer)
        self.sector_cap = int(sector_cap)
        self.lookback = int(lookback)

    def required_columns(self) -> tuple[str, ...]:
        # technical_daily columns beyond composite/sector (merged by the runner)
        if self.mode == "quality_momentum":
            return ("rs_3m_n500", "above_ema_200")
        return ()

    # ── eligibility: pure per-row _enter/_stay flags from cross-sectional ranks ──

    def _eligibility(self, panel: pd.DataFrame) -> pd.DataFrame:
        df = panel.dropna(subset=["composite"]).copy()
        risk_off = (
            df["regime_state"].isin(_RISK_OFF)
            if "regime_state" in df.columns
            else pd.Series(False, index=df.index)
        )
        if self.mode == "quality_momentum":
            df = df.dropna(subset=["rs_3m_n500", "above_ema_200"])
            ok = df["above_ema_200"].astype(bool) & (df["rs_3m_n500"].astype(float) >= 0)
            df = df.loc[ok]
        if df.empty:
            return pd.DataFrame(columns=pd.Index(["instrument_key", "date", "_enter", "_stay"]))

        if self.mode in ("conviction", "quality_momentum"):
            df["_rk"] = df.groupby("date")["composite"].rank(ascending=False, method="min")
            df["_secrk"] = df.groupby(["date", "sector"])["composite"].rank(
                ascending=False, method="min"
            )
            # sector quota applies at entry: within the top set, only the best
            # sector_cap names of any one sector may enter
            df["_enter"] = (
                (df["_rk"] <= self.n_names)
                & (df["_secrk"] <= self.sector_cap)
                & ~risk_off.loc[df.index]
            )
            df["_stay"] = df["_rk"] <= self.n_names + self.exit_buffer
            return pd.DataFrame(df[["instrument_key", "date", "_enter", "_stay"]])

        # sector modes: strength = mean constituent composite per (date, sector)
        strength = df.groupby(["date", "sector"], as_index=False)["composite"].mean()
        strength = strength.rename(columns={"composite": "_s"})
        strength["_srk"] = strength.groupby("date")["_s"].rank(ascending=False, method="min")

        if self.mode == "rotation":
            strength = strength.sort_values(["sector", "date"])
            g = strength.groupby("sector")
            strength["_srk_then"] = g["_srk"].shift(self.lookback)
            strength["_improve"] = strength["_srk_then"] - strength["_srk"]
            med = strength.groupby("date")["_srk_then"].transform("median")
            eligible = strength["_srk_then"] > med  # improving FROM a below-median base
            strength["_imprk"] = (
                strength.loc[eligible]
                .groupby("date")["_improve"]
                .rank(ascending=False, method="min")
            )
            strength["_sec_enter"] = eligible & (strength["_imprk"] <= self.n_sectors)
            strength["_sec_stay"] = (
                strength["_sec_enter"]
                | (strength["_imprk"] <= self.n_sectors + self.exit_buffer)
                | (strength["_srk"] <= self.n_sectors)
            )  # graduated to outright leader
        else:  # sector_leaders
            strength["_sec_enter"] = strength["_srk"] <= self.n_sectors
            strength["_sec_stay"] = strength["_srk"] <= self.n_sectors + self.exit_buffer

        df = df.merge(
            strength[["date", "sector", "_sec_enter", "_sec_stay"]],
            on=["date", "sector"],
            how="left",
        )
        # merge reset the index — recompute the regime mask on the merged frame
        risk_off = (
            df["regime_state"].isin(_RISK_OFF)
            if "regime_state" in df.columns
            else pd.Series(False, index=df.index)
        )
        df["_nrk"] = df.groupby(["date", "sector"])["composite"].rank(ascending=False, method="min")
        df["_enter"] = (
            df["_sec_enter"].fillna(False) & (df["_nrk"] <= self.n_per_sector) & ~risk_off
        )
        df["_stay"] = df["_sec_stay"].fillna(False) & (
            df["_nrk"] <= self.n_per_sector + self.exit_buffer
        )
        return pd.DataFrame(df[["instrument_key", "date", "_enter", "_stay"]])

    # ── membership state with hysteresis → events ───────────────────────────

    def _scan(self, elig: pd.DataFrame, floor=None) -> pd.DataFrame:
        """Path-dependent membership per name: in on _enter, out only past _stay.

        `floor` — signal floor date. History BEFORE the floor still drives the
        membership state (rotation needs it), but emissions start at the floor:
        a name already in-state at its first session ≥ floor emits an entry
        THERE, so a fresh live track (or backtest window) buys the current
        member set at the next close instead of waiting for names to cycle out
        and back in. Membership is the signal — unlike crossover transitions.
        """
        out = []
        for k, g in elig.groupby("instrument_key", sort=False):
            g = g.sort_values("date")
            held = False
            crossed = floor is None
            for r in g.to_dict("records"):
                nxt = bool(r["_stay"]) if held else bool(r["_enter"])
                if not crossed and r["date"] >= floor:
                    # first session at/after the floor: emit the membership STATE —
                    # entry if in the set (engine skips if already held), exit if a
                    # pre-floor member lapsed exactly here (engine ignores if unheld)
                    crossed = True
                    if nxt:
                        out.append({"instrument_key": k, "date": r["date"], "event": "entry"})
                    elif held:
                        out.append({"instrument_key": k, "date": r["date"], "event": "exit"})
                elif crossed and nxt != held:
                    out.append(
                        {
                            "instrument_key": k,
                            "date": r["date"],
                            "event": "entry" if nxt else "exit",
                        }
                    )
                held = nxt
        return pd.DataFrame(out, columns=pd.Index(["instrument_key", "date", "event"]))

    def events(self, tech: pd.DataFrame, floor=None) -> pd.DataFrame:
        ev = self._scan(self._eligibility(tech), floor=floor)
        return ev.sort_values(by="date").reset_index(drop=True) if not ev.empty else ev

    def state(self, tech: pd.DataFrame) -> pd.Series:
        """Membership at the panel's end (used only if a basket ever wraps this)."""
        elig = self._eligibility(tech)
        held: dict[str, bool] = {}
        for k, g in elig.groupby("instrument_key", sort=False):
            h = False
            for r in g.sort_values("date").to_dict("records"):
                h = bool(r["_stay"]) if h else bool(r["_enter"])
            held[str(k)] = h
        return pd.Series(held, dtype=bool)
