# Changelog

## Version 0.4.5 (2021-06-01)

### Features

- Add `check_api_maintenance()` method to `IMowAPI` Class. Check if the api server is currently under maintenance.  
  This method is automatically called if the api server returns a 500 error response for any request.
- One should call the new `close()` method for the `IMowAPI` Class when finishing the api interactions to correctly
  close the http session.

### Bugfixes

- [Issue #8](https://github.com/ChrisHaPunkt/stihl-imow-webapi/issues/8) - Example not working

## Version 0.4.4 (2021-05-28)

### Features

- Add `validate_token()` method to `IMowAPI` Class. Test if a token is valid and is able to call the webapi.

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
- Add PDoc documents, available
  on [https://chrishapunkt.github.io/stihl-imow-webapi/imow](https://chrishapunkt.github.io/stihl-imow-webapi/imow)

### Bugfixes

- Return a valid error message and raise if provided login credentials are wrong

## Version 0.2.2 (2021-05-00)

- Initial release
