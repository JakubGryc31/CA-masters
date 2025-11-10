
class PID:
    def __init__(self, kp=1.0, ki=0.0, kd=0.0, umin=-2.0, umax=2.0, antiwindup=0.95):
        self.kp=kp; self.ki=ki; self.kd=kd; self.umin=umin; self.umax=umax
        self.i=0.0; self.prev_e=0.0; self.antiwindup=antiwindup
    def reset(self):
        self.i=0.0; self.prev_e=0.0
    def step(self, e, dt=1.0):
        self.i += e*dt
        d = (e - self.prev_e) / dt
        self.prev_e = e
        u = self.kp*e + self.ki*self.i + self.kd*d
        if u > self.umax:
            u = self.umax; self.i *= self.antiwindup
        elif u < self.umin:
            u = self.umin; self.i *= self.antiwindup
        return u
