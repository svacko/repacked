
from repacked import Configuration
from pkg_resources import resource_string
from yapsy.IPlugin import IPlugin
from mako.template import Template

import os
import distutils.dir_util
import shutil
import tempfile
import re
import sys
import platform
import logging

tmpl_dir = os.path.expanduser("~/.repacked/templates")
logger = logging.getLogger()
logger.setLevel(logging.INFO)

if not os.path.exists(tmpl_dir):
    tmpl_dir = os.path.join(os.path.dirname(__file__),'../../repacked/templates')

class DebianPackager(IPlugin):
    def __init__(self):
        self.spec = {}
        self.package = {}
        self.output_dir = ""
        self.preserve_symlinks=False
        self.preserve_permissions=True

    def get_system_arch(self):
        arch = platform.architecture()[0]
        return arch

    def checkarch(self, architecture):
        if architecture == "system":
            architecture = self.get_system_arch()

        if architecture == "32-bit" or architecture == "32bit":
            architecture = "i386"
        elif architecture == "64-bit" or architecture == "64bit":
            architecture = "amd64"

        return architecture

    def filenamegen(self, package, config):
        """
        Generates a nice simple filename for a package
        based on its package info
        """

        spec = self.spec

        filename = "{name}_{version}-{release}_{architecture}.deb".format(
            name=spec['name'],
            version=config.version,
            release=config.release,
            architecture=self.checkarch(package['architecture']),
        )

        return filename

    def get_deps(self, package, config):
        if package.get('requires') is not None:
            return Template(package.get('requires')).render(package_version=config.version)
        else:
            return None

    def tree(self, spec, package, config):
        """
        Builds a debian package tree
        """

        self.spec = spec
        self.package = package

        ## Create directories

        # Create the temporary folder
        tmpdir = tempfile.mkdtemp()

        # Create the directory holding control files
        os.mkdir(os.path.join(tmpdir, "DEBIAN"))

        try:
            packagetree=spec['packagetree']
            # Copy across the contents of the file tree
            distutils.dir_util.copy_tree(spec['packagetree'], tmpdir, preserve_mode=config.preserve_permissions, preserve_symlinks=config.preserve_symlinks)
        except KeyError:
            logger.warning("No BUILDIR provided. This is ok if this should be used as meta package.")

        logger.debug(("Debian package tree created in {0}".format(tmpdir)))

        ## Create control file
        cf = open(os.path.join(tmpdir, "DEBIAN", "control"), "w")

        cf_template = Template(filename=os.path.join(tmpl_dir, "debcontrol.tmpl"))

        cf_version = config.version
        cf_release = str(config.release).replace('-','.');
        cf_provides = package.get('provides')
        cf_provides = "" if cf_provides == None else ", " + cf_provides

        cf_final = cf_template.render(
            package_name=spec['name'],
            version="{0}-{1}".format(cf_version, cf_release),
            architecture=self.checkarch(package['architecture']),
            maintainer=spec['maintainer'],
            size=os.path.getsize(tmpdir),
            summary=spec['summary'],
            description="\n .\n ".join(re.split(r"\n\s\s*", spec['description'].strip())),
            dependencies=self.get_deps(package, config),
            predepends=package.get('predepends'),
            replaces=package.get('replaces'),
            provides="{0}-{1}{2}".format(spec['name'], cf_version, cf_provides),
            conflicts=package.get('conflicts'),
        )

        cf.write(cf_final)
        cf.close()

        ## Check for lintian overrides and add them to the build tree
        overrides = package.get('lintian-overrides')

        if overrides:
            lint_tmpl = "{package}: {override}\n"
            lintfile = ""

            overrides = overrides.split(",")

            for o in overrides:
                override = o.strip()
                lintfile += lint_tmpl.format(package=spec['name'], override=override)

            try:
                os.makedirs(os.path.join(tmpdir, "usr/share/lintian/overrides"))
                do_overrides = True
            except:
                # Directory exists, skip it
                do_overrides = False

            if do_overrides:
                lf = open(os.path.join(tmpdir, "usr/share/lintian/overrides", spec['name']), "w")
                lf.write(lintfile)
                lf.close()

        ## Copy over installation scripts

        try:
            scripts = spec['scripts']
        except:
            # No installation scripts
            scripts = None

        if scripts:
            for app in list(scripts.items()):
                script = app[0]
                filename = app[1]

                if os.path.isfile(filename):
                    shutil.copy(filename, os.path.join(tmpdir, "DEBIAN"))
                    os.chmod(os.path.join(tmpdir, "DEBIAN", script), 0o755)
                else:
                    logger.error(("Installation script {0} not found.".format(script)))

        return tmpdir

    def build(self, directory, filename, config):
        """
        Builds a deb package from the directory tree
        """

        filename = os.path.join(config.output_dir, filename)
        logger.debug(("fakeroot dpkg-deb --build {0} {1}".format(directory, filename)))
        os.system("fakeroot dpkg-deb --build {0} {1} 2>&1 1>/dev/null".format(directory, filename))
