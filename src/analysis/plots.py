
import matplotlib.pyplot as plt
def plot_timeseries(df, path_prefix):
    plt.figure(); plt.plot(df['t'], df['attitude']); plt.xlabel('t'); plt.ylabel('attitude')
    plt.savefig(path_prefix+'_attitude.png', dpi=150, bbox_inches='tight'); plt.close()
    plt.figure(); plt.plot(df['t'], df['stability']); plt.xlabel('t'); plt.ylabel('stability')
    plt.savefig(path_prefix+'_stability.png', dpi=150, bbox_inches='tight'); plt.close()
    plt.figure(); plt.plot(df['t'], df['u_cmd']); plt.xlabel('t'); plt.ylabel('u_cmd')
    plt.savefig(path_prefix+'_u_cmd.png', dpi=150, bbox_inches='tight'); plt.close()
    plt.figure(); plt.plot(df['t'], df['u_eff']); plt.xlabel('t'); plt.ylabel('u_eff')
    plt.savefig(path_prefix+'_u_eff.png', dpi=150, bbox_inches='tight'); plt.close()
