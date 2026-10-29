"""A linear opacity fader that can reverse midway."""


class Fader:
    def __init__(self, duration_s=0.3):
        self.duration = duration_s
        self.target = 1.0
        self.origin = 1.0
        self.started = None

    def start(self, target, now):
        # a fresh fader starts from the opposite end; a running one reverses from where it is
        self.origin = (1.0 - float(target)) if self.started is None else self.value(now)
        self.target = float(target)
        self.started = now

    def value(self, now):
        if self.started is None:
            return self.target
        p = min(1.0, max(0.0, (now - self.started) / self.duration))
        return self.origin + (self.target - self.origin) * p

    def active(self, now):
        return self.started is not None and now - self.started < self.duration
