# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys


# Get the project root dir, which is the parent dir of this
cwd = os.getcwd()
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
simulator_dir = os.path.join(project_root, "B-Rocket_Simulator")

# Insert the project root dir and the simulator package directory into the
# PYTHONPATH so autodoc can import the module reliably.
sys.path.insert(0, project_root)
sys.path.insert(0, simulator_dir)
#from 2-Rocket_Simulator import __version__, __author__, __project__


# Import version from package
release = '1.0'#__version__
version='1.0'#__version__
project = 'Water Rocket Toolbox'#__project__
author = 'Benoit CASTETS'#__author__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.todo',
    'sphinx.ext.viewcode',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.duration',
    'sphinx.ext.napoleon',  # Support Google/NumPy docstring styles
    "sphinxcontrib.youtube",
]

# Autodoc configuration
autodoc_default_options = {
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
}
autodoc_typehints = 'description'
autodoc_typehints_format = 'short'

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# build even without optional runtime dependencies
autodoc_mock_imports = ["pandas", "numpy", "pygame", "pynput", "pyautogui", "matplotlib" ]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

"""
Tells the project to use sphinx pygments for color coding code examples.
"""

pygments_style = 'sphinx'

# Do not prepend module name to functions/classes in the TOC/sidebar
#add_module_names = False