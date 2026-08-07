"""Split the campaign's suites into balanced shards, and write the arg files.

The campaign is thirty suites of wildly different weight — the auth suite is
five seconds, the account form is over a minute — so splitting by *count* wastes
most of the parallelism. This packs by measured duration instead.

Run it after any full campaign, from the repository root::

    python qa/shards/balance.py qa/results/output.xml

With no argument it re-reads whatever durations it last recorded in
``qa/shards/durations.json``, and falls back to a source-size proxy for suites
it has never seen run. The proxy is *bad* — suite 05 is 1.6 kB of source and
thirty-seven seconds of broker round trips — so it exists only to get a first
partition off the ground. Re-run this against a real ``output.xml`` and commit
the result.

Notes:
    **Placement is unconstrained.** It did not use to be: 08, 09 and 17 read a
    planning that only suite 19 creates, and Robot runs a directory's suites in
    name order, so no arrangement could have put 19 first. That is now fixed at
    the source — ``Ensure A Planning Has Been Computed`` in
    ``api_keywords.resource`` — and every suite stands alone, so this is a plain
    bin-packing problem.

    The **cross-suite collision matrix does not constrain it either**, because
    each shard is expected to run against its own stack: its own API, database,
    broker and mail catcher. On a shared stack the matrix would dominate — the
    group contending for the seeded assistant alone is larger than a balanced
    quarter of the campaign — which is exactly why sharding a shared stack tops
    out around 2x however many workers you give it.

    ``99_coverage_report`` is in no shard. It reads what every other suite
    recorded, so it runs once, after the shards, over their merged raw output.
"""

from __future__ import annotations

# Standard library imports
import json
from pathlib import Path
import sys
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET

QA_ROOT = Path(__file__).resolve().parent
SUITES = QA_ROOT.parent / "robot" / "suites"
DURATIONS = QA_ROOT / "durations.json"

#: The suite that merges coverage. It belongs to no shard.
JOIN_SUITE = "99_coverage_report"

#: Shard counts to generate argument files for.
FANOUTS = (2, 3, 4)

#: Seconds per byte of suite source, used only for suites never yet measured.
#: Derived from the suites that have been: it is a poor predictor and is meant
#: to be replaced by real numbers on the first sharded run.
SECONDS_PER_BYTE = 0.00393


def suite_names() -> List[str]:
    """Return every shardable suite, in file order.

    Returns:
        List[str]: Suite stems, excluding the coverage join.
    """
    return sorted(
        path.stem
        for path in SUITES.glob("[0-9]*.robot")
        if path.stem != JOIN_SUITE
    )


def measured(output_xml: Path) -> Dict[str, float]:
    """Read per-suite elapsed seconds out of a Robot output file.

    Args:
        output_xml (Path): A completed run's ``output.xml``.

    Returns:
        Dict[str, float]: Seconds per suite stem, for the suites it contains.

    Notes:
        Robot 7 writes ``elapsed`` in seconds on each ``<status>``. A run that
        was interrupted leaves the file unparseable, so this returns what it can
        and the caller falls back for the rest.
    """
    try:
        root = ET.parse(output_xml).getroot()
    except ET.ParseError:
        print(f"  {output_xml} is truncated; falling back to the proxy.")
        return {}
    found: Dict[str, float] = {}
    for suite in root.iter("suite"):
        source = suite.get("source") or ""
        status = suite.find("status")
        if source.endswith(".robot") and status is not None and status.get("elapsed"):
            found[Path(source).stem] = float(status.get("elapsed"))
    return found


def durations(output_xml: Path | None) -> Dict[str, float]:
    """Return the best duration estimate available for every suite.

    Args:
        output_xml (Path | None): A run to read, or ``None`` to reuse the
            recorded ones.

    Returns:
        Dict[str, float]: Seconds per suite stem, for every shardable suite.
    """
    recorded: Dict[str, float] = {}
    if DURATIONS.exists():
        recorded = json.loads(DURATIONS.read_text())
    if output_xml is not None:
        recorded.update(measured(output_xml))
        DURATIONS.write_text(json.dumps(dict(sorted(recorded.items())), indent=2) + "\n")

    estimates: Dict[str, float] = {}
    for name in suite_names():
        if name in recorded:
            estimates[name] = recorded[name]
        else:
            size = (SUITES / f"{name}.robot").stat().st_size
            estimates[name] = round(size * SECONDS_PER_BYTE, 1)
    return estimates


