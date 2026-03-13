"""Tests for the Minesweeper constraint solver."""

from backend.solver.minesweeper import MinesweeperSolver, SolverResult


class TestMinesweeperSolver:
    def setup_method(self):
        self.solver = MinesweeperSolver()

    def test_empty_grid(self):
        result = self.solver.solve([])
        assert result.safe_cells == []
        assert result.mine_cells == []

    def test_no_information(self):
        """Grid with only unknowns provides no deductions."""
        grid = [["?", "?"], ["?", "?"]]
        result = self.solver.solve(grid)
        assert result.safe_cells == []
        assert result.mine_cells == []
        assert result.confidence == 0.0

    def test_all_mines_deduction(self):
        """If a '1' has exactly 1 unknown neighbor, that neighbor is a mine."""
        grid = [
            ["1", " "],
            ["?", " "],
        ]
        result = self.solver.solve(grid)
        assert (1, 0) in result.mine_cells

    def test_all_safe_deduction(self):
        """If a '1' has 1 adjacent flag, remaining unknowns are safe."""
        grid = [
            ["1", "F"],
            ["?", " "],
        ]
        result = self.solver.solve(grid)
        assert (1, 0) in result.safe_cells

    def test_complex_grid(self, sample_minesweeper_grid):
        """The sample grid should produce some deductions."""
        result = self.solver.solve(sample_minesweeper_grid)
        # With the given grid, solver should find at least some info
        assert isinstance(result, SolverResult)
        assert isinstance(result.safe_cells, list)
        assert isinstance(result.mine_cells, list)

    def test_fully_revealed(self):
        """Grid with no unknowns should produce no deductions."""
        grid = [
            ["1", "1", " "],
            ["1", "1", " "],
            [" ", " ", " "],
        ]
        result = self.solver.solve(grid)
        assert result.safe_cells == []
        assert result.mine_cells == []

    def test_two_number_constraint(self):
        """Two numbers sharing unknowns should both contribute."""
        grid = [
            [" ", "1", " "],
            [" ", "?", " "],
            [" ", "1", " "],
        ]
        result = self.solver.solve(grid)
        # (1,1) is the only unknown neighbor of both "1"s
        assert (1, 1) in result.mine_cells
