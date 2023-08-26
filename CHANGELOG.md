# Changelog
## Version 0.8.0 (2023-08-26)
This release focuses on support for imow 600 series. They need another action for mowing action calls.

### BREAKING CHANGE
The iMow action `IMowActions.START_MOWING` now creates a `startMowing` action and no longer a `startMowingFromPoint` action.
To issue a `startMowingFromPoint`, the new `IMowAction.START_MOWING_FROM_POINT` needs to be used.

#### Added 
- keywork arguments `starttime` and `endtime` in `IMow.intent()` call to be used with IMowActions.START_MOWING
- Updated Readme with `IMow.intent` exampes
- added debug log output in `intent()` call

## Version 0.7.10 (2023-05-13)
- Bugfix http_session not present on logout
## Version 0.7.9 (2023-05-13)
- remove unnecessary http_session closes
## Version 0.7.8 (2022-03-06)
- Implement a logout function `ImowAPI.api_logout()`. Use within re-authentication
## Version 0.7.7 (2022-03-06)
- Use more `async with`s
## Version 0.7.6 (2022-03-05)

### Dependency updates
- Update dependencies to latest

## Version 0.7.4 (2021-09-06)

### Bugfxes
- Allow handling of timestamps on mower intents (StartTime/Endtime)

## Version 0.7.3 (2021-07-03)

### Bugfxes
- Always return a MowerState on settings update

## Version 0.7.2 (2021-07-03)
```python
await mower.update_setting("gpsProtectionEnabled", True)
```
### Features
- Possibility to update a specific settings for a mower like gpsProtection on/off
## Version 0.7.0 (2021-06-30)
### Breaking Changes
- `IMowApi.intent` Parameter `mower_action_id` is renamed to `mower_external_id` to match the upstream api expectation.
### Features
- If an `api_request` is intended, and the used `access_token` expires in less than one day, it's automatically renewed.

## Version 0.6.0 (2021-06-28)
- ```python
  mower.machineError = 'M1120',
  mower.machineState = 'HOOD_BLOCKED',
  mower.stateMessage: dict = {
      'short': 'Hood blocked',
      'long': 'The hood is blocked. Please check the hood and press the OK button on your machine (M1120).',
      'legacyMessage': 'Abschaltung Automatikmode durch Bumper',
      'errorId': 'M1120',
      'error': True
  }
  ```

### Breaking Changes
- Migrated all own MowerState attributes to camelCase to match the upstream attributes style.
  ```
  - MowerState.stateMessage = None
  - MowerState.machineError = None
  - MowerState.machineState = None
  ```
## Version 0.5.2 (2021-06-15)

## Bugfixes
- Also quote password string in auth request to support more special chars

## Version 0.5.1 (2021-06-13)

## Features
- ```python
  mower.machine_error = 'M1120',
  mower.machine_state = 'HOOD_BLOCKED',
  mower.state_message: dict = {
      'short': 'Hood blocked',
      'long': 'The hood is blocked. Please check the hood and press the OK button on your machine (M1120).',
      'legacyMessage': 'Abschaltung Automatikmode durch Bumper',
      'errorId': 'M1120',
      'error': True
  }
  ```
  Provide a machine usable string from the short message in english

## Version 0.5.0 (2021-06-12)

### Breaking Changes

- The ``MowerTask`` class is removed in favor of the new ``state_message`` property on th ``MowerState`` object.
- The ``MowerState.get_current_task()`` method now returns the `short` property of the state message instead of a ``MowerTask``
  property and is now longer an ``async`` method.

### Features

- ```python
  mower.state_message -> dict
  {
      'short': 'Hood blocked',
      'long': 'The hood is blocked. Please check the hood and press the OK button on your machine (M1120).',
      'errorId': 'M1120',
      'error': True
  }
  ```
  The MowerState Class now provides a ```state_message``` property which gives a ``short`` and``long`` text for
  description (Besides an error indication and errorId). All error and status codes are now dynamically matched and
  human readable available.
  **This makes the ``MowerTask`` obsolete and it is removed with this release.**
- ``api = IMowApi(lang="en")``
  The imow api can now be instanced with a language code (fallback to ``en``).
  The ``state_message`` property displays the messages in the corresponding language.

## Version 0.4.5 (2021-06-01)

### Features

- Add 2 new identified Tasks within `MowerTask` (Thanks to @lausser)
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
