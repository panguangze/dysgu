from setuptools import setup, find_packages
import setuptools
from setuptools.extension import Extension
from Cython.Build import cythonize
import numpy
import redblackpy as rb
from distutils import ccompiler
from subprocess import run
import os
import sys
import glob
import platform
import pysam


# This was stolen from pybind11
# https://github.com/pybind/python_example/blob/master/setup.py
# As of Python 3.6, CCompiler has a `has_flag` method.
# cf http://bugs.python.org/issue26689
print(pysam.get_include())
print(numpy.get_include())
quit()

def has_flag(compiler, flagname):
    """Return a boolean indicating whether a flag name is supported on
    the specified compiler.
    """
    import tempfile

    with tempfile.NamedTemporaryFile('w', suffix='.cpp') as f:
        f.write('int main (int argc, char **argv) { return 0; }')
        try:
            compiler.compile([f.name], extra_postargs=[flagname])
        except setuptools.distutils.errors.CompileError:
            return False
    return True


def cpp_flag(compiler, flags):
    """Return the -std=c++[11/14/17] compiler flag.
    The newer version is prefered over c++11 (when it is available).
    """
    for flag in flags:
        if has_flag(compiler, flag):
            return flag


def get_extra_args():
    compiler = ccompiler.new_compiler()
    extra_compile_args = []

    flags = ['-std=c++17', '-std=c++14', '-std=c++11']

    f = cpp_flag(compiler, flags)
    if not f:
        raise RuntimeError("Invalid compiler")
    extra_compile_args.append(f)

    flags = ['--stdlib=libc++']
    f = cpp_flag(compiler, flags)
    if f:
        extra_compile_args.append(f)

    return extra_compile_args


# https://github.com/brentp/cyvcf2/blob/master/setup.py
# Build the Cython extension by statically linking to the bundled htslib
sources = [
    x for x in glob.glob('htslib/*.c')
    if not any(e in x for e in ['irods', 'plugin'])
]
sources += glob.glob('htslib/cram/*.c')
# Exclude the htslib sources containing main()'s
sources = [x for x in sources if not x.endswith(('htsfile.c', 'tabix.c', 'bgzip.c'))]

if 'CC' in os.environ and "clang" in os.environ['CC']:
    clang = True
else:
    clang = False

print("Clang:", clang)
ext_modules = list()

root = os.path.abspath(os.path.dirname(__file__))
include_dirs = [os.path.join(root, "htslib"), numpy.get_include()]
# include_dirs = [numpy.get_include()] + pysam.get_include()

extras = get_extra_args()  #["-Wno-sign-compare", "-Wno-unused-function",
                            # "-Wno-strict-prototypes", "-Wno-unused-result", "-Wno-discarded-qualifiers"]

print("Extra compiler args ", extras)


# No idea why this works:
if not clang:
    build_sources = [f"dysgu/sv2bam.pyx"] + sources
else:
    build_sources = [f"dysgu/sv2bam.pyx"]


ext_modules.append(Extension(f"dysgu.sv2bam",
                             build_sources,
                             libraries=['z', 'bz2', 'lzma', 'curl', 'ssl'] + (
                                       ['crypt'] if platform.system() != 'Darwin' else []),
                             library_dirs=['htslib', numpy.get_include(), 'dysgu'],
                             include_dirs=include_dirs,
                             extra_compile_args=extras,
                             language="c++"))


for item in ["io_funcs", "graph", "coverage", "assembler", "call_component",
             "map_set_utils", "cluster", "sv2fq", "sv2bam", "view"]:

    ext_modules.append(Extension(f"dysgu.{item}",
                                 [f"dysgu/{item}.pyx"],
                                 library_dirs=[numpy.get_include(), 'dysgu'],  # 'htslib',
                                 include_dirs=include_dirs,
                                 extra_compile_args=extras,
                                 language="c++"))

print("Found packages", find_packages(where="."))
setup(
    name="dysgu",
    author="Kez Cleal",
    author_email="clealk@cardiff.ac.uk",
    url="https://github.com/kcleal/dysgu",
    description="Structural variant calling",
    license="MIT",
    version='0.4.3',
    python_requires='>=3.7',
    install_requires=[
            'cython',
            'click',
            'numpy',
            'pandas',
            'pysam',
            'networkx>=2.4',
            'scikit-learn',
            'ncls',
            'scikit-bio',
            'sortedcontainers',
            'mmh3',

        ],
    packages=find_packages(where="."),
    ext_modules=cythonize(ext_modules),
    include_package_data=True,
    zip_safe=False,
    entry_points='''
        [console_scripts]
        dysgu=dysgu.main:cli
    ''',
)
