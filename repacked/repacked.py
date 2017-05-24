#!/usr/bin/python

"""
repacked - dead simple package creation
"""

from pkg_resources import resource_string
from yapsy.PluginManager import PluginManager
from mako.template import Template
from mako import exceptions

__author__ = "Jonathan Prior, enhanced by Adam Hamsik, Stanislav Bocinec, Michal Linhard"
__copyright__ = "Copyright 2011, 736 Computing Services Limited"
__license__ = "LGPL"
__version__ = "139"
__maintainer__ = "Stanislav Bocinec"
__email__ = "stanislav.bocinec@innovatrics.com"

import optparse
import yaml
import os
import sys
import tempfile
import distutils.dir_util
import shutil
import dbm
import shelve
import logging
import subprocess
import re

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
        self.version=None
        self.release=None
        self.define_env_version=None
        self.define_env_release=None
        self.config_version_db_path="/var/tmp/dbversion.db"
        self.config_version_db=None
        self.pkg_format="all"
        self.profile=None

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
        logger.debug ("Update Dist hook script: "+config.update_dist_hook)
        try:
            subprocess.check_call([config.update_dist_hook])
        except subprocess.CalledProcessError:
            logger.error("ERROR running " + config.update_dist_hook + " script")
            return(1)

def release_dist_hook(config, spec):
    if config.release_hook:
        logger.debug ("Release Hook script: "+config.release_hook)
        try:
            subprocess.check_call([config.release_hook, config.version + '.' + str(config.release), config.release_hook_tag])
        except subprocess.CalledProcessError:
            logger.error("ERROR running " + config.release_hook + " script")
            return(1)

def build_pkg_hook(config, spec):
    if config.build_pkg_hook:
        logger.debug ("Build Hook script: "+config.build_pkg_hook)
        args = config.build_pkg_hook_args if config.build_pkg_hook_args else ""
        try:
            subprocess.check_call([config.build_pkg_hook, args])
        except subprocess.CalledProcessError:
            logger.error("ERROR running " + config.build_pkg_hook + " script")
            return(1)

def run_package_build(spec, config, package, builder, tempdirs):
    logger.debug("Running custom distribution hook")
    if update_dist_hook(config, spec):
        logger.error("ERROR running distribution hook. Exitting")
        sys.exit(1)

    logger.debug("Running custom release hook")
    if release_dist_hook(config, spec):
        logger.error("ERROR running release hook. Exitting")
        sys.exit(1)

    logger.debug("Running custom build hook")
    if build_pkg_hook(config, spec):
        logger.error("ERROR running build hook. Exitting")
        sys.exit(1)

    logger.info("Creating package files")
    directory = builder.plugin_object.tree(spec, package, config)
    builder.plugin_object.build(directory, builder.plugin_object.filenamegen(package, config), config)

    env_name=spec['name'].replace("-", "_")+"_version"
    if config.config_version_db:
        config.config_version_db[env_name]=config.version

    tempdirs.append(directory)

