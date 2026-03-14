"""
Almgren-Chriss optimal execution model.

Refactored from OptimalPath(withoutMarketMovements).py to accept a config
dataclass and support calibration from live/replayed L1 orderbook events.
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class ACConfig:
    gamma: float        # permanent impact coefficient
    eta: float          # temporary impact coefficient
    epsilon: float      # half-spread (fixed cost per share)
    sigma2: float       # single-step price variance
    llambda: float      # trader risk aversion
    T: float            # liquidation time (minutes)
    N: int              # number of discrete trades
    shares: float       # total shares to liquidate


class AlmgrenChriss:
    """
    Almgren-Chriss (2000) optimal liquidation model.

    All math is equivalent to the original OptimalPath file but organized
    around an ACConfig dataclass for clean dependency injection.
    """

    def __init__(self, config: ACConfig):
        self.config = config

        self.gamma = config.gamma
        self.eta = config.eta
        self.epsilon = config.epsilon
        self.singleStepVariance = config.sigma2
        self.llambda = config.llambda
        self.liquidation_time = config.T
        self.num_n = config.N
        self.total_shares = config.shares

        self.tau = config.T / config.N
        self.eta_hat = config.eta - 0.5 * config.gamma * self.tau

        # Guard against non-positive eta_hat (degenerate parameterization)
        if self.eta_hat <= 0:
            self.eta_hat = max(config.eta * 0.01, 1e-12)

        kappa_hat_sq = (config.llambda * config.sigma2) / self.eta_hat
        self.kappa_hat = np.sqrt(max(kappa_hat_sq, 0.0))

        # kappa = arccosh(kappa_hat^2 * tau^2 / 2 + 1) / tau
        cosh_arg = (self.kappa_hat ** 2 * self.tau ** 2) / 2.0 + 1.0
        self.kappa = np.arccosh(max(cosh_arg, 1.0)) / self.tau

    # ------------------------------------------------------------------
    # Impact functions
    # ------------------------------------------------------------------

    def permanentImpact(self, sharesToSell: float) -> float:
        """Linear permanent market impact: gamma * shares."""
        return self.gamma * sharesToSell

    def temporaryImpact(self, sharesToSell: float) -> float:
        """
        Temporary impact = fixed half-spread + linear rate term.
        sharesToSell here is the *number of shares* in one trade slice.
        """
        return (self.epsilon * np.sign(sharesToSell)) + ((self.eta / self.tau) * sharesToSell)

    # ------------------------------------------------------------------
    # Expected shortfall / variance / utility
    # ------------------------------------------------------------------

    def get_expected_shortfall(self, sharesToSell: float) -> float:
        """
        Simplified expected shortfall (used for TWAP/Dump baselines).
        E = 0.5*gamma*X^2 + epsilon*X + (eta_hat/tau)*X
        """
        ft = 0.5 * self.gamma * (sharesToSell ** 2)
        st = self.epsilon * sharesToSell
        tt = (self.eta_hat / self.tau) * self.total_shares
        return ft + st + tt

    def get_AC_expected_shortfall(self, sharesToSell: float) -> float:
        """
        AC optimal expected shortfall using the closed-form hyperbolic solution.
        """
        ft = 0.5 * self.gamma * (sharesToSell ** 2)
        st = self.epsilon * sharesToSell
        tt = self.eta_hat * (sharesToSell ** 2)

        # Hyperbolic correction factor
        sinh_kT = np.sinh(self.kappa * self.liquidation_time)
        sinh_kt = np.sinh(self.kappa * self.tau)
        tanh_half = np.tanh(0.5 * self.kappa * self.tau)

        nft = tanh_half * (
            self.tau * np.sinh(2 * self.kappa * self.liquidation_time)
            + 2 * self.liquidation_time * sinh_kt
        )
        dft = 2 * (self.tau ** 2) * (sinh_kT ** 2)

        if abs(dft) < 1e-30:
            fot = 1.0
        else:
            fot = nft / dft

        return ft + st + (tt * fot)

    def get_AC_variance(self, sharesToSell: float) -> float:
        """Variance of the AC optimal trajectory."""
        ft = 0.5 * self.singleStepVariance * (sharesToSell ** 2)

        sinh_kT = np.sinh(self.kappa * self.liquidation_time)
        sinh_kt = np.sinh(self.kappa * self.tau)
        cosh_term = np.cosh(self.kappa * (self.liquidation_time - self.tau))

        nst = (
            self.tau * sinh_kT * cosh_term
            - self.liquidation_time * sinh_kt
        )
        dst = (sinh_kT ** 2) * sinh_kt

        if abs(dst) < 1e-30:
            st = 1.0
        else:
            st = nst / dst

        return ft * st

    def compute_AC_utility(self, sharesToSell: float) -> float:
        """AC utility = E[shortfall] + lambda * Var[shortfall]."""
        if self.liquidation_time == 0:
            return 0.0
        E = self.get_AC_expected_shortfall(sharesToSell)
        V = self.get_AC_variance(sharesToSell)
        return E + self.llambda * V

    def get_trade_list(self) -> np.ndarray:
        """
        Return the N-element array of optimal trade sizes (shares sold per step)
        following the AC closed-form trajectory.

        Numerical guard
        ---------------
        When kappa * T is large (e.g. N=1000 with small tau and high sigma),
        sinh(kappa * T) overflows to inf, making every trade qty = 0.  We
        detect this and fall back to the appropriate degenerate schedule:
          - kappa * T > threshold (very front-loaded)  → dump (sell all at step 0)
          - kappa * T ≈ 0         (very back-loaded)   → uniform (TWAP)
        """
        # Clamp kappa * T to prevent float overflow in sinh/cosh (sinh(710) ≈ 5e307)
        _kT = self.kappa * self.liquidation_time
        _kt_half = 0.5 * self.kappa * self.tau

        if _kT > 700:
            # Extremely front-loaded: AC degenerates toward immediate liquidation
            schedule = np.zeros(self.num_n)
            schedule[0] = self.total_shares
            return schedule

        sinh_kT = np.sinh(_kT)

        if abs(sinh_kT) < 1e-30 or not np.isfinite(sinh_kT):
            # kappa ≈ 0: schedule is flat (TWAP limit)
            return np.full(self.num_n, self.total_shares / self.num_n)

        ftn = 2 * np.sinh(_kt_half)
        ft = (ftn / sinh_kT) * self.total_shares

        trade_list = np.zeros(self.num_n)
        for i in range(1, self.num_n + 1):
            arg = self.kappa * (self.liquidation_time - (i - 0.5) * self.tau)
            # cosh can also overflow for large kappa; clamp arg symmetrically
            trade_list[i - 1] = np.cosh(min(arg, 700.0))

        trade_list *= ft

        trade_list = np.maximum(trade_list, 0.0)
        total = trade_list.sum()
        if total > 1e-30:
            trade_list = trade_list * (self.total_shares / total)
        else:
            # All weights collapsed to zero — fall back to uniform
            return np.full(self.num_n, self.total_shares / self.num_n)

        return trade_list

    def trajectory_variance(self, trades: np.ndarray) -> float:
        """
        Variance of an arbitrary trajectory (e.g., TWAP or Dump).
        V = sigma2 * sum(n_k^2) where n_k is shares sold at step k.
        """
        return float(np.sum((trades ** 2) * self.singleStepVariance))

    def recalibrate(self, sigma2: float, epsilon: float) -> None:
        """
        Rolling recalibration: update volatility and half-spread estimates,
        then recompute kappa so the optimal schedule adapts to current
        market conditions (heteroscedasticity correction).

        Called by the runner every `calibration_window` ticks with the
        rolling-window variance of mid-price log-returns.

        Parameters
        ----------
        sigma2 : float
            New per-tau price variance estimate (price² units).
        epsilon : float
            New half-spread estimate (absolute price units).
        """
        self.singleStepVariance = sigma2
        self.epsilon = epsilon
        self.config.sigma2 = sigma2
        self.config.epsilon = epsilon

        # Recompute eta_hat with updated epsilon (gamma and eta unchanged)
        self.eta_hat = self.eta - 0.5 * self.gamma * self.tau
        if self.eta_hat <= 0:
            self.eta_hat = max(self.eta * 0.01, 1e-12)

        kappa_hat_sq = (self.llambda * sigma2) / self.eta_hat
        self.kappa_hat = np.sqrt(max(kappa_hat_sq, 0.0))

        cosh_arg = (self.kappa_hat ** 2 * self.tau ** 2) / 2.0 + 1.0
        self.kappa = np.arccosh(max(cosh_arg, 1.0)) / self.tau


# ---------------------------------------------------------------------------
# Calibration from replay data
# ---------------------------------------------------------------------------

def calibrate_from_replay(
    events: list[dict],
    T: float,
    N: int,
    shares: float,
    llambda: float = 1e-6,
    daily_volume_estimate: float = 1e9,
) -> ACConfig:
    """
    Derive Almgren-Chriss parameters from L1 replay events.

    Parameters
    ----------
    events : list of dicts
        Each dict must contain at minimum 'bid', 'ask', and 'timestamp_ms'.
        'mid' is computed as (bid + ask) / 2 if not present.
    T : float
        Liquidation horizon in minutes.
    N : int
        Number of discrete trades.
    shares : float
        Total shares to liquidate.
    llambda : float
        Trader risk aversion coefficient.
    daily_volume_estimate : float
        Estimated daily notional volume (USD) for impact scaling.

    Returns
    -------
    ACConfig
        Calibrated configuration ready to pass to AlmgrenChriss().
    """
    if not events:
        raise ValueError("events list is empty; cannot calibrate.")

    bids = np.array([e["bid"] for e in events], dtype=float)
    asks = np.array([e["ask"] for e in events], dtype=float)
    mids = np.array([e.get("mid", (e["bid"] + e["ask"]) / 2.0) for e in events], dtype=float)

    # Half-spread: median (ask - bid) / 2
    half_spreads = (asks - bids) / 2.0
    epsilon = float(np.median(half_spreads))
    epsilon = max(epsilon, 1e-8)

    # BID_ASK_SP for impact calibration
    bid_ask_sp = 2.0 * epsilon

    # Permanent impact: gamma = bid_ask_sp / (0.1 * daily_volume)
    gamma = bid_ask_sp / (0.1 * daily_volume_estimate)

    # Temporary impact: eta = bid_ask_sp / (0.01 * daily_volume)
    eta = bid_ask_sp / (0.01 * daily_volume_estimate)

    # sigma2: variance of mid-price log-returns at interval tau = T/N
    # We compute returns on the raw tick series, then scale to tau.
    tau = T / N  # minutes per trade
    if len(mids) >= 2:
        log_returns = np.diff(np.log(mids))
        tick_variance = float(np.var(log_returns))
        # Scale from per-tick to per-tau interval.
        # Estimate ticks per minute from timestamps if available.
        timestamps = np.array([e.get("timestamp_ms", 0) for e in events], dtype=float)
        elapsed_ms = timestamps[-1] - timestamps[0]
        if elapsed_ms > 0:
            ticks_per_minute = (len(events) - 1) / (elapsed_ms / 60_000.0)
        else:
            ticks_per_minute = len(events)  # fallback: 1 minute total
        ticks_per_tau = ticks_per_minute * tau
        sigma2_per_tau = tick_variance * ticks_per_tau
        # Convert from fractional variance to price variance (price-squared units)
        mid_price = float(np.median(mids))
        sigma2 = sigma2_per_tau * (mid_price ** 2)
    else:
        # Fallback with single event: use a rough BTC-like estimate
        mid_price = float(mids[0]) if len(mids) > 0 else 97_000.0
        sigma2 = (0.0002 * mid_price) ** 2

    sigma2 = max(sigma2, 1e-10)

    return ACConfig(
        gamma=gamma,
        eta=eta,
        epsilon=epsilon,
        sigma2=sigma2,
        llambda=llambda,
        T=T,
        N=N,
        shares=shares,
    )
