# App 3 — Transcription pipeline (serverless)

This is the asynchronous replacement for the old blocking Transcribe loop that used
to run inside the Streamlit app. It runs entirely in AWS: the recorder app just
uploads audio to S3, and this pipeline transcribes it and writes the transcript back
into the session's DynamoDB item.

It is **not a Streamlit app** — it's two Lambda functions plus event wiring. The code
lives here (bundled with the recorder) so it travels with the recorder to its own
repo, but it is deployed to AWS, not run from this branch.

## Flow

```
recorder app  ──►  s3://storycraft-audio-bucket/{stem}/{stem}.wav
                        │  stem = {participant_id}-{YYYYMMDD}-{HHMMSS}-{session_id}  (Eastern time)
                        │  (S3 ObjectCreated event, no prefix, suffix ".wav")
                        ▼
                   Lambda A  (lambda_start_transcription.py)
                        │      starts an async Transcribe job (no output bucket, so the
                        │      raw result stays in Transcribe's managed bucket) — then exits
                        ▼
                   Amazon Transcribe
                        │  (EventBridge: "Transcribe Job State Change" = COMPLETED/FAILED)
                        ▼
                   Lambda B  (lambda_store_transcript.py)
                        │      fetches the transcript over HTTPS (TranscriptFileUri),
                        │      recovers session_id from the job's media URI, update_item's
                        │      DynamoDB
                        ▼
        DynamoDB item (Key: session_id) gains text_story + transcription_status
```

The transcript is stored **only in DynamoDB**. Nothing transcript-related is written
to `storycraft-audio-bucket` — the pipeline only ever reads the audio from it.

## The shared contract (must match the two Streamlit apps)

- **S3 key:** `{stem}/{stem}.wav` where
  `stem = {participant_id}-{YYYYMMDD}-{HHMMSS}-{session_id}` (Eastern local time) —
  written by the recorder (`recorder_services.build_audio_key`). The `participant_id`,
  date and time contain no hyphens, so the `session_id` is everything after the third
  hyphen of the stem (`stem.split("-", 3)[3]`), which stays correct even if the
  `session_id` itself contains hyphens. ⚠️ The conversation app
  (`finalise_services.build_audio_key`) must build the SAME key if it stores an audio
  location on the item; the pipeline itself reads the key from the S3 event, so it does
  not depend on that stored value.
- **DynamoDB primary key:** `session_id` on table
  `micro-narrative-story-app-database`. ⚠️ **Confirm the table's partition key is
  actually `session_id`** before deploying — `update_item` depends on it.
- **Region:** `us-east-2` (matches the current bucket/table).

## Files

| File | Role |
| --- | --- |
| `lambda_start_transcription.py` | Lambda A — S3 event → `start_transcription_job` (no polling). Handler: `lambda_start_transcription.handler`. |
| `lambda_store_transcript.py` | Lambda B — job-complete event → read transcript → `update_item`. Handler: `lambda_store_transcript.handler`. |
| `iam_policy.json` | Least-privilege policy for the Lambda execution role. |

## Environment variables

Lambda A:
- `LANGUAGE_CODE` (optional, default `en-US`)
- `JOB_NAME_PREFIX` (optional, default `story-`)
- `TABLE_NAME` = `micro-narrative-story-app-database` (optional — enables the
  `PROCESSING` marker; if unset the marker is skipped and transcription still works)

Lambda B:
- `TABLE_NAME` = `micro-narrative-story-app-database`

## Deploy (console outline)

1. **IAM role** — create a Lambda execution role, attach `iam_policy.json` (adjust the
   account id / bucket / table if they change) plus the AWS-managed
   `AWSLambdaBasicExecutionRole` for CloudWatch logs.
2. **Lambda A** — Python 3.12, handler `lambda_start_transcription.handler`, the role
   above, env vars set. Add an **S3 trigger** on `storycraft-audio-bucket` with suffix
   `.wav` (no prefix — the recordings sit at the bucket root).
3. **Lambda B** — Python 3.12, handler `lambda_store_transcript.handler`, same role,
   env vars set.
4. **EventBridge rule** — event pattern:
   ```json
   {
     "source": ["aws.transcribe"],
     "detail-type": ["Transcribe Job State Change"],
     "detail": { "TranscriptionJobStatus": ["COMPLETED", "FAILED"] }
   }
   ```
   Target: Lambda B.

## `transcription_status` lifecycle

Each session item carries a `transcription_status` that only moves forward, so the
state of every session is a single queryable field:

| Value | Set by | Meaning |
| --- | --- | --- |
| *(absent)* | — | App 1 wrote the row but the pipeline never ran (no recording, or Lambda A never fired). |
| `PROCESSING` | Lambda A | Transcribe job submitted; awaiting completion. A session stuck here past a few minutes needs attention. |
| `COMPLETED` | Lambda B | Transcript written to `text_story` (non-empty). |
| `EMPTY` | Lambda B | Job completed but the transcript was blank — silence / no speech / failed mic. `text_story` is `""`. |
| `FAILED` | Lambda B | Transcribe job failed; `transcription_failure_reason` holds why. |

## Idempotency & errors

- Lambda A uses a deterministic job name (`story-{session_id}`) and replaces an
  existing job on re-upload, so a participant re-recording just overwrites.
- Lambda A's `PROCESSING` marker is best-effort: the job is already submitted before it
  runs, so a DynamoDB hiccup there is logged, not raised, and does not block
  transcription.
- Lambda B uses `update_item`, so re-delivered events are harmless and only the
  transcription fields are touched.
- A completed-but-blank transcript is written as `EMPTY` (not `COMPLETED`) so it is not
  mistaken for a successful transcription.
- On a FAILED job, Lambda B writes `transcription_status = "FAILED"` plus
  `transcription_failure_reason` instead of a transcript.

## Where the transcript lives

The transcript ends up **only in DynamoDB** (`text_story` on the `session_id` item).
No output bucket is configured, so Amazon Transcribe keeps the raw result JSON in its
own service-managed bucket and Lambda B fetches it over HTTPS via the job's
`TranscriptFileUri`. Your `storycraft-audio-bucket` is only ever read from (the input
audio), never written to by this pipeline — so there is no risk of the output
re-triggering Lambda A.
