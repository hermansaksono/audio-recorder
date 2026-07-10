# audio-recorder

A standalone Streamlit app that records a study participant's spoken story and uploads
it to Amazon S3, plus a serverless pipeline that transcribes the recording and writes
the transcript back to DynamoDB.

This repository was split out of the combined micro-narratives storytelling app. It is
one part of a three-app pipeline:

```
App 1 (conversation, separate repo)        App 2 — this repo (recorder)         App 3 — this repo (pipeline)
────────────────────────────────────       ─────────────────────────────       ────────────────────────────
collects the participant's story      ──►   reads those points, records    ──►  S3 upload triggers Lambdas
points and writes them to DynamoDB          the audio, uploads the .wav          that transcribe the audio and
keyed by session_id                         to S3                                write text_story to DynamoDB
        │                                            ▲
        └──────────── shared session_id via URL ─────┘
```

There is **no in-app handoff** between App 1 and App 2. They are opened as two separate
links that carry the **same identifiers** in the URL, and they share state only through
the DynamoDB item keyed by `session_id`.

## What this repo contains

| Path | Role |
| --- | --- |
| `app.py` | App 2 — the Streamlit recorder (entry point). |
| `micCheck.py` | App 2 — microphone check / help / session-ended screens. |
| `recorder_services.py` | App 2 — S3 + DynamoDB clients, audio trimming/preview, S3 key contract. |
| `transcription_pipeline/` | App 3 — two AWS Lambdas that transcribe uploads. See its own [README](transcription_pipeline/README.md). |

## How App 2 works

The recorder reads `SESSION_ID`, `PROLIFIC_PID`, and `STUDY_ID` from the URL query string
(lowercase fallbacks accepted for hand-built links). `session_id` is **required** — it is
the DynamoDB primary key and drives the S3 upload path, so without it the app shows a
"missing session" message and stops.

It then runs a small state machine (`agentState`):

1. **Mic check** — record "hello" and play it back to confirm the microphone works.
   Failure routes to a **mic-help** page with troubleshooting steps, or ends the session.
2. **Record** — shows the storytelling points fetched from DynamoDB (`summary_answers`),
   then records the story. The recording is trimmed to a 10-minute maximum.
3. **Preview** — plays back the first 10 seconds. If the participant confirms, the **full**
   recording is uploaded to S3; if not, it is discarded so they can re-record.
4. **Done / upload-failed** — a thank-you screen, or a retry on upload failure.

### The shared S3 key contract

The recording is uploaded to `{stem}/{stem}.wav` where
`stem = {participant_id}-{YYYYMMDD}-{HHMMSS}-{session_id}` (US Eastern time). The
participant id, date, and time contain no hyphens, so the transcription pipeline recovers
`session_id` as everything after the third hyphen. Keep this layout in sync with
`transcription_pipeline` if you change it.

App 2 only ever **reads** from DynamoDB (the storytelling points). The transcript and
`transcription_status` are written by App 3, not here.

## Running locally

This project uses Python 3.12 and [`pipenv`](https://pipenv.pypa.io/en/latest/).

```sh
pipenv sync            # install dependencies (streamlit, boto3, pydub)
pipenv run streamlit run app.py
```

Because the app requires a `session_id`, open it with the identifiers in the URL, e.g.:

```
http://localhost:8501/?SESSION_ID=test-session-1&PROLIFIC_PID=TESTPID&STUDY_ID=TESTSTUDY
```

### Secrets

Create `.streamlit/secrets.toml` (not committed) with your AWS configuration:

```toml
S3_BUCKET_NAME       = "<your-audio-bucket>"
DYNAMODB_TABLE_NAME  = "<your-dynamodb-table>"
AWS_DEFAULT_REGION   = "<region, e.g. us-east-2>"
AWS_ACCESS_KEY_ID    = "<your-access-key-id>"
AWS_SECRET_ACCESS_KEY = "<your-secret-access-key>"
```

If the S3 or DynamoDB settings are absent, the app still runs but skips the upload /
storytelling-points lookup respectively (useful for UI testing).

## The transcription pipeline (App 3)

App 3 is **not** a Streamlit app — it is two AWS Lambda functions wired to S3 and
EventBridge. When the recorder uploads a `.wav`, Lambda A starts an asynchronous Amazon
Transcribe job; when the job completes, Lambda B writes `text_story` and
`transcription_status` back onto the session's DynamoDB item. The transcript lives **only
in DynamoDB**. See [`transcription_pipeline/README.md`](transcription_pipeline/README.md)
for the flow, the `transcription_status` lifecycle, and deployment steps.

## Deployment

The recorder is a standard Streamlit app (see the `Procfile`) and can be deployed on
Streamlit Community Cloud or any host that runs `streamlit run app.py` (Python 3.12).
Configure the secrets above in the host's secrets manager. Deploy the transcription
pipeline separately to AWS as described in its README.
