The simulator
=============

The rocket simulator is composed of several tools that calculate the state of the rocket
throughout the flight. This is useful to adjust rocket design (nozzle diameter, number of
bottles, etc.) and launch parameters (water volume, air pressure, ...).

Get started
-----------
1. Download the rocket simulator folder.
2. Open a command prompt and navigate to the folder.
3. Create a virtual environment and install dependencies.

.. code-block:: bash

    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate.bat
    pip install -r requirements.txt

4. Start Python and create a rocket object.

.. code-block:: python

    from waterRocketSim import WaterRocket
    rocket = WaterRocket()




API reference
-------------

The documentation below is generated automatically from the docstrings in the simulator module.

.. currentmodule:: waterRocketSim

.. automodule:: waterRocketSim
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: WaterRocket
   :members:
   :undoc-members:
   :show-inheritance:

