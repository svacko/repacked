from setuptools import setup, find_packages
import sys, os

version = '104'

if sys.version_info[0] == 2:
	yapsy='Yapsy==1.9'
else:
	yapsy='Yapsy==1.9.2_python3'


setup(name='repacked',
      version=version,
      description="repacked is a simple way to build multiple deb/RPM packages from a single directoryy",
      long_description=open("README").read(),
      classifiers=[
         'Development Status :: 4 - Alpha',
         'Environment :: Console',
         'Intended Audience :: Developers',
         'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
         'Programming Language :: Python',
         'Topic :: Software Development :: Libraries :: Python Modules',
      ],
      keywords='packaging',
      author='Adam Hamsik',
      author_email='adam.hamsik@innovatrics.com',
      url='https://github.com/736/repacked/',
      license='LGPL',
      packages=find_packages(exclude=['examples', 'tests']),
      scripts=["repacked/repacked.py"],
      package_data={'repacked': ['plugins/*.plugin', 'templates/*.tmpl']},
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'mako', yapsy, 'pyyaml'
      ],
)
