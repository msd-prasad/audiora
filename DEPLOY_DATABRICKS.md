# Deploy Audiora on Databricks Apps

This repository deploys as one Databricks App:

```text
Browser → FastAPI (React static UI + API + OpenAI + ElevenLabs + FFmpeg)
```

The React build is served by FastAPI, so the browser uses relative `/api/...`
paths and no separate Node or Express process is deployed.

## 1. Pre-deploy checks

Run these from the repository root before pushing the deployment branch:

```bash
pnpm install --frozen-lockfile
pnpm --filter @audiora/frontend build
python3 -m py_compile services/story-audio/main.py services/story-audio/audio_api.py
find services/story-audio/sounds -type f -size +10M -print
```

The final command must print nothing: Databricks Apps rejects any individual
app file larger than 10 MB. The bundled sound library is required for local
mixing, so do not omit it unless `SOUND_LIBRARY_ROOT` points to an equivalent
runtime location.

FFmpeg and FFprobe are required by the renderer. Before enabling production
audio generation, confirm both binaries are present in the deployed app
environment (`ffmpeg -version` and `ffprobe -version`). The renderer reports a
clear startup error if either is unavailable.

## 2. Configure secrets

Do **not** upload `.env` or place API keys in Git or `app.yaml`.

In the Databricks App's **Resources** section, add two Secret resources with
read access to the appropriate secret scope:

| Resource key | Secret value |
| --- | --- |
| `audiora_openai_key` | OpenAI API key |
| `audiora_elevenlabs_key` | ElevenLabs API key |

`app.yaml` maps these resource keys to `OPENAI_API_KEY` and
`ELEVENLABS_API_KEY` only at runtime. Keep the resource keys exactly as shown
unless you update the corresponding `valueFrom` entries.

## 3. Deploy from Git

1. Push the branch containing this repository and select it as the Databricks
   App's Git source.
2. Ensure the app service principal has access to the repository and the two
   secret resources.
3. Deploy or redeploy from the App overview page. Databricks installs the root
   `requirements.txt`, detects the Node workspace, installs Node dependencies,
   runs the frontend build, and finally executes the `command` in `app.yaml`.
4. Open the URL shown on the App overview page and use `/api/health` to verify
   `storyEngine` and `audioEngine` are both `live`.

`app.yaml` starts `python services/story-audio/main.py`. The application honors
Databricks' `UVICORN_HOST` and `UVICORN_PORT` variables, so it listens on the
port assigned by the Apps runtime without a hard-coded production port.

## 4. Persist finished stories (recommended)

By default, generated WAV files and library metadata use the app's local
filesystem. Treat that storage as ephemeral: redeploys or restarts can remove
it. For durable output, create a Unity Catalog volume, grant the app service
principal access, and set these `app.yaml` environment values:

```yaml
env:
  - name: AUDIO_OUTPUT_ROOT
    value: /Volumes/<catalog>/<schema>/<volume>/audiora/rendered
  - name: LIBRARY_STORAGE_PATH
    value: /Volumes/<catalog>/<schema>/<volume>/audiora/library.json
```

The configured volume must be writable by the App service principal.

## 5. Troubleshooting

| Symptom | Check |
| --- | --- |
| `OPENAI_API_KEY is required` or `ELEVENLABS_API_KEY is required` | Confirm the App has both Secret resources and their resource keys match `app.yaml`. |
| Audio render fails before dialogue generation | Confirm outbound access to OpenAI and ElevenLabs, and verify the key resources. |
| `Missing: ffmpeg, ffprobe` | Confirm those binaries are present in the Databricks Apps runtime before enabling audio rendering. |
| Finished audio disappears after a redeploy | Configure the Unity Catalog volume paths above. |
| App build fails on a large asset | Run the pre-deploy `find ... -size +10M` check and move oversized assets to an approved runtime location. |

## References

- [Deploy a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy)
- [Configure app execution with app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime)
- [Add secret resources](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/secrets)
- [Databricks Apps environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env)
