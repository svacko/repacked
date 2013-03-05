
#!/usr/bin/python

"""
repacked - dead simple package creation
"""

from pkg_resources import resource_string
from yapsy.PluginManager import PluginManager

__author__ = "Jonathan Prior and fixes by Adam Hamsik"
__copyright__ = "Copyright 2011, 736 Computing Services Limited"
__license__ = "LGPL"
__version__ = "106"
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

class Configuration:
    def __init__(self):
        self.preserve_symlinks=False
        self.preserve_permissions=True
        self.output_dir=None
        self.dist_directory=None
        self.update_dist_hook=None
        self.release_hook=None
        self.build_dist_hook=None

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
        print ("Update Dist hook script at"+config.update_dist_hook)
        output_log=open("/tmp/"+spec['name']+"-bundler.log", "a")
        subprocess.call([config.update_dist_hook], stdout=output_log)
        output_log.close()

def release_dist_hook(config, spec):
    if config.release_hook:
        print ("Release Hook script at"+config.release_hook)
        output_log=open("/tmp/"+spec['name']+"-bundler.log", "a")        
        subprocess.call([config.release_hook], stdout=output_log)
        output_log.close()

def build_dist_hook(config, spec):
    if config.build_dist_hook:
        print ("Build Hook script at "+config.build_dist_hook)
        output_log=open("/tmp/"+spec['name']+"-bundler.log", "a")
        subprocess.call([config.build_dist_hook], stdout=output_log)
        output_log.close()

def build_packages(spec, config):
    """
    Loops through package specs and call the package
    builders one by one
    """
    packages = spec['packages']
    tempdirs = []

    # Eventually replace this with a plugin system
    # with scripts to create build trees for different
    # packages
    for package in packages:
        try:
            builder = pkg_plugins[package['package']]
        except KeyError:
            builder = None
            print("Module {0} isn't installed. Ignoring this package and continuing.".format(package['package']))
        
        if builder:
            print("Running custom Distribution Hooks")
            update_dist_hook(config, spec)
            release_dist_hook(config, spec)
            build_dist_hook(config, spec)
            print("Creating package files")
            directory = builder.plugin_object.tree(spec, package, config)
            builder.plugin_object.build(directory, builder.plugin_object.filenamegen(package), config)
            tempdirs.append(directory)
        
    return tempdirs

def clean_up(dirs):
    """
    Delete the temporary build trees to save space
    """
    for fldr in dirs:
        shutil.rmtree(fldr, ignore_errors=True)

#
# Merge configuration options for package build from arguments and from package config
#
def extract_config(spec, config, outputdir, symlinks, permission):
    """
    Merge configuration options and specfile option together to pass them arround
    """
    # Prefer settings from packagespec file
    try:
        config.preserve_symlinks = spec['pkgbuild']['preserve-symlinks']
    except KeyError:
    	config.preserve_symlinks = symlinks

    try:
        config.preserve_permissions = spec['pkgbuild']['preserve-permissions']
    except KeyError:
    	config.preserve_permissions = permission

    try:
        config.update_dist_hook = spec['pkgbuild']['pkg-update-dist']
    except KeyError:
        pass

    try:
        config.release_hook = spec['pkgbuild']['pkg-release-hooks']
    except KeyError:
        pass

    try:
        config.build_package_hook = spec['pkgbuild']['pkg-build-package']
    except KeyError:
        pass

    try:
        config.dist_directory = spec['pkgbuild']['dist-directory']
    except KeyError:
        config.dist_directory = 'DIST/'

    config.output_dir=outputdir

def main():
    """
    Set up the application
    """

    parser = optparse.OptionParser(description="Creates deb and RPM packages from files defined in a package specification.",
                                   prog="repacked.py", version=__version__, usage="%prog specfile [options]")
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
        print("Run with --help option for more information.")
        sys.exit(0)

    config=Configuration()
    extract_config(spec, config, options.outputdir, options.preserve, options.permission)

    # Import the plugins
    print("Enumerating plugins...")

    for plugin in pluginMgr.getAllPlugins():
        print("Found plugin {name}".format(name=plugin.name))
        pkg_plugins[plugin.name] = plugin
    
    # Create build trees based on the spec
    print("Building packages...")
    tempdirs = build_packages(spec, config)

    # Clean up old build trees
    if not options.no_clean:
        print("Cleaning up...")
        clean_up(tempdirs)

if __name__ == "__main__":
    main()
