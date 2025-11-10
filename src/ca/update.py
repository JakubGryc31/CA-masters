
import numpy as np
def step_ca(state, ctrl_bias=0.0, turb=0.0):
    a, s, v = state.a, state.s, state.v
    a_new = a.copy(); s_new = s.copy(); v_new = v.copy()
    H, W = a.shape
    for i in range(H):
        for j in range(W):
            acc_a=acc_s=acc_v=0.0; cnt=0
            for ni,nj in state.neighbors(i,j):
                acc_a += a[ni,nj]; acc_s += s[ni,nj]; acc_v += v[ni,nj]; cnt += 1
            la = acc_a/cnt if cnt else a[i,j]
            ls = acc_s/cnt if cnt else s[i,j]
            lv = acc_v/cnt if cnt else v[i,j]
            responsiveness = 0.25 + 0.75*ls
            a_new[i,j] = 0.6*a[i,j] + 0.35*la + responsiveness*ctrl_bias + np.random.normal(0.0, 0.02 + 0.15*turb)
            s_decay = 0.003 + 0.03*turb
            s_recover = 0.012 + 0.015*max(0.0, 1.0-abs(ctrl_bias))
            s_new[i,j] = (1 - s_decay)*s[i,j] + 0.05*ls + s_recover
            s_new[i,j] = np.clip(s_new[i,j], 0.0, 1.0)
            v_new[i,j] = 0.9*v[i,j] + 0.1*lv + 0.01*(ls-0.5)
    state.a, state.s, state.v = a_new, s_new, v_new

def crash_condition(state, a_thresh=6.0, s_thresh=0.18):
    return bool(abs(state.mean_attitude()) > a_thresh or state.mean_stability() < s_thresh)
