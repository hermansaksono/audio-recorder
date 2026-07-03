"""
Lambda A -- "start-transcription".

Triggered by an S3 ``ObjectCreated`` event when the recorder app uploads an audio
file to ``recordings/{session_id}/audio.wav``. It recovers the session id from the
key and starts an asynchronous Amazon Transcribe job, then returns immediately -- it
does NOT poll for completion (that is Lambda B's job).

The job is started WITHOUT an output bucket, so Amazon Transcribe stores the raw
result in its own service-managed bucket and returns a ``TranscriptFileUri`` that
Lambda B fetches. Nothing transcript-related is written to our own S3 bucket.

Environment variables:
    LANGUAGE_CODE    Transcribe language code (default "en-US").
    JOB_NAME_PREFIX  Prefix for Transcribe job names (default "story-").
"""

import os
import urllib.parse

import boto3

transcribe = boto3.client("transcribe")

LANGUAGE_CODE = os.environ.get("LANGUAGE_CODE", "en-US")
JOB_NAME_PREFIX = os.environ.get("JOB_NAME_PREFIX", "story-")


def session_id_from_key(key):
    """
    Recover the session id from an audio key of the form
    ``recordings/{session_id}/audio.wav``. Returns None for any other layout.
    """
    parts = key.split("/")
    if len(parts) >= 3 and parts[0] == "recordings":
        return parts[1]
    return None


def job_name_for(session_id):
    """
    Build a deterministic Transcribe job name. Job names may only contain
    ``[0-9a-zA-Z._-]`` and be at most 200 characters, so unsupported characters are
    replaced. The session id is NOT recovered from the job name (Lambda B recovers it
    from the media URI instead), so this sanitisation is safe.
    """
    safe = "".join(c if (c.isalnum() or c in "._-") else "-" for c in session_id)
    return f"{JOB_NAME_PREFIX}{safe}"[:200]


def start_job(job_name, media_uri):
    kwargs = dict(
        TranscriptionJobName=job_name,
        LanguageCode=LANGUAGE_CODE,
        MediaFormat="wav",
        Media={"MediaFileUri": media_uri},
    )
    try:
        transcribe.start_transcription_job(**kwargs)
        print(f"Started transcription job {job_name} for {media_uri}")
    except transcribe.exceptions.ConflictException:
        # A job with this name already exists (e.g. the participant re-recorded).
        # Replace it so the latest audio wins.
        print(f"Job {job_name} already exists; replacing it")
        transcribe.delete_transcription_job(TranscriptionJobName=job_name)
        transcribe.start_transcription_job(**kwargs)


def handler(event, context):
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        if not key.endswith(".wav"):
            print(f"Skipping non-wav key: {key}")
            continue

        session_id = session_id_from_key(key)
        if not session_id:
            print(f"Skipping key with unexpected layout: {key}")
            continue

        media_uri = f"s3://{bucket}/{key}"
        start_job(job_name=job_name_for(session_id), media_uri=media_uri)
