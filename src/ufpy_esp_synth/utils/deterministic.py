from __future__ import annotations


def _triangle(u: float) -> float:
    """
    Triangular wave in [0..1] with period 1:
      u=0 -> 0
      u=0.5 -> 1
      u=1 -> 0
    """
    u = u % 1.0
    return 1.0 - abs(2.0 * u - 1.0)


def make_q_profile(
    n_points: int,
    q_min: float,
    q_max: float,
    run_id: int,
    total_runs: int,
) -> list[float]:
    """
    Deterministic (no randomness) q_liq profile derived only from:
      - pump DB range (q_min/q_max)
      - run_id and total_runs (phase shift)

    This ensures:
      - reproducibility
      - different files differ deterministically (phase shift)
    """
    if n_points < 1:
        raise ValueError("n_points must be >= 1")
    if q_min < 0 or q_max < 0:
        raise ValueError("q_min/q_max must be >= 0")
    if q_max < q_min:
        q_min, q_max = q_max, q_min

    span = q_max - q_min
    if total_runs <= 0:
        phase = 0.0
    else:
        # phase in [0,1)
        phase = (run_id % total_runs) / float(total_runs)

    if n_points == 1:
        return [q_min + span * _triangle(phase)]

    prof: list[float] = []
    for i in range(n_points):
        u = phase + (i / float(n_points - 1))
        prof.append(q_min + span * _triangle(u))
    return prof
