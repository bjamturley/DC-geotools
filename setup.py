from setuptools import setup

def readme():
    with open('README.md') as f:
        return f.read()

setup(name="dcgeotools",
      version="0.0.2",
      author = "Ben Turley",
      author_email = "ben.turley@dc.gov",
      description = "DC MAR Geo-Toolset",
      long_description = readme(),
      long_description_content_type = "text/markdown",
      url = "https://github.com/pypa/DC-geotools",
      packages=["dcgeotools"],
      install_requires=[
          "rtree",
          "pandas",
          "geopandas",
          "numpy",
      ],
      test_suite='nose.collector',
      tests_require=['nose'],
      zip_safe=False)