# Future Mochad JSON API

The bridge currently uses the main newline-delimited mochad TCP listener on
port `1099`.

A future `mochad-redux` milestone may add an optional generic JSON-RPC API on
port `1102`. If that daemon API is implemented, the bridge may add:

```text
MOCHAD_PROTOCOL=auto|json|legacy
```

The proposed modes are:

- `auto`: try the JSON API, then fall back to the legacy main listener.
- `json`: require the JSON API and fail clearly when unavailable.
- `legacy`: keep the current newline-delimited listener.

This selector and port `1102` support are not implemented. The daemon protocol
must remain generic X10 infrastructure; MQTT topics and Home Assistant entity
concepts remain bridge responsibilities.
