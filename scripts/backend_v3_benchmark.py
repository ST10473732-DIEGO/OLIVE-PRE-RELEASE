"""Explicit live benchmark; never downloads or promotes models."""
import argparse
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.evaluation.backend_benchmark import run

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--models', nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--split', choices=['development', 'held_out'], default='development')
    p.add_argument('--trials', type=int, default=3)
    p.add_argument('--case-limit', type=int)
    p.add_argument('--context', type=int, default=4096)
    p.add_argument('--num-predict', type=int, default=512)
    p.add_argument('--num-gpu', type=int)
    a = vars(p.parse_args())
    asyncio.run(run(**a))
