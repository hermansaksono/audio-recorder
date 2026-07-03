"""
Lambda B -- "store-transcript".

Triggered by an EventBridge rule on "Transcribe Job State Change" (COMPLETED or
FAILED). It recovers the session id from the job's media URI, reads the transcript
JSON, and writes ``text_story`` back onto the DynamoDB item with ``update_item`` so
the conversation app's data is left untouched.

Environment variables:
    TABLE_NAME     DynamoDB table (e.g. "micro-narrative-story-app-database").
    OUTPUT_BUCKET  S3 bucket that holds transcripts/{session_id}.json.
"""

import json
import os

import boto3

transcribe = boto3.client("transcribe")
s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def session_id_from_media_uri(uri):
    """
    Recover the session id from ``s3://{bucket}/recordings/{session_id}/audio.wav``.
    """
    without_scheme = uri.split("://", 1)[-1]
    parts = without_scheme.split("/")
    # parts == [bucket, "recordings", session_id, "audio.wav"]
    if len(parts) >= 4 and parts[1] == "recordings":
        return parts[2]
    return None


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

    # Read the transcript we asked Transcribe to write to our output bucket.
    output_key = f"transcripts/{session_id}.json"
    obj = s3.get_object(Bucket=OUTPUT_BUCKET, Key=output_key)
    payload = json.loads(obj["Body"].read())
    text = payload["results"]["transcripts"][0]["transcript"]

    update_item(session_id, text_story=text, status="COMPLETED")
