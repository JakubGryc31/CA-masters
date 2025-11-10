
def turbulence_schedule_factory(low=0.0, mid=0.4, late=0.1, t1=60, t2=120):
    def schedule(t):
        if t < t1: return low
        if t < t2: return mid
        return late
    return schedule
