# STIHL iMow unofficial Python API wrapper

[![PyPI version](https://img.shields.io/pypi/v/imow-webapi?style=for-the-badge&logo=pypi&logoColor=ccc)](https://pypi.python.org/pypi/imow-webapi/)
[![Docs on GitHub pages](https://img.shields.io/badge/docs-GitHub%20Pages-blue?style=for-the-badge&logo=github&logoColor=ccc)](https://chrishapunkt.github.io/stihl-imow-webapi/imow)
[![CI](https://img.shields.io/github/actions/workflow/status/ChrisHaPunkt/stihl-imow-webapi/python-package.yml?style=for-the-badge&logo=github&logoColor=ccc&branch=main)](https://github.com/ChrisHaPunkt/stihl-imow-webapi/actions/workflows/python-package.yml)
[![PyPI downloads](https://img.shields.io/pypi/dm/imow-webapi?style=for-the-badge&logo=pypi&logoColor=ccc&label=downloads)](https://pypi.python.org/pypi/imow-webapi/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/imow-webapi?style=for-the-badge&logo=python&logoColor=ccc)](https://pypi.python.org/pypi/imow-webapi/)
[![PyPI license](https://img.shields.io/pypi/l/imow-webapi?style=for-the-badge)](https://pypi.python.org/pypi/imow-webapi/)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a-coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=000)](https://www.buymeacoffee.com/chrishapunkt)


This unofficial Python API was created to provide an interface to interact with the STIHL iMow mower WebAPI. This wrapper is able to receive the current state
from the mowers and to send actions.  
I wrote this library to implement an integration for the [Home Assistant Smart Home System](https://www.home-assistant.io/), which you can find [here](https://github.com/ChrisHaPunkt/ha-stihl-imow).

## iMOW compatibility
STIHL uses different webapps for their iMOW generations. Currently only the **iMOW RMI series are supported** by this library, because i'm not able to reverse engineer the newer generation.
This is simply because I do not own them. 

If you use this webapp, [https://app.imow.sithl.com](https://app.imow.stihl.com), this library should work for your mower.

Also see here: [Issue #13](https://github.com/ChrisHaPunkt/stihl-imow-webapi/issues/13)
## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing
purposes. See deployment for notes on how to deploy the project on a live system.

API Documentation is available on: [https://chrishapunkt.github.io/stihl-imow-webapi/imow](https://chrishapunkt.github.io/stihl-imow-webapi/imow)

If you want to support this project, use the [Buy Me A Coffee](https://www.buymeacoffee.com/chrishapunkt) badge at the top of this page.


### Prerequisites

Python 3.14+ is required to run this application. Development uses
[uv](https://docs.astral.sh/uv/) for environment and package management.

### Installing

For development, clone the repository and let uv create the environment
(it will fetch Python 3.14 automatically per `.python-version`):

```bash
uv sync --group dev
```

Run commands inside the environment with `uv run`, e.g. `uv run pytest`.
Alternatively, install the published library into your own environment:

```bash
pip install imow-webapi
```

And have fun!

## Usage
### Python Import and Usage
Import the module and instantiate the `IMowApi()` constructor with credentials. Afterwards, initiate the `get_token()` method.
Or place credentials in the `get_token()` method.

```python
from imow.api import IMowApi
from imow.common.actions import IMowActions
import asyncio
import aiohttp


async def main():
    async with aiohttp.ClientSession() as session:
        api = IMowApi(aiohttp_session=session, lang="de")
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

### Example: Receive startpoints and intent mowing 
Save the following as `myscript.sh` and execute `chmod +x myscript.sh`. Make sure you install the api via `pip3 install imow-webapi`  
Afterwards you can execute via `./myscript.sh`
```bash
#!/usr/bin/env python3
from imow.api import IMowApi
from imow.common.actions import IMowActions
import asyncio
import aiohttp
import logging

logger = logging.getLogger("imow")
# Enable DEBUG output
logging.basicConfig(level=logging.DEBUG)

async def main():
    async with aiohttp.ClientSession() as session:
        api = IMowApi(aiohttp_session=session, lang="de")
        # save token for later use if you want to recreate IMowApi(token=my_token) because the created token is valid for
        # 30 days
        token, expire_time = await api.get_token("email@account.stihl", "supersecret", return_expire_time=True)
    
        print(await api.get_token())
    
        mowers = await api.receive_mowers()
        mower = mowers[0]
    
        print(f"{mower.name} @ {mower.coordinateLatitude},{mower.coordinateLongitude}")
        print(f"Currently: {mower.stateMessage['short']}")
    
        startpoints = await mower.get_startpoints()
        for i in range(len(startpoints)):
            print("Startpoint {}: {}".format(i, startpoints[i]))
        
        # if your mower supports the "startMowing" call, use this action (i.e iMow 600 series)
        await mower.intent(IMowActions.START_MOWING, starttime="2023-08-12 20:50")
        # await mower.intent(IMowActions.START_MOWING, endtime="2023-08-12 22:50")
        # await mower.intent(IMowActions.START_MOWING, starttime="2023-08-12 20:50", endtime="2023-08-12 22:50")

        # if your mower supports the "startMowingFromPoint" call, use this action (i.e iMow 400 series)
        await mower.intent(IMowActions.START_MOWING_FROM_POINT, duration=50)
        # await mower.intent(IMowActions.START_MOWING_FROM_POINT, startpoint=2)
        # await mower.intent(IMowActions.START_MOWING_FROM_POINT, duration=50, startpoint=2)


if __name__ == "__main__":
    asyncio.run(main())

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
