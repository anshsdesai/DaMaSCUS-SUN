import math
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import srdm_source_grid as grid


class SRDMSourceGridTests(unittest.TestCase):
    def test_production_grid_shape_and_endpoints(self):
        points = grid.all_points()
        self.assertEqual(len(points), 475)
        self.assertAlmostEqual(points[0].mass_mev, 1.0e-2)
        self.assertAlmostEqual(points[-1].mass_mev, 3.0)
        self.assertAlmostEqual(points[0].sigma_e_cm2, 1.0e-42)
        self.assertAlmostEqual(points[-1].sigma_e_cm2, 1.0e-33)
        ratio = grid.sigma_es_cm2()[1] / grid.sigma_es_cm2()[0]
        self.assertAlmostEqual(ratio, math.sqrt(10.0))

    def test_pilot_indices_cover_corners(self):
        self.assertEqual(grid.pilot_indices(), [0, 18, 456, 474])
        self.assertTrue(all(grid.point_by_index(i).is_corner for i in grid.pilot_indices()))

    def test_render_config_replaces_all_markers(self):
        point = grid.point_by_index(0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "point.cfg"
            grid.render_config(
                REPO_ROOT / grid.DEFAULT_TEMPLATE,
                out,
                point,
                sample_size=1234,
                interpolation_points=99,
            )
            text = out.read_text(encoding="utf-8")
        self.assertNotIn("__", text)
        self.assertIn(point.run_id, text)
        self.assertIn("sample_size", text)
        self.assertIn("1234", text)
        self.assertIn("DM_cross_section_electron", text)
        self.assertIn("SHM_v0\t\t=\t238.0", text)
        self.assertIn("SHM_vObserver\t=\t(11.1, 250.2, 7.3)", text)

    def test_flux_summary_and_reference_eta(self):
        point = grid.GridPoint(index=0, mass_mev=1.0, sigma_e_cm2=1.0e-36)
        with tempfile.TemporaryDirectory() as tmp:
            flux = Path(tmp) / "flux.txt"
            eta = Path(tmp) / "eta.txt"
            flux.write_text(
                "0\t1\n100\t10\n200\t5\n400\t0\n",
                encoding="utf-8",
            )
            summary = grid.source_flux_summary(flux, point.mass_mev)
            eta_summary = grid.write_reference_eta_diagnostic(
                flux,
                eta,
                point.mass_mev,
                rho_ref_gev_cm3=0.3,
            )
            rows = [
                tuple(float(x) for x in line.split())
                for line in eta.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        self.assertGreater(summary["total_flux_cm^-2_s^-1"], 0.0)
        self.assertEqual(summary["dropped_nonpositive_speed_rows"], 1)
        self.assertEqual(rows[0][0], 0.0)
        self.assertTrue(all(a[1] >= b[1] for a, b in zip(rows, rows[1:])))
        self.assertIn("n_ref_cm^-3", eta_summary)

    def test_manifest_entries_are_unique(self):
        entries = grid.manifest_entries(REPO_ROOT, grid.DEFAULT_RESULTS_ROOT)
        self.assertEqual(len(entries), 475)
        self.assertEqual(len({entry["index"] for entry in entries}), 475)
        self.assertEqual(len({entry["run_id"] for entry in entries}), 475)


if __name__ == "__main__":
    unittest.main()
