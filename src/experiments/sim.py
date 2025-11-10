
from ..ca.grid import CAState
from ..ca.update import step_ca, crash_condition
from ..control.pid import PID
from ..dynamics.actuator import FirstOrderActuator
from ..dynamics.noise import Turbulence

from ..ca.grid import CAState
from ..ca.update import step_ca, crash_condition
from ..control.pid import PID
from ..dynamics.actuator import FirstOrderActuator
from ..dynamics.noise import Turbulence

def run(T=140, seed=0, kp=0.8, ki=0.05, kd=0.12, a_ref=0.0,
        pitch_up_at=35, pitch_up_delta=0.3, failure_window=None,
        turb_sched=lambda t:0.0, grid_h=30, grid_w=30):
    state = CAState(h=grid_h, w=grid_w, seed=seed)
    pid = PID(kp,ki,kd, umin=-2.0, umax=2.0)
    act = FirstOrderActuator(tau=0.3, umax=2.0, rate=0.5)
    turb = Turbulence(theta=0.3, sigma=0.2, seed=seed)
    log = {k:[] for k in ['t','attitude','stability','speed','u_cmd','u_eff','turb','crashed','a_ref']}
    for t in range(T):
        ref = a_ref + (pitch_up_delta if t==pitch_up_at else 0.0)
        e = ref - state.mean_attitude()
        if failure_window and (failure_window[0] <= t < failure_window[1]):
            old_ki, old_kd = pid.ki, pid.kd
            pid.ki, pid.kd = 0.0, 0.0
            u_cmd = pid.step(e)
            pid.ki, pid.kd = old_ki, old_kd
        else:
            u_cmd = pid.step(e)
        u_eff = act.step(u_cmd)
        level = turb_sched(t)
        noise = turb.step(level=level)
        step_ca(state, ctrl_bias=u_eff+noise, turb=level)
        crashed = crash_condition(state)
        log['t'].append(t); log['attitude'].append(state.mean_attitude())
        log['stability'].append(state.mean_stability()); log['speed'].append(state.mean_speed())
        log['u_cmd'].append(u_cmd); log['u_eff'].append(u_eff); log['turb'].append(level)
        log['crashed'].append(crashed); log['a_ref'].append(ref)
        if crashed: break
    return log
