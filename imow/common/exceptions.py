class IMowError(Exception):
    """Base class for all errors raised by ``imow-webapi``.

    Consumers (e.g. the Home Assistant integration) can catch this to handle
    any library-specific failure with a single ``except`` clause.
    """


class LoginError(IMowError):
    pass


class ApiMaintenanceError(IMowError):
    pass


class MessageNotFoundError(IMowError):
    pass


class LanguageNotFoundError(IMowError):
    pass
