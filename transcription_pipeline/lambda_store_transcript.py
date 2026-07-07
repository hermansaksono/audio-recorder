"""
Lambda B -- "store-transcript".

Triggered by an EventBridge rule on "Transcribe Job State Change" (COMPLETED or
FAILED). It recovers the session id from the job's media URI, fetches the transcript
JSON from the ``TranscriptFileUri`` Amazon Transcribe returns, and writes
``text_story`` back onto the DynamoDB item with ``update_item`` so the conversation
app's data is left untouched.

The transcript lives only in DynamoDB -- Transcribe holds the raw JSON in its own
service-managed bucket (no output bucket is configured), and it is fetched over HTTPS
rather than from our S3 bucket.

Environment variables:
    TABLE_NAME  DynamoDB table (e.g. "micro-narrative-story-app-database").
"""

import json
import os
import urllib.request

import boto3

transcribe = boto3.client("transcribe")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def session_id_from_stem(stem):
    """
    Recover the session id from a folder/file stem of the form
    ``{participant_id}-{YYYYMMDD}-{HHMMSS}-{session_id}``. The participant id, date and
    time never contain "-", so everything after the third "-" is the session id (which
    may itself contain "-"). Returns None if the stem has too few fields.
    """
    fields = stem.split("-", 3)
    if len(fields) == 4:
        return fields[3]
    return None


def session_id_from_media_uri(uri):
    """
    Recover the session id from ``s3://{bucket}/{stem}/{stem}.wav``.
    """
    without_scheme = uri.split("://", 1)[-1]
    parts = without_scheme.split("/")
    # parts == [bucket, stem, "{stem}.wav"]
    if len(parts) >= 3:
        return session_id_from_stem(parts[1])
    return None


def fetch_transcript_text(transcript_file_uri):
    """Download the Transcribe result JSON and return the transcript text."""
    with urllib.request.urlopen(transcript_file_uri) as response:
        payload = json.loads(response.read())
    return payload["results"]["transcripts"][0]["transcript"]


def update_item(session_id, *, text_story=None, status, failure_reason=None):
    """
    Write only the transcription-related attributes onto the existing item. Using
    update_item (not put_item) keeps this idempotent and preserves everything the
    conversation app wrote.
    """
    set_parts = ["#status = :status"]
    names = {"#status": "transcription_status"}
    values = {":status": status}

    if text_story is not None:
        set_parts.append("#text = :text")
        names["#text"] = "text_story"
        values[":text"] = text_story

    if failure_reason is not None:
        set_parts.append("#reason = :reason")
        names["#reason"] = "transcription_failure_reason"
        values[":reason"] = failure_reason

    table.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    print(f"Updated session {session_id} with transcription_status={status}")


def handler(event, context):
    detail = event.get("detail", {})
    job_name = detail.get("TranscriptionJobName")
    status = detail.get("TranscriptionJobStatus")

    if not job_name:
        print("Event has no TranscriptionJobName; ignoring")
        return

    job = transcribe.get_transcription_job(TranscriptionJobName=job_name)[
        "TranscriptionJob"
    ]
    media_uri = job["Media"]["MediaFileUri"]
    session_id = session_id_from_media_uri(media_uri)
    if not session_id:
        print(f"Cannot recover session id from media URI: {media_uri}")
        return

    if status == "FAILED":
        reason = job.get("FailureReason", "unknown")
        update_item(session_id, status="FAILED", failure_reason=reason)
        return

    if status != "COMPLETED":
        print(f"Ignoring job {job_name} in status {status}")
        return

    text = fetch_transcript_text(job["Transcript"]["TranscriptFileUri"])
    # A completed job with a blank transcript means silence / no speech was detected
    # (e.g. a dead-air recording or a failed mic). Flag it so it is not mistaken for a
    # successful transcription -- an empty text_story otherwise looks identical to a
    # session that never recorded.
    status = "COMPLETED" if text.strip() else "EMPTY"
    update_item(session_id, text_story=text, status=status)
