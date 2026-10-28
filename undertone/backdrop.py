"""Backdrop motion: a slow, eased zoom that ping-pongs between 1.0 and max_scale."""
import math


def ken_burns_scale(t, period_s=40.0, max_scale=1.08):
    if max_scale <= 1.0 or period_s <= 0:
        return 1.0
    return 1.0 + (max_scale - 1.0) * (0.5 - 0.5 * math.cos(2 * math.pi * t / period_s))
