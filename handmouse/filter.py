"""One Euro Filter (1D) + Point2DFilter (x,y).

Filtro passa-baixa adaptativo: pouco lag em movimento rapido, muito suave em
repouso. Opera sobre coords normalizadas [0,1]; `t` em segundos.
"""

from __future__ import annotations

import math


def _alpha(cutoff: float, te: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / te)


class OneEuroFilter:
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev: float | None = None
        self._x_hat_prev: float = 0.0
        self._dx_prev: float = 0.0
        self._t_prev: float | None = None

    def filter(self, x: float, t: float) -> float:
        if self._t_prev is None:
            self._x_prev = x
            self._x_hat_prev = x
            self._dx_prev = 0.0
            self._t_prev = t
            return x

        te = max(t - self._t_prev, 1e-6)

        # derivada filtrada
        dx = (x - self._x_prev) / te
        a_d = _alpha(self.d_cutoff, te)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev

        # cutoff adaptativo
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = _alpha(cutoff, te)
        x_hat = a * x + (1.0 - a) * self._x_hat_prev

        self._x_prev = x
        self._dx_prev = dx_hat
        self._x_hat_prev = x_hat
        self._t_prev = t
        return x_hat

    def reset(self) -> None:
        self._x_prev = None
        self._x_hat_prev = 0.0
        self._dx_prev = 0.0
        self._t_prev = None


class Point2DFilter:
    """Dois OneEuroFilter (x,y) com os mesmos parametros e timestamp."""

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float):
        self._fx = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self._fy = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def filter(self, x: float, y: float, t: float) -> tuple[float, float]:
        return self._fx.filter(x, t), self._fy.filter(y, t)

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()
