import re
from setuptools import find_packages, setup

with open("imow/common/package_descriptions.py", encoding='utf-8') as file_handler:
    lines = file_handler.read()
    version = re.search(r'__version__ = "(.*?)"', lines).group(1)
    package_name = re.search(r'package_name = "(.*?)"', lines).group(1)
    python_major = int(re.search(r'python_major = "(.*?)"', lines).group(1))
    python_minor = int(re.search(r'python_minor = "(.*?)"', lines).group(1))
PACKAGES = [f"imow.{p}" for p in find_packages(where="imow")]
with open("requirements/release.txt", mode='r', encoding='utf-8') as requirements:
    packages = requirements.read().splitlines()

setup(
    name="imow-webapi",
    version=version,
    author="ChrisHaPunkt",
    description="A library to authenticate and interact with STIHL iMow mowers using their WebAPI",
    long_description=open("README.md").read() + "\n\n" + open("CHANGELOG.md").read(),
    long_description_content_type="text/markdown",
    license="GPL",
    keywords="stihl imow mower api",
    url="https://github.com/ChrisHaPunkt/stihl-imow-webapi",
    packages=PACKAGES,
    namespace_packages=["imow"],
    zip_safe=False,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    test_suite="tests",
    install_requires=packages,
    setup_requires=["pytest-runner"],
    entry_points={
        'console_scripts': ['%s=%s.__init__:main' % (package_name, package_name)]
    },
)

wheel_name = package_name.replace('-', '_') if '-' in package_name else package_name
print("Setup is complete. Run 'python -m pip install dist/%s-%s-py%d-none-any.whl' to install this wheel." % (wheel_name, version, python_major))
