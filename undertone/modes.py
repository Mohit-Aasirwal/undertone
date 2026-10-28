"""Visualizer modes. Pure geometry helpers are testable; draw_* functions paint with cairo.

Every draw function has the signature (cr, cx, cy, max_r, levels, pulse, accent, opacity, state)
and must stay inside the circle of radius max_r + 4 so the per-frame redraw clip holds."""
import math
import random
from dataclasses import dataclass

import numpy as np

from .visualizer import ring_radii

MODES = ["rings", "bars", "wave", "particles"]


# ---- geometry ---------------------------------------------------------------
def bar_layout(levels, inner_r, max_len):
    """(angle, outer_radius) per bar: each band drawn mirrored on the left and right halves."""
    n = len(levels)
    out = []
    for i, level in enumerate(levels):
        frac = (i + 0.5) / n
        outer = inner_r + max_len * float(level)
        out.append((-math.pi / 2 + frac * math.pi, outer))   # right half, top to bottom
        out.append((-math.pi / 2 - frac * math.pi, outer))   # left half, top to bottom
    return out


def wave_points(levels, base_r, amp, phase, n_points=180):
    """A closed ring whose radius wobbles by the band levels; returns (x, y) offsets from centre."""
    lv = np.asarray(levels, float)
    pts = []
    for k in range(n_points):
        a = 2 * math.pi * k / n_points
        wobble = 0.0
        for i, level in enumerate(lv):
            wobble += float(level) * math.sin((i + 2) * a + phase * (1 + i * 0.3))
        wobble /= max(len(lv), 1)
        r = base_r + amp * wobble
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


@dataclass
class Particle:
    angle: float
    r: float
    speed: float
    life: float
    size: float


class ParticleField:
    def __init__(self, max_particles=240, seed=None):
        self.max = max_particles
        self.rng = random.Random(seed)
        self.particles = []

    def step(self, dt, pulse, level, beat):
        for p in self.particles:
            p.r += p.speed * dt * (1 + 2 * pulse)
            p.life -= dt
        self.particles = [p for p in self.particles if p.life > 0]
        if beat:
            burst = int(12 + 40 * level)
            for _ in range(min(burst, self.max - len(self.particles))):
                self.particles.append(Particle(
                    angle=self.rng.uniform(0, 2 * math.pi), r=0.08,
                    speed=self.rng.uniform(0.25, 0.6), life=self.rng.uniform(1.2, 2.4),
                    size=self.rng.uniform(1.5, 4.0)))


# ---- drawing ----------------------------------------------------------------
def _tint(accent, level):
    ar, ag, ab = accent
    mix = 0.5 * float(level)
    return (0.85 + (ar - 0.85) * mix, 0.85 + (ag - 0.85) * mix, 0.88 + (ab - 0.88) * mix)


def draw_rings(cr, cx, cy, max_r, levels, pulse, accent, opacity, state):
    n = len(levels)
    base = max_r * 0.22
    spacing = (max_r - base) / max(n, 1)
    kick = pulse * spacing * 0.5
    for r, level in zip(ring_radii(levels, base + kick, spacing, spacing * 0.9), levels):
        cr.set_source_rgba(*_tint(accent, level), opacity * (0.35 + 0.65 * float(level)))
        cr.set_line_width(1.0 + 2.5 * float(level))
        cr.new_sub_path()
        cr.arc(cx, cy, min(float(r), max_r), 0, 2 * math.pi)
        cr.stroke()


def draw_bars(cr, cx, cy, max_r, levels, pulse, accent, opacity, state):
    inner = max_r * 0.45 + pulse * max_r * 0.04
    for angle, outer in bar_layout(levels, inner, max_r * 0.5):
        level = (outer - inner) / (max_r * 0.5)
        cr.set_source_rgba(*_tint(accent, level), opacity * (0.4 + 0.6 * level))
        cr.set_line_width(max(3.0, max_r * 0.02))
        cr.set_line_cap(1)  # round
        cr.move_to(cx + inner * math.cos(angle), cy + inner * math.sin(angle))
        cr.line_to(cx + min(outer, max_r - 2) * math.cos(angle), cy + min(outer, max_r - 2) * math.sin(angle))
        cr.stroke()
    cr.set_source_rgba(*_tint(accent, 0.3), opacity * 0.5)
    cr.set_line_width(1.0)
    cr.new_sub_path()
    cr.arc(cx, cy, inner - 6, 0, 2 * math.pi)
    cr.stroke()


def draw_wave(cr, cx, cy, max_r, levels, pulse, accent, opacity, state):
    state["phase"] = state.get("phase", 0.0) + 0.05 + 0.1 * pulse
    for layer, (base_f, amp_f, alpha) in enumerate(((0.62, 0.28, 1.0), (0.5, 0.2, 0.6), (0.38, 0.14, 0.35))):
        pts = wave_points(levels, max_r * base_f + pulse * max_r * 0.03, max_r * amp_f,
                          state["phase"] * (1 + layer * 0.4))
        cr.set_source_rgba(*_tint(accent, float(np.mean(levels)) if len(levels) else 0),
                           opacity * alpha * (0.5 + 0.5 * float(np.max(levels)) if len(levels) else 0.5))
        cr.set_line_width(1.5 + 1.5 * pulse)
        cr.new_sub_path()
        for i, (x, y) in enumerate(pts):
            (cr.move_to if i == 0 else cr.line_to)(cx + x, cy + y)
        cr.close_path()
        cr.stroke()


def draw_particles(cr, cx, cy, max_r, levels, pulse, accent, opacity, state):
    field = state.setdefault("particles", ParticleField())
    last = state.get("last_pulse", 0.0)
    beat = pulse > last + 0.3
    state["last_pulse"] = pulse
    field.step(dt=1 / 30, pulse=pulse, level=float(np.mean(levels)) if len(levels) else 0.0, beat=beat)
    for p in field.particles:
        r = min(p.r * max_r, max_r - 2)
        fade = min(1.0, p.life)
        cr.set_source_rgba(*_tint(accent, fade), opacity * 2.2 * fade)
        cr.arc(cx + r * math.cos(p.angle), cy + r * math.sin(p.angle), p.size, 0, 2 * math.pi)
        cr.fill()
    cr.set_source_rgba(*_tint(accent, pulse), opacity * (0.5 + 0.5 * pulse))
    cr.set_line_width(1.0 + 2.0 * pulse)
    cr.new_sub_path()
    cr.arc(cx, cy, max_r * (0.2 + 0.05 * pulse), 0, 2 * math.pi)
    cr.stroke()


DRAWERS = {"rings": draw_rings, "bars": draw_bars, "wave": draw_wave, "particles": draw_particles}
