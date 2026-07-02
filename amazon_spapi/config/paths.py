# -*- coding: utf-8 -*-
"""Default paths for config and logs."""

import os

DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".amazon_spapi")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_HOME, "config.ini")
DEFAULT_LOG_DIR = os.path.join(DEFAULT_HOME, "logs")

CONFIG_ENV_VAR = "AMAZON_SPAPI_CONFIG_PATH"
LEGACY_EVERYMARKET_CONFIG_ENV_VAR = "EVERYMARKET_CONFIG_PATH"
LEGACY_CONFIG_ENV_VAR = "EM_WORKERS_CONFIG_PATH"
LEGACY_MWS_CONFIG_ENV_VAR = "MWS_COLLECTOR_CONFIGURATION_PATH"
