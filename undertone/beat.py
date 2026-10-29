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
        self.beats = deque(maxlen=96)
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

    def tempo_bpm(self, window_s=30.0):
        """Tempo from a histogram of beat intervals over the window, folded into one octave (70-140 bpm
        before unfolding back to a musical range), refined by the mean of the intervals in the peak bin."""
        recent = [b for b in self.beats if self.t - b <= window_s]
        if len(recent) < 4:
            return 0
        # candidates: every interval between beats up to 3 apart, so swung or missed beats still vote
        cands = []
        for i in range(len(recent)):
            for j in range(i + 1, min(i + 4, len(recent))):
                iv = recent[j] - recent[i]
                if iv > 0:
                    cands.append(iv)
        folded = []
        for iv in cands:
            bpm = 60.0 / iv
            while bpm >= 140:
                bpm /= 2
            while bpm < 70:
                bpm *= 2
            folded.append(bpm)
        bins = {}
        for bpm in folded:
            key = int(bpm // 3)  # 3 bpm wide bins
            bins[key] = bins.get(key, 0) + 1
        peak = max(bins, key=lambda k: bins[k] + 0.5 * bins.get(k - 1, 0) + 0.5 * bins.get(k + 1, 0))
        centre = peak * 3 + 1.5
        near = [b for b in folded if abs(b - centre) <= 4.5]
        bpm = sum(near) / len(near) if near else centre
        # unfold toward the range the raw beat-to-beat intervals actually sit in
        raw = sorted(b - a for a, b in zip(recent, recent[1:]))
        raw_bpm = 60.0 / raw[len(raw) // 2]
        while bpm * 2 <= raw_bpm * 1.3 and bpm < 100:
            bpm *= 2
        while bpm / 2 >= raw_bpm * 0.7 and bpm > 150:
            bpm /= 2
        return round(bpm)
