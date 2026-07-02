import logging
import os

logger = logging.getLogger("amazon_spapi.config")

try:
    from ConfigParser import ConfigParser, RawConfigParser
except ImportError:
    from configparser import ConfigParser, NoOptionError, RawConfigParser


class ConfigLoader(object):
    def load(self):
        raise NotImplementedError()


class IniConfigLoader(ConfigLoader):
    section = ""
    config = None

    def __init__(self, config_path, interpolation=True):
        self.config_path = os.path.abspath(os.path.expanduser(config_path))
        self.interpolation = interpolation

        if not os.path.isfile(self.config_path):
            raise ValueError(
                "Could not find configuration file - {}".format(config_path)
            )

        if interpolation:
            self.config = RawConfigParser()
        else:
            self.config = RawConfigParser(interpolation=None)
        self.config.read(config_path)

    def set_section(self, section):
        self.section = section

    def get(self, key):
        if self.section:
            try:
                return self.config.get(self.section, key)
            except NoOptionError:
                message_info = [
                    self.section,
                    str(key),
                    "ConfigTool.error",
                    "no_key",
                ]
                logger.error("|".join(message_info))
                return None
        else:
            return None

    def get_all_dict(self):
        configs = {}
        lists = self.config.items(self.section)
        for item in lists:
            configs[item[0]] = item[1]

        return configs

    def get_all(self):
        return self.config.items(self.section)

    def get_section_key(self, section, key):
        return self.config.get(section, key)

    def get_section_all(self, section):
        return self.config.items(section)

    def load(self):
        config = dict()
        if self.interpolation:
            cp = ConfigParser()
        else:
            cp = ConfigParser(interpolation=None)
        cp.read(self.config_path)
        for section in cp.sections():
            config[section] = dict()
            for opt, val in cp.items(section):
                config[section][opt] = val

        return config
