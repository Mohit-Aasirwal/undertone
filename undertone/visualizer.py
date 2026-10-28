"""Pure visualizer math: spectrum to log-spaced band levels, smoothing, ring geometry."""
import numpy as np


def band_levels(magnitudes, sample_rate, n_bands, fmin=40.0, fmax=12000.0, floor_db=-60.0, reference=None):
    """Log-spaced band energies mapped to 0..1 via dB above a noise floor, relative to `reference`
    (defaults to the frame's own peak; callers pass a slowly-decaying running peak for auto-gain)."""
    n_bins = len(magnitudes)
    freqs = np.linspace(0, sample_rate / 2, n_bins)
    edges = np.geomspace(fmin, fmax, n_bands + 1)
    levels = np.zeros(n_bands)
    scale = max(float(reference if reference is not None else np.max(magnitudes)), 1e-9)
    for i in range(n_bands):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if not mask.any():
            continue
        power = float(np.mean(magnitudes[mask])) / scale
        if power <= 0:
            continue
        db = 20 * np.log10(power + 1e-12)
        levels[i] = np.clip((db - floor_db) / -floor_db, 0.0, 1.0)
    if float(np.max(magnitudes)) <= 1e-9:
        return np.zeros(n_bands)
    return levels


def smooth_levels(prev, new, attack, decay):
    prev, new = np.asarray(prev, float), np.asarray(new, float)
    rate = np.where(new > prev, attack, decay)
    return prev + (new - prev) * rate


def ring_radii(levels, base, spacing, swell):
    idx = np.arange(len(levels))
    return base + idx * spacing + np.asarray(levels, float) * swell
