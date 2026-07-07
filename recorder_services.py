import io
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3
import streamlit as st
from pydub import AudioSegment

logger = st.logger.get_logger("micronarratives")

# US Eastern *local* time (EST in winter, EDT in summer) for the upload timestamp.
EASTERN = ZoneInfo("America/New_York")


def build_audio_key(session_id, participant_id):
    """
    Build the S3 key for this session's recording, e.g.

        {stem}/{stem}.wav

    where ``stem`` is ``{participant_id}-{YYYYMMDD}-{HHMMSS}-{session_id}`` and the
    timestamp is US Eastern local time.

    The transcription pipeline recovers the ``session_id`` from this path to locate the
    DynamoDB item, so the layout is a shared contract (see ``transcription_pipeline``).
    ``session_id`` MUST stay last: the participant id is sanitised to remove hyphens and
    the date/time are hyphen-free, so the only structural hyphens are the three
    separators -- the pipeline treats everything after the third hyphen as the session
    id, which stays correct even if the session id itself contains hyphens.
    """
    now = datetime.now(EASTERN)
    date = now.strftime("%Y%m%d")
    time = now.strftime("%H%M%S")
    # Guarantee the participant id contributes no structural hyphens.
    pid = (participant_id or "unknown").replace("-", "_")
    stem = f"{pid}-{date}-{time}-{session_id}"
    return f"{stem}/{stem}.wav"


@st.cache_resource
def create_bucket_link():
    """
    Create and cache a boto3 S3 client. Returns None if no bucket is configured.
    """
    if bucket_name := st.secrets.get("S3_BUCKET_NAME"):
        client = boto3.client(
            service_name="s3",
            region_name=st.secrets.get("AWS_DEFAULT_REGION"),
            aws_access_key_id=st.secrets.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=st.secrets.get("AWS_SECRET_ACCESS_KEY"),
        )
        logger.info(f"Audio will be saved to {bucket_name}\n")
        return client

    logger.info("No bucket details provided\n")
    return None


@st.cache_resource
def create_database_link():
    """
    Create and cache a boto3 DynamoDB Table used to read this session's data (the
    storytelling points shown while the participant records). Returns None if no table
    is configured.
    """
    if table_name := st.secrets.get("DYNAMODB_TABLE_NAME"):
        resource = boto3.resource(
            service_name="dynamodb",
            region_name=st.secrets.get("AWS_DEFAULT_REGION"),
            aws_access_key_id=st.secrets.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=st.secrets.get("AWS_SECRET_ACCESS_KEY"),
        )
        logger.info(f"Reading session data from {table_name}\n")
        return resource.Table(table_name)

    logger.info("No database details provided\n")
    return None


def fetch_session_data(table, session_id):
    """
    Fetch this session's item from DynamoDB by its primary key (``session_id``).
    Returns the item dict, or None if the table is not configured or the item is
    missing.
    """
    if not table or not session_id:
        return None

    try:
        response = table.get_item(Key={"session_id": session_id})
    except Exception as exc:
        logger.error(f"Unable to read session {session_id} from DynamoDB: {exc}")
        return None

    return response.get("Item")


def create_audio_preview(wav_bytes, max_seconds=10):
    """Return the first ``max_seconds`` of the recording as WAV bytes for playback."""
    try:
        audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
        preview = audio[: max_seconds * 1000]
        preview_buffer = io.BytesIO()
        preview.export(preview_buffer, format="wav")
        return preview_buffer.getvalue()
    except Exception as exc:
        logger.warning(f"Unable to create audio preview: {exc}")
        return wav_bytes


def upload_audio_to_s3(audio_bytes, bucket, key):
    """
    Upload the recording to S3 at ``key``. Returns True on success.
    Uploads synchronously -- unlike the old combined app there is nothing else for the
    participant to do while this runs, and the transcription pipeline is triggered by
    this object landing in S3.
    """
    bucket_name = st.secrets.get("S3_BUCKET_NAME")
    if not bucket or not bucket_name:
        logger.info("S3 upload skipped (bucket not configured)")
        return False

    try:
        bucket.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=audio_bytes,
            ContentType="audio/wav",
        )
        logger.info(f"Audio saved to s3://{bucket_name}/{key}")
        return True
    except Exception as exc:
        logger.error(f"S3 upload failed: {exc}")
        return False


def process_recorded_audio(audio_bytes, max_recording_seconds):
    """
    Trim the recording to the maximum length and build a short preview, then store both
    in session state and route to the preview page. The S3 upload happens later, once
    the participant confirms the recording sounds right.
    """
    max_duration_ms = max_recording_seconds * 1000
    audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
    if len(audio_segment) > max_duration_ms:
        audio_segment = audio_segment[:max_duration_ms]
        trimmed_buffer = io.BytesIO()
        audio_segment.export(trimmed_buffer, format="wav")
        audio_bytes = trimmed_buffer.getvalue()
        logger.info("Audio trimmed to the maximum length")

    st.session_state["Audio_Story"] = audio_bytes
    st.session_state["Audio_Story_Preview"] = create_audio_preview(
        audio_bytes, max_seconds=10
    )
    st.session_state["agentState"] = "preview"
    st.rerun()
