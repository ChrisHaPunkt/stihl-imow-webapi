IMOW_OAUTH_URI = "https://oauth2.imow.stihl.com"
IMOW_API_URI = "https://api.imow.stihl.com"
IMOW_APP_URI = "https://app.imow.stihl.com"
IMOW_OAUTH_CLIENT_ID = "9526273B-1477-47C6-801C-4356F58EF883"

# Endpoint used to probe whether the upstream API is under maintenance.
IMOW_MAINTENANCE_URI = (
    "https://app-api-maintenance-r-euwe-4bf2d8.azurewebsites.net/maintenance/"
)

# Base URL for the bundled i18n message files fetched from the SPA.
IMOW_I18N_BASE_URI = "https://app.imow.stihl.com/assets/i18n/animations"

# Hosts whose cookies belong to the STIHL auth/session and must be isolated
# from any externally provided (e.g. shared) aiohttp cookie jar.
IMOW_COOKIE_HOSTS = (
    "app.imow.stihl.com",
    "oauth2.imow.stihl.com",
    "api.imow.stihl.com",
)