def pack(estimates: Dict[str, float], fanout: int) -> List[List[str]]:
    """Distribute suites across shards, longest first.

    Args:
        estimates (Dict[str, float]): Seconds per suite.
        fanout (int): How many shards to fill.

    Returns:
        List[List[str]]: The suites in each shard.

    Notes:
        Longest-processing-time first: repeatedly put the heaviest remaining
        suite in the lightest shard. It is the standard greedy heuristic and is
        provably within 4/3 of optimal, which is far closer than the input
        estimates are.
    """
    shards: List[List[str]] = [[] for _ in range(fanout)]
    loads = [0.0] * fanout
    for name, seconds in sorted(estimates.items(), key=lambda e: -e[1]):
        lightest = loads.index(min(loads))
        shards[lightest].append(name)
        loads[lightest] += seconds
    return [sorted(shard) for shard in shards]


def write(shards: List[List[str]], estimates: Dict[str, float], fanout: int) -> None:
    """Write one Robot argument file per shard.

    Args:
        shards (List[List[str]]): The suites in each shard.
        estimates (Dict[str, float]): Seconds per suite, for the header.
        fanout (int): How many shards there are.
    """
    directory = QA_ROOT / str(fanout)
    directory.mkdir(parents=True, exist_ok=True)
    for index, suites in enumerate(shards, start=1):
        total = sum(estimates[name] for name in suites)
        lines = [
            f"# Shard {index} of {fanout} — about {total:.0f}s.",
            "#",
            "# GENERATED by qa/shards/balance.py. Re-run it after a full",
            "# campaign to re-balance against real durations:",
            "#",
            "#     python qa/shards/balance.py qa/results/output.xml",
            "#",
            "# Used as:",
            "#",
            f"#     robot --argumentfile qa/shards/{fanout}/{index}.args \\",
            "#           --outputdir qa/results qa/robot/suites",
            "",
        ]
        lines += [f"--suite {name}" for name in suites]
        (directory / f"{index}.args").write_text("\n".join(lines) + "\n")


def check() -> int:
    """Verify the committed argument files still cover every suite exactly once.

    Returns:
        int: 0 when every fan-out is a true partition, 1 otherwise.

    Notes:
        **This is the control that matters.** Robot does *not* fail when a
        ``--suite`` pattern matches nothing while others match — so renaming a
        suite file, or adding one and forgetting the shard lists, silently
        shrinks the campaign. Every shard stays green and coverage quietly
        drops. Nobody notices for months.

        Run in CI on every push. It needs no stack, no browser and no Python
        dependencies beyond the standard library.
    """
    expected = set(suite_names())
    failed = False
    for fanout in FANOUTS:
        assigned: List[str] = []
        for index in range(1, fanout + 1):
            path = QA_ROOT / str(fanout) / f"{index}.args"
            if not path.exists():
                print(f"MISSING {path}")
                failed = True
                continue
            assigned += [
                line.split(maxsplit=1)[1].strip()
                for line in path.read_text().splitlines()
                if line.startswith("--suite ")
            ]
        missing = expected - set(assigned)
        unknown = set(assigned) - expected
        duplicated = {name for name in assigned if assigned.count(name) > 1}
        if missing or unknown or duplicated:
            failed = True
            print(f"{fanout} shards: NOT a partition of the campaign")
            if missing:
                print(f"    in no shard:      {' '.join(sorted(missing))}")
            if unknown:
                print(f"    no such suite:    {' '.join(sorted(unknown))}")
            if duplicated:
                print(f"    in two shards:    {' '.join(sorted(duplicated))}")
        else:
            print(f"{fanout} shards: every one of {len(expected)} suites, exactly once")
    return 1 if failed else 0


def main() -> int:
    """Generate every fan-out's argument files, or check the committed ones.

    Returns:
        int: Process exit status.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        return check()
    output_xml = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    estimates = durations(output_xml)
    names = suite_names()
    print(f"{len(names)} shardable suites, {sum(estimates.values()):.0f}s total\n")
    for fanout in FANOUTS:
        shards = pack(estimates, fanout)
        write(shards, estimates, fanout)
        loads: List[Tuple[int, float]] = [
            (index, sum(estimates[name] for name in shard))
            for index, shard in enumerate(shards, start=1)
        ]
        slowest = max(load for _, load in loads)
        print(f"  {fanout} shards -> slowest {slowest:.0f}s "
              f"(speedup {sum(estimates.values()) / slowest:.2f}x)")
        for index, load in loads:
            print(f"      {index}: {load:6.0f}s  {' '.join(shards[index - 1])}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
