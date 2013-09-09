
#!/usr/bin/python

"""
repacked - dead simple package creation
"""

from pkg_resources import resource_string
from yapsy.PluginManager import PluginManager

__author__ = "Jonathan Prior and fixes by Adam Hamsik"
__copyright__ = "Copyright 2011, 736 Computing Services Limited"
__license__ = "LGPL"
__version__ = "110"
__maintainer__ = "Adam Hamsik"
__email__ = "adam.hamsik@chillisys.com"

import optparse
import yaml
import os
import sys
import tempfile
import distutils.dir_util
import shutil
import logging
import subprocess

logger = logging.getLogger()

class Configuration:
    def __init__(self):
        self.preserve_symlinks=False
        self.preserve_permissions=True
        self.output_dir=None
        self.dist_directory=None
        self.update_dist_hook=None
        self.release_hook=None
        self.build_pkg_hook=None
        self.build_pkg_hook_args=""
        
plugin_dir = os.path.expanduser("~/.repacked/plugins")

if not os.path.exists(plugin_dir):
    plugin_dir = os.path.join(os.path.dirname(__file__),'../../repacked/plugins')

pkg_plugins = {}

pluginMgr = PluginManager(plugin_info_ext="plugin")
pluginMgr.setPluginPlaces([plugin_dir])
pluginMgr.locatePlugins()
pluginMgr.loadPlugins()

for pluginInfo in pluginMgr.getAllPlugins():
   pluginMgr.activatePluginByName(pluginInfo.name)

def parse_spec(filename):
    """
    Loads the YAML file into a Python object for parsing
    and returns it
    """

    fp = open(filename, 'r')
    spec = yaml.safe_load("\n".join(fp.readlines()))

    return spec

def update_dist_hook(config, spec):
    if config.update_dist_hook:
        logger.debug ("Update Dist hook script at: "+config.update_dist_hook)
        output_log=open("/tmp/"+spec['name']+"-update-dist.log", "a")
        subprocess.call([config.update_dist_hook], stdout=output_log)
        output_log.close()

def release_dist_hook(config, spec):
    if config.release_hook:
        logger.debug ("Release Hook script at: "+config.release_hook)
        output_log=open("/tmp/"+spec['name']+"-release-dist.log", "a")        
        subprocess.call([config.release_hook, config.version, config.release_hook_tag], stdout=output_log)
        output_log.close()

def build_pkg_hook(config, spec):
    if config.build_pkg_hook:
        logger.debug ("Build Hook script at: "+config.build_pkg_hook)
        output_log=open("/tmp/"+spec['name']+"-build-pkg.log", "a")

        args = config.build_pkg_hook_args if config.build_pkg_hook_args else ""

        subprocess.call([config.build_pkg_hook, args])
        output_log.close()

def run_package_build(spec, config, package, builder, tempdirs):
    logger.info("Running custom Distribution Hooks")
    update_dist_hook(config, spec)
    release_dist_hook(config, spec)
    build_pkg_hook(config, spec)
    logger.info("Creating package files")
    directory = builder.plugin_object.tree(spec, package, config)
    builder.plugin_object.build(directory, builder.plugin_object.filenamegen(package, config), config)
    tempdirs.append(directory)

def build_packages(spec, config):
    """
    Loops through package specs and call the package
    builders one by one
    """
    import re

    packages = spec['packages']
    tempdirs = []

    # Eventually replace this with a plugin system
    # with scripts to create build trees for different
    # packages
    for package in packages:
        try:
            builder = pkg_plugins[package['package']]
        except KeyError:
            logger.error("Module {0} isn't installed. Ignoring this package and continuing.".format(package['package']))
            exit
        
        # We want to build a package if there is no version defined or if version matches
        if package.get('pkg-version', None) is None or re.match(str(package.get('pkg-version','')), config.version) is not None:
            logger.info("package version:"+format(package.get('pkg-version'))+", config version: "+format(config.version))
            run_package_build(spec, config, package, builder, tempdirs)

    return tempdirs