def build_packages(spec, config):
    """
    Loops through package specs and call the package
    builders one by one
    """

    packages = spec['packages']
    name = spec['name']
    tempdirs = []

    # Eventually replace this with a plugin system
    # with scripts to create build trees for different
    # packages
    for package in packages:
        try:
            if config.pkg_format in [ "all", package['package'] ]:
                builder = pkg_plugins[package['package']]
            else: 
                logger.info("Ignoring %s package format for %s package and continuing" % (package['package'], name))
                continue
        except KeyError:
            logger.error("Module {0} isn't installed. Ignoring this package and continuing.".format(package['package']))
            exit
        # We want to build a package if there is no version defined or if version matches
        pkg_profile = package.get('profile', None)
        if config.profile is None or pkg_profile is None or pkg_profile == config.profile:
            if package.get('pkg-version', None) is None or re.match(str(package.get('pkg-version','')), config.version) is not None:
                logger.info("package version:"+format(package.get('pkg-version'))+", config version: "+str(config.version)+", release version: "+str(config.release))
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
def extract_config(spec, config, outputdir, symlinks, permission, pkgformat, profile):
    """
    Merge configuration options and specfile option together to pass them arround
    """
    import re

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
                logger.warning("Release hook tag not specified using defined version as TAG.")

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
        #
        # if define_env_release is true then we take our build release version from env variable called
        # name_of_package_with_underscores_release
        #
        config.define_env_release = assign_value(spec.get('pkgbuild').get('define_env_release'))

    env_name=spec['name'].replace("-", "_")+"_version"
    config.version = assign_value(os.environ.get(env_name), spec.get('version'))
    #if config.define_env_version is not None:
    #    logger.info("define_env_version is set, package version = "+format(config.version))
    
    env_name=spec['name'].replace("-", "_")+"_release"
    config.release = assign_value(os.environ.get(env_name), spec.get('release'))
    #if config.define_env_release is not None:
    #    logger.info("define_env_release is set, package version release = "+format(config.release))
    
    if pkgformat not in ['debian', 'rpm', 'all']:
        logger.error("pkg-format not supported. Supported values: debian/rpm/all")
        sys.exit(1)
    config.pkg_format = pkgformat
    config.profile = profile

def initialize_project(project_name):
    """
    Initialize new empty packaging project
    """
    project_abs_path=os.path.join(os.getcwd(), project_name)
    if not os.path.exists(project_abs_path):
        os.mkdir(project_abs_path)

    tmpl_dir = os.path.expanduser("~/.repacked/templates")
    if not os.path.exists(tmpl_dir):
        tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../repacked/templates')

    project_spec_file = open(os.path.join(project_abs_path, "packagespec"), "w")
    project_spec_tmpl = Template(filename=os.path.join(tmpl_dir, "packagespec.tmpl"))
    project_spec_content = project_spec_tmpl.render(
        project_name=project_name
    )

    project_spec_file.write(project_spec_content)
    project_spec_file.close()

def main():
    """
    Set up the application
    """
    if os.environ.get("REPACKED_DEBUG"):
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    parser = optparse.OptionParser(description="Creates DEB and RPM packages from files defined in a package specification.", prog="repacked.py", version=__version__, usage="%prog specfile [options]")
    parser.add_option('--outputdir', '-o', default='.', help="packages will be placed in the specified directory")
    parser.add_option('--no-clean', '-C', action="store_true", help="Don't remove temporary files used to build packages")
    parser.add_option('--pkg-format', '-f', default="all", help="Specify package format (all/debian/rpm), default setting is to create all")
    parser.add_option('--profile', '-F', default=None, help="Specify profiles to build, only packages in given profile will be created, includes all by default")
    parser.add_option('--init', '-i', dest='project_name', default=False, help="Initialize empty project in new directory")
    parser.add_option('--preserve', '-p', default=False, action="store_true", help="Preserve Symlinks, default setting is to follow them.")
    parser.add_option('--permission', '-P', default=True, action="store_false", help="Disable preservation of  File Permissions, default setting is to preserve them.")

    options, arguments = parser.parse_args()

    # Initialize new empty project
    if options.project_name:
        logger.info("Initializing new project \"{}\"".format(options.project_name))
        initialize_project(options.project_name)
        sys.exit(0)

    # Parse the specification
    try:
        spec = parse_spec(arguments[0])
    except IndexError:
        parser.print_usage()
        logger.error("Run with --help option for more information.")
        sys.exit(1)
    
    config=Configuration()
    extract_config(spec, config, options.outputdir, options.preserve, options.permission, options.pkg_format, options.profile)

    try:
        config.config_version_db = shelve.open(config.config_version_db_path)
    except dbm.error:
        config.config_version_db = None

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
        if not os.environ.get("REPACKED_DEBUG"):
            clean_up(tempdirs)
        else:
            logger.info("Not removing temp directories {dirs} debug enabled".format(dirs=tempdirs))

    if config.config_version_db:
        config.config_version_db.close()

if __name__ == "__main__":
    main()
