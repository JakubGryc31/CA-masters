
import numpy as np
class Turbulence:
    def __init__(self, theta=0.3, sigma=0.15, dt=1.0, seed=0):
        self.theta = theta; self.sigma = sigma; self.dt = dt
        self.rng = np.random.default_rng(seed); self.x = 0.0
    def step(self, level=0.0):
        dw = self.rng.normal(0.0, self.dt**0.5)
        self.x += self.theta*(0.0 - self.x)*self.dt + self.sigma*dw*level
        return float(self.x)
