from handmouse.filter import OneEuroFilter, Point2DFilter

DT = 1.0 / 60.0


def test_first_sample_returns_input():
    f = OneEuroFilter(1.0, 0.0, 1.0)
    assert f.filter(0.5, 0.0) == 0.5


def test_lowpass_does_not_jump_to_target_on_first_move():
    f = OneEuroFilter(1.0, 0.0, 1.0)
    f.filter(0.0, 0.0)
    y = f.filter(1.0, DT)
    assert 0.0 < y < 1.0  # passa-baixa atenua o degrau


def test_constant_signal_converges():
    f = OneEuroFilter(1.0, 0.0, 1.0)
    f.filter(0.0, 0.0)
    out, t = 0.0, DT
    for _ in range(500):
        out = f.filter(1.0, t)
        t += DT
    assert abs(out - 1.0) < 1e-3


def test_reset_clears_state():
    f = OneEuroFilter(1.0, 0.0, 1.0)
    f.filter(0.5, 0.0)
    f.filter(0.7, DT)
    f.reset()
    assert f.filter(0.2, 0.0) == 0.2  # comporta-se como 1a amostra de novo


def test_point2d_first_sample_passthrough():
    p = Point2DFilter(1.0, 0.0, 1.0)
    assert p.filter(0.3, 0.6, 0.0) == (0.3, 0.6)
