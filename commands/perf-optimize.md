---
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent
description: Profile application performance and systematically optimize bottlenecks
argument-hint: [target module or function (optional)]
---

# Perf Optimize

Optimize application performance using `/fix-loop` for the iterative cycle
and `/hypothesis-lab` for parallel strategy testing.

## How to use

Follow the `/fix-loop` workflow (measure → classify → fix → verify → repeat).
This command adds performance-specific guidance for each phase. When multiple
optimization strategies are viable for a bottleneck, use `/hypothesis-lab` to
test them in parallel worktree subagents.

**Quick reference** — the fix-loop cycle:
1. Baseline → 2. Classify → 3. Fix (reproduce → diagnose → fix → verify → log) → 4. Summary

## Phase 1: Profiling target

Pick a representative target (ask user if unclear):

- **Full test suite**: run all tests/benchmarks with timing
- **Specific module**: run targeted tests for the module in question
- **Specific function**: use cProfile or `time.perf_counter` instrumentation

Record: total wall time, per-phase breakdown, per-function hot spots.

### Python profiling example

```python
import cProfile, pstats

cProfile.run('your_function()', '/tmp/profile_output')
s = pstats.Stats('/tmp/profile_output')
s.sort_stats('cumulative')
s.print_stats(20)
```

### Node.js profiling example

```bash
node --prof app.js
node --prof-process isolate-*.log > profile.txt
```

## Phase 2: Bottleneck identification

Find the **single biggest time consumer**:

1. **Phase-level**: Which phase/module dominates?
2. **Function-level**: Profile the dominant phase to find hot functions
3. **Call count**: High call counts with moderate per-call time often outweigh
   low-count expensive calls. Look for both.
4. **Reference comparison**: Research how well-known libraries implement the same
   functionality — algorithm, data structure, complexity — to inform the
   optimization direction.

## Phase 3: Optimization strategies

Choose the simplest that works:

- **Vectorization**: Replace Python loops with NumPy/pandas batch operations
- **Caching**: `functools.lru_cache` or manual memoization for repeated computations
- **Lazy loading**: Defer imports or computations until actually needed
- **Algorithmic**: Better data structures, spatial indexing, early exit conditions
- **Reduce allocations**: Reuse arrays/buffers, avoid unnecessary copies
- **Concurrency**: Parallelize I/O-bound work (asyncio, threading) or CPU-bound work (multiprocessing)
- **Native acceleration**: For compute-heavy operations, consider Cython, Numba, or Rust bindings
- **GPU acceleration**: For parallelizable compute-heavy ops, consider CuPy, Numba CUDA,
  or PyTorch. Only when the bottleneck is parallelizable and data volume justifies
  transfer overhead

### Reference library comparison

Before optimizing, research how established libraries solve the same problem.
Look for algorithmic patterns worth borrowing:
- Spatial indexing (BVH, R-tree, k-d tree)
- Adaptive discretization / level-of-detail
- Incremental / streaming algorithms
- Tolerance-based early rejection

Borrow algorithmic ideas but adapt for your stack: e.g. NumPy vectorization over
per-element loops in Python, or batch processing over individual calls in Node.js.

### Parallel strategy testing

When multiple strategies seem viable, use `/hypothesis-lab` to test them in parallel
worktree subagents. Each subagent implements one strategy, runs targeted benchmarks,
and reports speedup. Merge the best result.

## Summary report format

```
## Performance Optimization Summary

**Target:** [what was profiled]
**Baseline:** X.XXs total
**Final:** Y.YYs total (Z.Zx speedup)

| Cycle | Bottleneck | Technique | Files | Before | After | Speedup |
|-------|-----------|-----------|-------|--------|-------|---------|
| 1     | ...       | ...       | ...   | ...    | ...   | ...     |

**Cumulative speedup: Z.Zx**
```

## Important notes

- Profile before optimizing — intuition about bottlenecks is often wrong
- One optimization per cycle — don't bundle, or you can't attribute speedups
- **Never sacrifice correctness for speed** — test suite must stay green
- Measure before and after every change to quantify actual improvement
