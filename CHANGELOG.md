
# Changelog

## Version 0.4.3 (2021-05-27)

### Features
- Allow `IMowAPI` Class to use predefined `aiohttp` session when instantiating

## Version 0.4.1 (2021-05-24)

### Changes
- Even more asynchronously with switch from `requests` to `aiohttp` 

## Version 0.4.0 (2021-05-17)

### Breaking Changes
- Reworked everything to use asyncio where possible. See Readme.md for new usage example.
- Renamed MowerState method `update` to `update_from_upstream`
- Renamed MowerState method `get_status` to `get_current_status`

## Version 0.3.0 (2021-05-17)

### Breaking Changes
- Renamed Class/Enum `MowerState` to `MowerTask` because it describes the current task not the state
- Renamed Class `Mower` to `MowerState` because it's just a snapshot of the last upstream state

### Features
- Add methods to work on `MowerState` objects, like action intents or statistic receive
- Add PDoc documents, available on [https://chrishapunkt.github.io/stihl-imow-webapi/imow](https://chrishapunkt.github.io/stihl-imow-webapi/imow)

### Bugfixes
- Return a valid error message and raise if provided login credentials are wrong


## Version 0.2.2 (2021-05-00)

- Initial release