def clean_up(dirs):
    """
    Delete the temporary build trees to save space
    """
    for fldr in dirs:
        shutil.rmtree(fldr, ignore_errors=True)

def assign_value(first, default=None):
    if first:
        return first
    else:
        return default

#
# Merge configuration options for package build from arguments and from package config
#
def extract_config(spec, config, outputdir, symlinks, permission):
    """
    Merge configuration options and specfile option together to pass them arround
    """
    config.output_dir=outputdir
    if spec.get('pkgbuild') is not None:
        # Prefer settings from packagespec file
        config.preserve_symlinks = assign_value(spec.get('pkgbuild').get('preserve-symlinks'), symlinks)
        config.preserve_permissions = assign_value(spec.get('pkgbuild').get('preserve-permissions'), permission)
        config.dist_directory = assign_value(spec.get('pkgbuild').get('dist-directory'), 'DIST/')


        config.update_dist_hook = assign_value(spec.get('pkgbuild').get('pkg-update-dist'))
        config.release_hook = assign_value(spec.get('pkgbuild').get('pkg-release-hooks'))

        if config.release_hook:
            config.release_hook_tag = assign_value(spec.get('pkgbuild').get('pkg-release-hooks-tag'), spec['version'])
            if config.release_hook_tag is None:
                logger.warning("Release tag not specified using defined version as TAG.")

        config.build_pkg_hook = assign_value(spec.get('pkgbuild').get('pkg-build-package'))
        if config.build_pkg_hook:
            env_name=spec['name'].replace("-", "_")+"_build_args"
            config.build_pkg_hook_args = assign_value(spec.get('pkgbuild').get('pkg-build-package-args'), os.environ.get(env_name))
            if config.build_pkg_hook_args is None:
                logger.warning("No build scripts args specified env var: "+env_name+" and pkg-build-package-args config option were not specified")

        #
        # if define_env_version is true then we take our build version from env variable called
        # name_of_package_with_underscores_version
        #		
        config.define_env_version = assign_value(spec.get('pkgbuild').get('define_env_version'))
     
        env_name=spec['name'].replace("-", "_")+"_version"
        config.version = assign_value(os.environ.get(env_name), spec.get('version'))
                
        logger.info("define_env_version is true I got pkg version from ENV = "+format(config.version))

def main():
    """
    Set up the application
    """

    logger.setLevel(logging.INFO)

    parser = optparse.OptionParser(description="Creates deb and RPM packages from files defined in a package specification.", prog="repacked.py", version=__version__, usage="%prog specfile [options]")
    parser.add_option('--outputdir', '-o', default='.', help="packages will be placed in the specified directory")
    parser.add_option('--no-clean', '-C', action="store_true", help="Don't remove temporary files used to build packages")
    parser.add_option('--preserve', '-p', default=False, action="store_true", help="Preserve Symlinks, default setting is to follow them.")
    parser.add_option('--permission', '-P', default=True, action="store_false", help="Disable preservation of  File Permissions, default setting is to preserve them.")

    options, arguments = parser.parse_args()

    # Parse the specification
    try:
        spec = parse_spec(arguments[0])
    except IndexError:
        parser.print_usage()
        logger.error("Run with --help option for more information.")
        sys.exit(1)

    config=Configuration()
    extract_config(spec, config, options.outputdir, options.preserve, options.permission)

    # Import the plugins
    logger.debug("Enumerating plugins...")

    for plugin in pluginMgr.getAllPlugins():
        logger.debug("Found plugin {name}".format(name=plugin.name))
        pkg_plugins[plugin.name] = plugin
    
    # Create build trees based on the spec
    logger.info("Building packages...")
    tempdirs = build_packages(spec, config)

    # Clean up old build trees
    if not options.no_clean:
        logger.info("Cleaning up...")
        clean_up(tempdirs)

if __name__ == "__main__":
    main()
