
import numpy as np, pandas as pd
def metrics_from_log(log):
    df = pd.DataFrame(log)
    df['attitude_err'] = df['attitude'] - df['a_ref']
    overshoot = float(np.max(np.abs(df['attitude_err'])))
    ttr = float(next((t for t,e in zip(df['t'], np.abs(df['attitude_err'])) if e<0.05), df['t'].iloc[-1]))
    stab_var = float(np.var(df['stability']))
    effort = float(np.sum(np.abs(df['u_eff'])))
    crash = bool(df['crashed'].any())
    return {'overshoot':overshoot,'time_to_recover':ttr,'stability_variance':stab_var,'control_effort':effort,'crash':crash}, df
