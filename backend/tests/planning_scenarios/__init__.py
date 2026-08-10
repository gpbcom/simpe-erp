"""Reusable planning instances for exercising the solver directly.

Notes:
    The package exists because two solver budgets were sized this session
    against instances invented alongside the measurement, and both were wrong
    in ways that looked plausible. One gave every visit a 09:00-20:00 window
    and was pathologically hard; the next was over-constrained and left 28 of
    95 visits unplaceable. A budget tuned against either is tuned against a
    problem the agency does not have.

    So the instances live here, are built from the seeded agency's own service
    windows and addresses, and are shared by the correctness catalogue and the
    performance workload alike.
"""
