# STIHL iMow unofficial Python API wrapper

[![PyPI version shields.io](https://img.shields.io/pypi/v/imow-webapi)](https://pypi.python.org/pypi/imow-webapi/)
[![Docs on GitHub pages](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](hhttps://chrishapunkt.github.io/stihl-imow-webapi/imow)
[![CI](https://github.com/ChrisHaPunkt/stihl-imow-webapi/actions/workflows/python-package.yml/badge.svg?branch=master)](https://github.com/ChrisHaPunkt/stihl-imow-webapi/actions/workflows/python-package.yml)
[![PyPI download total](https://img.shields.io/pypi/dm/imow-webapi)](https://pypi.python.org/pypi/imow-webapi/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/imow-webapi)](https://pypi.python.org/pypi/imow-webapi/)
[![PyPI license](https://img.shields.io/pypi/l/imow-webapi)](https://pypi.python.org/pypi/imow-webapi/)


This unofficial Python API was created to provide an interface to interact with the STIHL iMow mower WebAPI. This wrapper is able to receive the current status
status from the mowers and to send actions.  
I wrote this library to implement an integration for the [Home Assistant Smart Home System](https://www.home-assistant.io/), which you can find [here](https://github.com/ChrisHaPunkt/ha-stihl-imow).



## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing
purposes. See deployment for notes on how to deploy the project on a live system.

API Documentation is available on: [https://chrishapunkt.github.io/stihl-imow-webapi/imow](https://chrishapunkt.github.io/stihl-imow-webapi/imow)

If you want to  
[!["Buy Me A Coffee"](
https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee&emoji=&slug=chrishapunkt&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff)](https://www.buymeacoffee.com/chrishapunkt)


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

Import the module and instantiate the `IMowApi()` constructor with credentials. Afterwards, initiate the `get_token()` method.
Or place credentials in the `get_token()` method.

```python
from imow.api import IMowApi
from imow.common.actions import IMowActions
import asyncio


async def main():
    api = IMowApi(lang="de")
    # save token for later use if you want to recreate IMowApi(token=my_token) because the created token is valid for
    # 30 days
    token, expire_time = await api.get_token("email@account.stihl", "supersecret", return_expire_time=True)

    print(await api.get_token())

    mowers = await api.receive_mowers()
    mower = mowers[0]

    print(f"{mower.name} @ {mower.coordinateLatitude},{mower.coordinateLongitude}")
    print(f"Currently: {mower.stateMessage['short']}")
    await mower.update_setting("gpsProtectionEnabled", True)

    print(mower.stateMessage)
    print(mower.machineState)
    await mower.intent(IMowActions.TO_DOCKING)
    print(await mower.update_from_upstream())
    print(await mower.get_startpoints())

    # Cleanup the created http session
    await api.close()


if __name__ == "__main__":
    asyncio.run(main())

```
```text
Selection of outputs from above statements:
> Mährlin @ 54.123456,10.12345
> Currently: Hood blocked
> {'short': 'Hood blocked', 'long': 'The hood is blocked. Please check the hood and press the OK button on your machine (M1120).', 'legacyMessage': 'Abschaltung Automatikmode durch Bumper', 'errorId': '', 'error': False}
> HOOD_BLOCKED
> <imow.common.mowerstate.MowerState object at 0x000001B034C245F8>
```
## Testing
For unit testing run `pytest -s tests/test_unit*`. For upstream integration testing, provide a `/secrets.py` with the following contents:
````python
EMAIL = "email@account.stihl"
PASSWORD = "supersecret"
MOWER_NAME = "MyRobot"
````
and run `pytest -s tests/test_integration*` or `pytest -s`. 

## Built With

* aiohttp
* BeautifulSoup
* asyncio

## Versioning

Navigate to [tags on this repository](https://github.com/ChrisHaPunkt/imow-webapi/releases)
to see all available versions.

## Authors

| Mail Address                | GitHub Profile                                |
-----------------------------|-----------------------------------------------|
| chris@homeset.de          | [ChrisHaPunkt](https://github.com/ChrisHaPunkt)     |

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md)
license file for more details.

# Acknowledges

Thanks to

* https://github.com/nstrydom2/anonfile-api
* https://github.com/OpenXbox/xbox-webapi-python

for repo structure inspiration
