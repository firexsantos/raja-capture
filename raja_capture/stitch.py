"""Vertical image stitching for scrolling capture.

Frames are consecutive captures of the same screen region while content scrolls
downwards. Static rows at the top/bottom (sticky headers/footers) are detected
per frame pair so they appear only once in the result.
"""

from __future__ import annotations

import numpy as np


def _gray(a: np.ndarray, col_step: int) -> np.ndarray:
    a = a[:, ::col_step].astype(np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def static_rows(a: np.ndarray, b: np.ndarray, tol: int = 6) -> tuple[int, int]:
    """Number of identical rows at the top and bottom of two same-size frames."""
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2).max(axis=1)
    same = diff <= tol
    h = len(same)
    if same.all():
        return h, 0
    top = int(np.argmin(same))  # index of first differing row
    bottom = int(np.argmin(same[::-1]))
    return top, bottom


def find_shift(a: np.ndarray, b: np.ndarray, max_err: float = 10.0) -> int | None:
    """How many pixels content moved up from frame ``a`` to frame ``b``.

    Returns None when no reliable match is found.
    """
    h, w = a.shape[:2]
    if h < 16:
        return None
    step = max(1, w // 320)
    ga, gb = _gray(a, step), _gray(b, step)
    k = int(max(8, min(h // 4, 120)))

    # Choose the most textured block in the upper half of b as template, so
    # blank areas don't produce ambiguous matches.
    best_t, best_std = 0, -1.0
    for t in range(0, max(1, h // 2 - k + 1), max(1, k // 3)):
        s = float(gb[t : t + k].std())
        if s > best_std:
            best_t, best_std = t, s
    if best_std < 1.5:
        return None
    t = best_t
    tmpl = gb[t : t + k]

    errs = np.full(h - k + 1, np.inf, dtype=np.float32)
    for y in range(t, h - k + 1):  # content moves up -> match lies at or below t in a
        errs[y] = np.abs(ga[y : y + k] - tmpl).mean()
    y_best = int(np.argmin(errs))
    if not np.isfinite(errs[y_best]) or errs[y_best] > max_err:
        return None
    return y_best - t


class Stitcher:
    def __init__(self):
        self.strips: list[np.ndarray] = []
        self.first: np.ndarray | None = None
        self.last: np.ndarray | None = None
        self.footer: np.ndarray | None = None
        self.end_row = 0  # row in `last` where the stitched body currently ends
        self.frames = 0
        self.misses = 0

    @property
    def height(self) -> int:
        body = sum(s.shape[0] for s in self.strips) if self.strips else (
            self.first.shape[0] if self.first is not None else 0)
        return body + (self.footer.shape[0] if self.footer is not None else 0)

    def add(self, frame: np.ndarray) -> str:
        """Add a frame. Returns 'added', 'same' (no movement) or 'nomatch'."""
        if self.first is None:
            self.first = self.last = frame
            self.end_row = frame.shape[0]
            self.frames = 1
            return "added"
        last = self.last
        if frame.shape != last.shape:
            return "nomatch"
        h = frame.shape[0]
        top, bottom = static_rows(last, frame)
        if top >= h or top + bottom >= h - 8:
            return "same"
        body_a = last[top : h - bottom]
        body_b = frame[top : h - bottom]
        shift = find_shift(body_a, body_b)
        if shift is None:
            self.misses += 1
            return "nomatch"
        if shift <= 0:
            return "same"

        if not self.strips:
            # First real movement: we now know the footer height.
            self.strips.append(self.first[: h - bottom])
            self.end_row = h - bottom
        start = self.end_row - shift
        stop = h - bottom
        if start < top:  # moved further than the overlap; keep what we can
            start = top
        if stop > start:
            self.strips.append(frame[start:stop])
        self.footer = frame[h - bottom :] if bottom else None
        self.end_row = stop
        self.last = frame
        self.frames += 1
        return "added"

    def result(self) -> np.ndarray | None:
        if self.first is None:
            return None
        if not self.strips:
            return self.first
        parts = list(self.strips)
        if self.footer is not None and self.footer.shape[0]:
            parts.append(self.footer)
        return np.vstack(parts)
