
# Changelog

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
