
import numpy as np
class FirstOrderActuator:
    def __init__(self, tau=0.2, umax=2.0, rate=0.5):
        self.tau=tau; self.umax=umax; self.rate=rate; self.u=0.0
    def step(self, u_cmd, dt=1.0):
        u_cmd = float(np.clip(u_cmd, -self.umax, self.umax))
        du = np.clip(u_cmd - self.u, -self.rate*dt, self.rate*dt)
        self.u += du
        self.u += (-(self.u) + u_cmd) * (dt / max(self.tau, 1e-6))
        return float(np.clip(self.u, -self.umax, self.umax))
