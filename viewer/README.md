# Viewer

A web app over the check. Synthetic data only.

```
uv sync --extra viewer                  # add --extra audio on Apple Silicon to record or upload audio
viewer/serve-demo.sh --local            # http://127.0.0.1:8000
```

`serve-demo.sh` loads `.env` from the repo root (git-ignored; copy `.env.example`) and keeps the Mac awake while it runs. Ctrl-C stops it. `uv run kyc-viewer` starts the same app without the extras.

**New meeting** offers:

- **Record**, or **upload audio**: transcribed on the machine by Whisper; the first audio run downloads the model (about 1.5 GB).
- **Paste a transcript**: one turn per line, `speaker: text`.
- **Load a sample meeting**: C01 and the demo meetings D01–D05 in `samples/`.

Click an underlined phrase in the transcript to see the fact it produced; click a fact to find its words. Each key figure has a play button for the seconds of audio behind it, and a Confirm button. **Download check** saves the result as one HTML file: flags, key figures with what was confirmed, what needs confirmation, gaps, and every fact with the client's words.

## Sharing it

The viewer has no accounts. To let others open it, set both in `.env`:

```
VIEWER_PASSWORD=<a long shared password>   # checked on every route (HTTP Basic; any user name)
VIEWER_BUDGET_USD=5                        # total new API spend the viewer may make
```

- **Budget:** each run is capped at $0.50, and spend is kept in `.viewer-spend.json` across restarts. Once it's used up, the samples and any meeting already seen still work (from cache, free); new meetings get a clear "budget used up" message.
- **A fixed public link:** with Tailscale installed and signed in, `viewer/serve-demo.sh` serves the app on Tailscale Funnel at `https://<machine>.<tailnet>.ts.net/`. It refuses to go public without a password and a budget. The link works only while the machine is on and the script is running.
- **An iPad on the same Wi-Fi, without Tailscale:** `uv run kyc-viewer --lan` serves HTTPS on the local network with a [mkcert](https://github.com/FiloSottile/mkcert) certificate. Recording needs the iPad to trust the certificate: install `$(mkcert -CAROOT)/rootCA.pem` (never `rootCA-key.pem`) as a profile, then turn on full trust under Settings > General > About > Certificate Trust Settings.
- Uploaded audio is kept in `.viewer-audio/` (git-ignored) so key figures can be played back. Empty it after a demo.
