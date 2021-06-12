# Changelog

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
      'error_id': 'M1120', 
      'error': True
  }
  ```
  The MowerState Class now provides a ```state_message``` property which gives a ``short`` and``long`` text for
  description (Besides an error indication and error_id). All error and status codes are now dynamically matched and
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
