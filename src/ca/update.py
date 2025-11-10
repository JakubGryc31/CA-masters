import numpy as np
from scipy.signal import convolve2d

# 8-neighbor (Moore) kernel without center
NEIGH = np.array([[1, 1, 1],
                  [1, 0, 1],
                  [1, 1, 1]], dtype=float)

def _neighbor_mean(x: np.ndarray) -> np.ndarray:
    """Fast Moore-neighborhood mean via 2D convolution (reflective boundary)."""
    s = convolve2d(x, NEIGH, mode='same', boundary='symm')
    c = convolve2d(np.ones_like(x), NEIGH, mode='same', boundary='symm')
    return s / np.maximum(c, 1.0)

def step_ca(state, ctrl_bias: float = 0.0, turb: float = 0.0) -> None:
    """
    One CA update with local diffusion, control coupling, and turbulence injection.
    - attitude 'a' diffuses with neighbors and is driven by controller bias (scaled by local stability)
    - stability 's' decays with turbulence and recovers with time and low control effort
    - speed 'v' trends toward ~1.0 with small coupling to stability
    """
    a, s, v = state.a, state.s, state.v

    # Neighbor means (vectorized)
    la = _neighbor_mean(a)
    ls = _neighbor_mean(s)
    lv = _neighbor_mean(v)

    # Attitude update (control responsiveness depends on local stability)
    responsiveness = 0.25 + 0.75 * ls
    a_new = (
        0.6 * a
        + 0.35 * la
        + responsiveness * ctrl_bias
        + np.random.normal(0.0, 0.02 + 0.15 * turb, size=a.shape)
    )

    # Stability update (decay with turbulence, recover otherwise)
    s_decay = 0.003 + 0.03 * turb
    s_recover = 0.012 + 0.015 * max(0.0, 1.0 - abs(ctrl_bias))
    s_new = (1 - s_decay) * s + 0.05 * ls + s_recover
    s_new = np.clip(s_new, 0.0, 1.0)

    # Speed update (weak coupling to stability)
    v_new = 0.9 * v + 0.1 * lv + 0.01 * (ls - 0.5)

    state.a, state.s, state.v = a_new, s_new, v_new

def crash_condition(state, a_thresh: float = 6.0, s_thresh: float = 0.18) -> bool:
    """Crash if attitude magnitude explodes or stability collapses."""
    return bool(abs(state.mean_attitude()) > a_thresh or state.mean_stability() < s_thresh)
