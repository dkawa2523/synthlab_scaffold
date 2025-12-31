from __future__ import annotations

from math import sqrt, tau
from typing import Iterable


def wrap_angle_rad(angle: float | None) -> float | None:
    if angle is None:
        return None
    value = float(angle) % tau
    if value < 0.0:
        value += tau
    return value


def angular_distance_rad(a: float, b: float) -> float:
    diff = abs((a - b) % tau)
    return min(diff, tau - diff)


def quantile(values: Iterable[float], q: float) -> float | None:
    data = sorted(float(v) for v in values)
    if not data:
        return None
    if q <= 0.0:
        return data[0]
    if q >= 1.0:
        return data[-1]
    pos = q * (len(data) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(data) - 1)
    if lo == hi:
        return data[lo]
    frac = pos - lo
    return data[lo] + (data[hi] - data[lo]) * frac


def mean(values: Iterable[float]) -> float | None:
    total = 0.0
    count = 0
    for value in values:
        total += float(value)
        count += 1
    if count == 0:
        return None
    return total / count


def std(values: Iterable[float], *, mean_value: float | None = None) -> float | None:
    data = [float(v) for v in values]
    if not data:
        return None
    if mean_value is None:
        mean_value = mean(data)
    if mean_value is None:
        return None
    var = sum((v - mean_value) ** 2 for v in data) / len(data)
    return sqrt(var)
