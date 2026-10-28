"""Beat detection from a low-band energy stream: onset flux vs an adaptive threshold."""
import math
from collections import deque


class OnsetDetector:
    def __init__(self, frame_hz, history_s=1.5, refractory_s=0.12, pulse_tau_s=0.25, floor=0.03):
        self.dt = 1.0 / frame_hz
        self.history = deque(maxlen=max(4, int(history_s * frame_hz)))
        self.energy_history = deque(maxlen=max(4, int(history_s * frame_hz)))
        self.refractory = refractory_s
        self.tau = pulse_tau_s
        self.floor = floor
        self.prev = 0.0
        self.t = 0.0
        self.last_beat = -1e9
        self.beats = deque(maxlen=24)
        self._pulse = 0.0

    def feed(self, energy):
        """Advance one frame with the current bass energy (0..1). Returns True on a beat."""
        self.t += self.dt
        self._pulse *= math.exp(-self.dt / self.tau)
        flux = max(0.0, energy - self.prev)
        hist = sorted(self.history)
        median = hist[len(hist) // 2] if hist else 0.0
        mean = sum(hist) / len(hist) if hist else 0.0
        # a rise must beat the recent flux statistics, be large relative to the level it rose from,
        # and be a real fraction of the loudest recent frame so noise-floor wobble never counts
        peak = max(self.energy_history) if self.energy_history else 0.0
        threshold = max(self.floor, 1.5 * median + 0.5 * mean, 0.2 * self.prev, 0.25 * peak)
        self.prev = energy
        self.energy_history.append(energy)
        self.history.append(flux)
        if flux > threshold and self.t - self.last_beat >= self.refractory:
            self.last_beat = self.t
            self.beats.append(self.t)
            self._pulse = 1.0
            return True
        return False

    def pulse(self):
        return self._pulse

    def tempo_bpm(self, window_s=8.0):
        recent = [b for b in self.beats if self.t - b <= window_s]
        if len(recent) < 4:
            return 0
        intervals = sorted(b - a for a, b in zip(recent, recent[1:]))
        median = intervals[len(intervals) // 2]
        if median <= 0:
            return 0
        # mean of the intervals near the median: finer than the frame-quantized median itself
        near = [i for i in intervals if abs(i - median) <= 0.2 * median]
        bpm = 60.0 / (sum(near) / len(near))
        while bpm > 200:
            bpm /= 2
        while bpm < 60:
            bpm *= 2
        return round(bpm)
