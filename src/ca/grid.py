
import numpy as np
class CAState:
    def __init__(self, h=40, w=40, seed=0):
        self.h, self.w = h, w
        self.rng = np.random.default_rng(seed)
        self.a = self.rng.normal(0.0, 0.03, size=(h,w))
        self.s = self.rng.uniform(0.6, 0.9, size=(h,w))
        self.v = self.rng.normal(1.0, 0.02, size=(h,w))
        self._neigh = [(di,dj) for di in (-1,0,1) for dj in (-1,0,1) if not (di==0 and dj==0)]
    def mean_attitude(self): return float(self.a.mean())
    def mean_stability(self): return float(self.s.mean())
    def mean_speed(self): return float(self.v.mean())
    def neighbors(self, i,j):
        for di,dj in self._neigh:
            ni, nj = i+di, j+dj
            if 0 <= ni < self.h and 0 <= nj < self.w:
                yield ni, nj
