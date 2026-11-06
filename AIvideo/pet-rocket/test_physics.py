import json
import math
import unittest

from simulate import ROOT, GAMMA, R, gas_nozzle, integrate, design_values


class PhysicsTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "scenario.json").read_text())
        self.design = design_values()

    def test_no_discharge_below_ambient(self):
        self.assertEqual(gas_nozzle(100000, 293.15, 101325, 1e-4)[:3], (0, 0, 0))

    def test_choking_boundary_is_continuous(self):
        critical = (2 / (GAMMA + 1)) ** (GAMMA / (GAMMA - 1))
        pressure = 101325 / critical
        lower = gas_nozzle(pressure * (1 - 1e-7), 250, 101325, 1e-4)
        upper = gas_nozzle(pressure * (1 + 1e-7), 250, 101325, 1e-4)
        self.assertLess(abs(lower[0]-upper[0])/upper[0], 1e-6)
        self.assertLess(abs(lower[1]-upper[1])/upper[1], 1e-6)

    def test_mass_and_phase_continuity(self):
        result = integrate(self.config, self.design)
        data = result["data"]
        self.assertAlmostEqual(result["integrated_water_out_kg"], result["initial_water_mass_kg"], places=8)
        self.assertAlmostEqual(result["integrated_air_out_kg"], result["initial_air_mass_kg"]-result["final_air_mass_kg"], places=8)
        self.assertLess(abs(data[-1,2]), 1e-7)
        self.assertLess(abs(data[-1,6]-self.config["ambient_pressure_pa"]), 0.1)
        self.assertLess(data[-1,7], self.config["temperature_k"])
        self.assertEqual(self.design["fin_count"], 3)

    def test_vacuum_coast_obeys_ballistic_apogee(self):
        result = integrate(self.config, self.design, drag_override=0)
        data = result["data"]
        end = result["phase_ends"]["air"]
        row = data[abs(data[:,0]-end).argmin()]
        expected = row[1] + row[2]**2/(2*9.80665)
        self.assertAlmostEqual(result["apogee_m"], expected, places=6)


if __name__ == "__main__":
    unittest.main()
