import numpy as np
import matplotlib.pyplot as plt

# -------------------------------------------------
# USER INPUTS (High-level parameters)
# -------------------------------------------------

ANNUAL_VOLAT = 0.12          # Annual volatility of stock price
BID_ASK_SP = 1 / 8           # Bid-ask spread
DAILY_TRADE_VOL = 5e6        # Daily trading volume
TRAD_DAYS = 250              # Number of trading days in a year

TOTAL_SHARES = 1000000       # Total shares to sell
STARTING_PRICE = 50          # Starting price per share
LLAMBDA = 1e-6               # Trader's risk aversion
LIQUIDATION_TIME = 60        # Time horizon in minutes
NUM_N = 60                   # Number of trades

# -------------------------------------------------
# DERIVED PARAMETERS
# -------------------------------------------------

DAILY_VOLAT = ANNUAL_VOLAT / np.sqrt(TRAD_DAYS)                 # Daily volatility
EPSILON = BID_ASK_SP / 2                                        # Fixed cost of selling per share
SINGLE_STEP_VARIANCE = (DAILY_VOLAT * STARTING_PRICE) ** 2      # Variance of price changes per step
ETA = BID_ASK_SP / (0.01 * DAILY_TRADE_VOL)                     # Temporary impact coefficient
GAMMA = BID_ASK_SP / (0.1 * DAILY_TRADE_VOL)                    # Permanent impact coefficient

# -------------------------------------------------
# ALMGREN-CHRISS MODEL WITH DETAILED METHODS
# -------------------------------------------------

class AlmgrenChriss:

    def __init__(self, gamma, eta, epsilon, sigma2,
                 llambda, T, N, shares):
        self.gamma = gamma
        self.eta = eta
        self.epsilon = epsilon
        self.singleStepVariance = sigma2
        self.llambda = llambda
        self.liquidation_time = T
        self.num_n = N
        self.total_shares = shares
        self.tau = T / N
        self.eta_hat = eta - 0.5 * gamma * self.tau
        self.kappa_hat = np.sqrt((llambda * sigma2) / self.eta_hat)
        self.kappa = np.arccosh((self.kappa_hat**2 * self.tau**2)/2 + 1) / self.tau

    # Permanent impact
    def permanentImpact(self, sharesToSell):
        return self.gamma * sharesToSell

    # Temporary impact
    def temporaryImpact(self, sharesToSell):
        return (self.epsilon * np.sign(sharesToSell)) + ((self.eta / self.tau) * sharesToSell)

    # Expected shortfall (basic)
    def get_expected_shortfall(self, sharesToSell):
        ft = 0.5 * self.gamma * (sharesToSell ** 2)
        st = self.epsilon * sharesToSell
        tt = (self.eta_hat / self.tau) * self.total_shares
        return ft + st + tt

    # Expected shortfall for AC optimal strategy
    def get_AC_expected_shortfall(self, sharesToSell):
        ft = 0.5 * self.gamma * (sharesToSell ** 2)        
        st = self.epsilon * sharesToSell        
        tt = self.eta_hat * (sharesToSell ** 2)       
        nft = np.tanh(0.5 * self.kappa * self.tau) * (self.tau * np.sinh(2 * self.kappa * self.liquidation_time) \
                                                      + 2 * self.liquidation_time * np.sinh(self.kappa * self.tau))       
        dft = 2 * (self.tau ** 2) * (np.sinh(self.kappa * self.liquidation_time) ** 2)   
        fot = nft / dft       
        return ft + st + (tt * fot)  

    # Variance of AC strategy
    def get_AC_variance(self, sharesToSell):
        ft = 0.5 * (self.singleStepVariance) * (sharesToSell ** 2)                        
        nst  = self.tau * np.sinh(self.kappa * self.liquidation_time) * np.cosh(self.kappa * (self.liquidation_time - self.tau)) \
               - self.liquidation_time * np.sinh(self.kappa * self.tau)        
        dst = (np.sinh(self.kappa * self.liquidation_time) ** 2) * np.sinh(self.kappa * self.tau)        
        st = nst / dst
        return ft * st

    # AC Utility = expected shortfall + risk aversion * variance
    def compute_AC_utility(self, sharesToSell):
        if self.liquidation_time == 0:
            return 0        
        E = self.get_AC_expected_shortfall(sharesToSell)
        V = self.get_AC_variance(sharesToSell)
        return E + self.llambda * V

    # Optimal trade list for AC
    def get_trade_list(self):
        trade_list = np.zeros(self.num_n)
        ftn = 2 * np.sinh(0.5 * self.kappa * self.tau)
        ftd = np.sinh(self.kappa * self.liquidation_time)
        ft = (ftn / ftd) * self.total_shares
        for i in range(1, self.num_n + 1):
            st = np.cosh(self.kappa * (self.liquidation_time - (i - 0.5) * self.tau))
            trade_list[i - 1] = st
        trade_list *= ft
        return trade_list

    # Variance of an arbitrary trajectory (for TWAP/Dump)
    def trajectory_variance(self, trades):
        return np.sum((trades ** 2) * self.singleStepVariance)

# -------------------------------------------------
# BUILD MODEL
# -------------------------------------------------

ac = AlmgrenChriss(
    GAMMA,
    ETA,
    EPSILON,
    SINGLE_STEP_VARIANCE,
    LLAMBDA,
    LIQUIDATION_TIME,
    NUM_N,
    TOTAL_SHARES
)

ac_trades = ac.get_trade_list()

# -------------------------------------------------
# TWAP AND DUMP STRATEGIES
# -------------------------------------------------

twap = np.repeat(TOTAL_SHARES / NUM_N, NUM_N)
dump = np.zeros(NUM_N)
dump[0] = TOTAL_SHARES

# -------------------------------------------------
# COMPUTE UTILITIES USING CONSISTENT VARIANCE
# -------------------------------------------------

ac_util = ac.compute_AC_utility(TOTAL_SHARES)
twap_util = ac.get_expected_shortfall(TOTAL_SHARES) + LLAMBDA * ac.trajectory_variance(twap)
dump_util = ac.get_expected_shortfall(TOTAL_SHARES) + LLAMBDA * ac.trajectory_variance(dump)

print("\nExecution Utility Comparison")
print("----------------------------")
print("Almgren-Chriss:", ac_util)
print("TWAP:", twap_util)
print("Dump:", dump_util)

# havent implemented step function that moves the mkt when you dump so costs are inversed 
# will have to change the basic expected shotfall after implementing also 


# -------------------------------------------------
# PLOT EXECUTION TRAJECTORY BASED ON UTILITY
# -------------------------------------------------

plt.figure(figsize=(10,6))
plt.plot(np.cumsum(ac_trades), label=f"AC Utility = {ac_util:.2f}")
plt.plot(np.cumsum(twap), label=f"TWAP Utility = {twap_util:.2f}")
plt.plot(np.cumsum(dump), label=f"Dump Utility = {dump_util:.2f}")
plt.title(f"Optimal Execution Comparison ({TOTAL_SHARES} shares)")
plt.xlabel("Execution Step")
plt.ylabel("Shares Sold")
plt.legend()
plt.grid(True)
plt.show()