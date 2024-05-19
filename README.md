# Aptus Home^2 Assistant Integration
Provides Aptus Home support for Home Assistant
enabling unlocking and locking some doors.
It is very hardcoded and probably doesn't work in every place.

```yaml
lock:
  - platform: aptus_home
    host: '<host url>'
    username: '<probably 4 digit code>'
    password: '<your password>'
```

There are also a test client for testing the API,
you wil just have to set the env vars
`APTUS_HOST`, `APTUS_USERNAME` and `APTUS_PASSWORD`.
