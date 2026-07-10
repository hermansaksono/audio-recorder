# Setup

This file collects notes on configuring an instance of the **audio recorder** (App 2)
and the identifiers it depends on. For the overall architecture, see the
[README](../README.md); for the transcription pipeline (App 3), see
[`transcription_pipeline/README.md`](../transcription_pipeline/README.md).

## Participant identifiers come from the URL

Unlike the original micro-narratives app, the recorder is **not** configured through a
`config` file and does **not** prompt the participant for an ID. It reads its identifiers
from the URL query string when the page loads (`initialiseSessionState` in `app.py`):

| Session-state key | Primary query param | Lowercase fallback |
| --- | --- | --- |
| `session_id` | `SESSION_ID` | `session_id` |
| `participant_id` / `prolific_pid` | `PROLIFIC_PID` | `participant_id` / `prolific_pid` |
| `study_id` | `STUDY_ID` | `study_id` |

The uppercase names match the identifiers Prolific appends to a study URL; the lowercase
fallbacks exist for hand-built or test links, e.g.:

```
https://<your-recorder-host>/?SESSION_ID=abc-123&PROLIFIC_PID=TESTPID&STUDY_ID=TESTSTUDY
```

### `session_id` is required

`session_id` is the DynamoDB primary key **and** the value baked into the S3 upload path,
so the recorder cannot function without it. If it is absent, the app shows a
"missing session information" message and stops. `participant_id` and `study_id` are used
for the S3 key / logging and degrade gracefully if missing (the participant id falls back
to `unknown`).

## Shared state with the conversation app

The recorder and the conversation app (App 1) are opened as **two separate links carrying
the same identifiers** — there is no in-app handoff. They share data only through the
DynamoDB item keyed by `session_id`:

- **App 1 writes** `summary_answers` (the storytelling points) onto the item.
- **The recorder reads** `summary_answers` to show the participant their points while they
  record. It never writes to DynamoDB.
- **App 3 (the pipeline) writes** `text_story` and `transcription_status` onto the same
  item after transcribing the upload.

## The S3 key contract

The recording is uploaded to `{stem}/{stem}.wav`, where
`stem = {participant_id}-{YYYYMMDD}-{HHMMSS}-{session_id}` in US Eastern time
(`recorder_services.build_audio_key`). The participant id is stripped of hyphens and the
date/time are hyphen-free, so `session_id` is everything after the third hyphen — this is
how the transcription pipeline recovers it. Keep this layout in sync with
`transcription_pipeline` if you change it.

## Secrets

The recorder reads its AWS configuration from `.streamlit/secrets.toml` (not committed):

```toml
S3_BUCKET_NAME        = "<your-audio-bucket>"
DYNAMODB_TABLE_NAME   = "<your-dynamodb-table>"
AWS_DEFAULT_REGION    = "<region, e.g. us-east-2>"
AWS_ACCESS_KEY_ID     = "<your-access-key-id>"
AWS_SECRET_ACCESS_KEY = "<your-secret-access-key>"
```

- If `S3_BUCKET_NAME` is absent, the upload step is skipped (the app still runs, useful for
  UI testing).
- If `DYNAMODB_TABLE_NAME` is absent, the storytelling-points lookup is skipped and the
  record page simply shows no points.

The DynamoDB table's partition key **must** be `session_id` (String), matching the key
used by both the conversation app and the transcription pipeline.

> [!TIP]
> When running locally you can rely on any `boto3`-compatible credential source instead of
> putting keys in `secrets.toml` — see `boto3`'s
> [credentials documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html).
> The credentials must allow `s3:PutObject` on the bucket and `dynamodb:GetItem` on the table.
