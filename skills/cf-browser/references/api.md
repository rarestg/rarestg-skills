# Cloudflare Browser Rendering API Reference

Base URL: `https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/browser-rendering`

All endpoints accept POST with JSON body. Every request requires either `url` (website) or `html` (raw markup).

## Endpoints

### `/markdown` — Rendered page as clean markdown

```json
{"url": "https://example.com"}
```

Returns `{"success": true, "result": "# Example Domain\n..."}`.

Best for LLM consumption. Pair with `rejectRequestPattern: ["/^.*\\.(css)/"]` to skip stylesheets and speed things up.

### `/scrape` — Extract elements by CSS selector

Requires `elements` array with `selector` strings.

```json
{
  "url": "https://example.com",
  "elements": [
    {"selector": "h1"},
    {"selector": "a"}
  ]
}
```

Each matched element returns: `text`, `html`, `attributes` (name/value pairs, e.g. `href`), `height`, `width`, `top`, `left`.

### `/json` — AI-powered structured extraction

Pass `prompt` and/or `response_format` (JSON schema). Uses Workers AI by default (incurs charges).

```json
{
  "url": "https://example.com",
  "prompt": "Extract all product listings",
  "response_format": {
    "type": "json_schema",
    "schema": {
      "type": "object",
      "properties": {
        "listings": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "title": {"type": "string"},
              "price": {"type": "string"}
            },
            "required": ["title"]
          }
        }
      }
    }
  }
}
```

**custom_ai** — swap in OpenAI/Anthropic/etc. Models tried in order as fallbacks:

```json
"custom_ai": [
  {"model": "openai/gpt-4o", "authorization": "Bearer sk-..."}
]
```

> Anthropic gotcha: do NOT use `response_format` with Claude models — use only `prompt`.

### `/content` — Full rendered HTML

```json
{"url": "https://example.com"}
```

Returns `{"success": true, "result": "<!DOCTYPE html>...", "meta": {"status": 200, "title": "..."}}`.

Use for JS-heavy / SPA sites where view-source is empty.

### `/links` — All hrefs on the page

```json
{"url": "https://example.com"}
```

Returns `{"success": true, "result": ["https://..."]}`.

Options: `"visibleLinksOnly": true`, `"excludeExternalLinks": true`.

### `/screenshot` — Binary PNG/JPEG

Returns raw bytes (use `--output`). Options via `screenshotOptions`:

```json
{
  "url": "https://example.com",
  "screenshotOptions": {"fullPage": true, "type": "jpeg", "quality": 80},
  "viewport": {"width": 1280, "height": 720}
}
```

`quality` is JPEG-only (400 error if used with PNG). Use `selector` to capture a specific element. Use `deviceScaleFactor` for hi-res.

### `/snapshot` — HTML + base64 screenshot in one call

```json
{"url": "https://example.com"}
```

Returns `{"success": true, "result": {"content": "<!DOCTYPE html>...", "screenshot": "iVBOR..."}}`.

Decode: `base64 -d <<< "$screenshot" > snap.png`

## Common Parameters (all endpoints)

### Page loading

| Parameter | Description |
|---|---|
| `gotoOptions.waitUntil` | `load` (default), `domcontentloaded`, `networkidle0`, `networkidle2` |
| `gotoOptions.timeout` | Max navigation time in ms |
| `waitForSelector` | Return as soon as this CSS selector appears (faster than networkidle) |

**waitUntil values:** `networkidle0` = zero connections for 500ms (best for SPAs). `networkidle2` = at most 2 connections for 500ms (good balance).

### Request filtering (speed optimization)

| Parameter | Description |
|---|---|
| `rejectResourceTypes` | Block by type: `image`, `stylesheet`, `font`, `script`, `media` |
| `rejectRequestPattern` | Block by regex |
| `allowResourceTypes` | Whitelist types |
| `allowRequestPattern` | Whitelist patterns |

### Auth & headers

| Parameter | Description |
|---|---|
| `cookies` | `[{name, value, domain, path}]` |
| `authenticate` | HTTP basic auth credentials |
| `setExtraHTTPHeaders` | Key/value pairs |
| `userAgent` | Custom UA (does NOT bypass bot detection) |

### Content injection

| Parameter | Description |
|---|---|
| `addScriptTag` | `[{"content": "..."}]` or `[{"url": "..."}]` |
| `addStyleTag` | `[{"content": "..."}]` or `[{"url": "..."}]` |
| `setJavaScriptEnabled` | Disable JS (default: true) |

### Viewport

Default 1920x1080. Override with `viewport: {width, height, deviceScaleFactor}`.
