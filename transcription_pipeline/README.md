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
recorder app  ──►  s3://storycraft-audio-bucket/recordings/{session_id}/audio.wav
                        │  (S3 ObjectCreated event, prefix "recordings/", suffix ".wav")
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

- **S3 key:** `recordings/{session_id}/audio.wav` — written by the recorder
  (`recorder_services.build_audio_key`) and stored on the item by the conversation
  app (`finalise_services.build_audio_key`). The `session_id` is the second path
  segment.
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

Lambda B:
- `TABLE_NAME` = `micro-narrative-story-app-database`

## Deploy (console outline)

1. **IAM role** — create a Lambda execution role, attach `iam_policy.json` (adjust the
   account id / bucket / table if they change) plus the AWS-managed
   `AWSLambdaBasicExecutionRole` for CloudWatch logs.
2. **Lambda A** — Python 3.12, handler `lambda_start_transcription.handler`, the role
   above, env vars set. Add an **S3 trigger** on `storycraft-audio-bucket` with prefix
   `recordings/` and suffix `.wav`.
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

## Idempotency & errors

- Lambda A uses a deterministic job name (`story-{session_id}`) and replaces an
  existing job on re-upload, so a participant re-recording just overwrites.
- Lambda B uses `update_item`, so re-delivered events are harmless and only the
  transcription fields are touched.
- On a FAILED job, Lambda B writes `transcription_status = "FAILED"` plus
  `transcription_failure_reason` instead of a transcript.

## Where the transcript lives

The transcript ends up **only in DynamoDB** (`text_story` on the `session_id` item).
No output bucket is configured, so Amazon Transcribe keeps the raw result JSON in its
own service-managed bucket and Lambda B fetches it over HTTPS via the job's
`TranscriptFileUri`. Your `storycraft-audio-bucket` is only ever read from (the input
audio), never written to by this pipeline — so there is no risk of the output
re-triggering Lambda A.
