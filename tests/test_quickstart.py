"""Run the examples/quickstart script against the in-process mock."""

from __future__ import annotations

import asyncio

from examples.quickstart.run import main, parse_args, run_quickstart


def test_quickstart_yes_against_mock(capsys) -> None:
    code = main(["--yes", "--prompt", "A sunrise over the sea"])
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "Job succeeded" in captured.out
    assert "play_url:" in captured.out
    assert "actual_credits:" in captured.out


def test_quickstart_declines_without_yes(capsys) -> None:
    args = parse_args(["--prompt", "A sunrise over the sea"])
    code = asyncio.run(run_quickstart(args, input_fn=lambda _: "n"))
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "Not confirmed" in captured.out
    assert "Job succeeded" not in captured.out
