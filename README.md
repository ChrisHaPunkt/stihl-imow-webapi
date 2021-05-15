# STIHL iMow Unofficial Python API Wrapper

[![PyPI version shields.io](https://img.shields.io/pypi/v/imow-webapi)](https://pypi.python.org/pypi/imow-webapi/)
[![CI](https://github.com/ChrisHaPunkt/stihl-imow-webapi/actions/workflows/python-package.yml/badge.svg?branch=master)](https://github.com/ChrisHaPunkt/stihl-imow-webapi/actions/workflows/python-package.yml)
[![PyPI download total](https://img.shields.io/pypi/dm/imow-webapi)](https://pypi.python.org/pypi/imow-webapi/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/imow-webapi)](https://pypi.python.org/pypi/imow-webapi/)
[![PyPI license](https://img.shields.io/pypi/l/imow-webapi)](https://pypi.python.org/pypi/imow-webapi/)

This unofficial Python API was created to provide an interface to interact with the STIHL iMow mower WebAPI. This wrapper is able to receive the current status
status from the mowers and to send actions

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing
purposes. See deployment for notes on how to deploy the project on a live system.

### Prerequisites

Python 3.7+ is required to run this application, other than that there are no prerequisites for the project, as the
dependencies are included in the repository.

### Installing

To install the library is as simple as cloning the repository and running

```bash
pip install -e .
```

It is recommended to create an virtual environment prior to installing this library. Alternatively, you can also install
this library via Pip:

```bash
pip install imow-webapi
```

And have fun!

## Usage

Import the module and instantiate the `IMowApi()` constructor with credentials.
.

```python
from imow.api import IMowApi

if __name__ == '__main__':
    api = IMowApi("email@account.stihl", "supersecret")
    mower = api.receive_mowers()[0]
    print(f'{mower.name} @ {mower.coordinateLatitude},{mower.coordinateLongitude}')



```

## Testing
For unit testing run `pytest -s tests/test_unit*`. For upstream integration testing, provide a `/secrets.py` with the following contents:
````python
EMAIL = "my-stihl-imow-account@email.com"
PASSWORD = "supersecret"
MOWER_NAME = "MyRobot"
````
and run `pytest -s tests/test_integration*` or `pytest -s`. 

## Built With

* [Requests](http://docs.python-requests.org/en/master/) - Http for Humans

## Versioning

Navigate to [tags on this repository](https://github.com/ChrisHaPunkt/imow-webapi/releases)
to see all available versions.

## Authors

| Name             | Mail Address                | GitHub Profile                                |
|------------------|-----------------------------|-----------------------------------------------|
| Christian Heinrichs | chris.heinrichs.mail@gmail.com          | [ChrisHaPunkt](https://github.com/ChrisHaPunkt)     |

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md)
license file for more details.

# Acknowledges

Thanks to

* https://github.com/nstrydom2/anonfile-api
* https://github.com/OpenXbox/xbox-webapi-python

for repo structure inspiration