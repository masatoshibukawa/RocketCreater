"""Integration tests for rocket simulator

To run these tests:
    python test.py -v
    
Or with specific test:
    python -m pytest test.py::Software::test_1 -v

Or
    python -m unittest test.Software.test_1
"""

import waterRocketSim as wrs

import traceback
import unittest
import sys
import time
from functools import wraps
import json
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
import os
from constants import *
       
class Software(unittest.TestCase):
    """Test utils functions."""
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        pass

    def test_1(self):
        rocket=wrs.WaterRocket(s1_nozzleDiameter = 0.020,
                 s2_nozzleDiameter = 0.007,
                 s1_bottleCount = 1,
                 s2_bottleCount = 2,
                 bottleType = CST_BOTTLE_TYPE_1dot5L,
                 rocket_payloadMass = 0)
        best=rocket.parametersForMaxAltitude(
                                 s1_waterVolumeIni_range=np.arange(0.0005, 0.001, 0.0001),
                                 s2_waterVolumeIni_range=np.arange(0.0005, 0.002, 0.0001),
                                 simulation_step=0.01,
                                 simulation_time=20
                                 )
        print(best)
        flyParameters = rocket.launchSimulation()
        rocket.plot_flight_diagnostics(flyParameters)

        print("\nTest 1: dfsghstfhsfthfgh")
        #self.assertEqual()

def print_test_instructions():
    """Print instructions for running software tests."""
    print("\n" + "="*70)
    print("ROCKET SIMULATOR SOFTWARE TEST SUITE")
    print("="*70)
    print("\nRunning all tests:")
    print("  python test.py -v")
    print("\nRunning specific test class:")
    print("  python -m pytest test.py::Software -v")
    print("\nRunning specific test:")
    print("  python -m pytest test.py::Software::test_1 -v")
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    print_test_instructions()
    unittest.main(verbosity=2)
