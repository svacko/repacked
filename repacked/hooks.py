
import os
import shutil
import re
import sys
import platform
import subprocess

class RepackedHooks():
    def init(self):
        self.RepackedHooksList={}

    def PkgUpdateDistHook():
        print("PkgUpdateDistHook")

    def PkgeReleaseHook():
        print("PkgReleaseHook")

    def PkgBuildPackageHook():
        print("PkgBuildPackage")
