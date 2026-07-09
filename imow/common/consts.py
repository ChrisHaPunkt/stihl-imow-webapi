IMOW_OAUTH_URI = "https://oauth2.imow.stihl.com"
IMOW_API_URI = "https://api.imow.stihl.com"
IMOW_APP_URI = "https://app.imow.stihl.com"
IMOW_OAUTH_CLIENT_ID = "9526273B-1477-47C6-801C-4356F58EF883"

# Hosts whose cookies belong to the STIHL auth/session and must be isolated
# from any externally provided (e.g. shared) aiohttp cookie jar.
IMOW_COOKIE_HOSTS = (
    "app.imow.stihl.com",
    "oauth2.imow.stihl.com",
    "api.imow.stihl.com",
)
