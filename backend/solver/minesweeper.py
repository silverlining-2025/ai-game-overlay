"""Constraint-based Minesweeper solver."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SolverResult:
    """Result of solving the current grid state."""
    safe_cells: list[tuple[int, int]] = field(default_factory=list)
    mine_cells: list[tuple[int, int]] = field(default_factory=list)
    confidence: float = 0.0


class MinesweeperSolver:
    """Simple constraint-based Minesweeper solver.

    For each revealed number N:
    - If adjacent unknowns == N - adjacent flags → all unknowns are mines
    - If adjacent flags == N → all adjacent unknowns are safe
    """

    NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    def solve(self, grid: list[list[str]]) -> SolverResult:
        """Analyze grid and return safe/mine cells."""
        if not grid or not grid[0]:
            return SolverResult()

        rows = len(grid)
        cols = len(grid[0])
        safe: set[tuple[int, int]] = set()
        mines: set[tuple[int, int]] = set()

        for r in range(rows):
            for c in range(cols):
                cell = grid[r][c]
                if not cell.isdigit() or cell == "0":
                    continue

                number = int(cell)
                unknowns: list[tuple[int, int]] = []
                flags = 0

                for dr, dc in self.NEIGHBORS:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols:
                        neighbor = grid[nr][nc]
                        if neighbor == "?":
                            unknowns.append((nr, nc))
                        elif neighbor == "F":
                            flags += 1

                # All unknowns are mines
                if len(unknowns) == number - flags and len(unknowns) > 0:
                    mines.update(unknowns)

                # All unknowns are safe
                if flags == number and len(unknowns) > 0:
                    safe.update(unknowns)

        # Remove contradictions (if a cell appears in both, drop it)
        contradictions = safe & mines
        safe -= contradictions
        mines -= contradictions

        total_deductions = len(safe) + len(mines)
        confidence = 1.0 if total_deductions > 0 else 0.0

        return SolverResult(
            safe_cells=sorted(safe),
            mine_cells=sorted(mines),
            confidence=confidence,
        )
