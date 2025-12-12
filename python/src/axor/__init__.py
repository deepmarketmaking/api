"""
AXOR API Client Library

Python client for the Deep MM AXOR API providing real-time and historical
corporate bond pricing through AI-powered inference.
"""

from .authentication import create_get_id_token
from .connection import connect, DEFAULT_SERVER
from .cusips_to_figis import openfigi_map_cusips_to_figis
from .fit_johnson_su import (
    fit_johnson_su,
    plot_cdf_of_fitted_johnson_su_distribution,
    plot_pdf_of_fitted_johnson_su_distribution,
)
from .fit_normal_distribution import fit_normal_distribution

__version__ = "0.1.0"
__all__ = [
    # Authentication
    "create_get_id_token",
    # Connection
    "connect",
    "DEFAULT_SERVER",
    # CUSIP/FIGI mapping
    "openfigi_map_cusips_to_figis",
    # Distribution fitting
    "fit_johnson_su",
    "plot_cdf_of_fitted_johnson_su_distribution",
    "plot_pdf_of_fitted_johnson_su_distribution",
    "fit_normal_distribution",
]
