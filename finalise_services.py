import datetime
import io
import json
import threading
import time

import requests
import streamlit as st
from langsmith import traceable
from pydub import AudioSegment

from utils import score_mappings

logger = st.logger.get_logger("micronarratives")


def create_audio_preview(wav_bytes, max_seconds=10):
    try:
        audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
        preview = audio[: max_seconds * 1000]
        preview_buffer = io.BytesIO()
        preview.export(preview_buffer, format="wav")
        return preview_buffer.getvalue()
    except Exception as exc:
        logger.warning(f"Unable to create audio preview: {exc}")
        return wav_bytes


@traceable
def summarise_session_data(message_history):
    """
    Collates a summary of all the data from this interaction with a user. If LangSmith
    is enabled, the contents of the summarised package will be stored in LangSmith.
    Args:
        message_history (StreamlitChatMessageHistory): chat history
    Returns:
        dict: data package to be placed in the database
    """

    # Combine scenario text and all user feedback (converted to numerical where
    # appropriate) into single dataset
    scenarios_with_feedback = [
        {"text": scenario, "feedback": feedback, "judgement": judgement}
        for scenario, feedback, judgement in zip(
            st.session_state["generated_scenarios"],
            [score_mappings.get(fb) for fb in st.session_state["scenario_feedback"]],
            st.session_state["scenario_judgement"],
            strict=True,
        )
    ]

    # Note: two different formats of the message history are saved, to better suit
    # different analysis methods after data collection
    scenario_package = {
        "session_id": str(st.session_state["session_id"]),
        "participant_id": str(st.session_state["participant_id"]),
        "langsmith_session_id": str(st.session_state["langsmith_run_id"]),
        "completion_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "all_scenario": st.session_state["generated_scenarios"],
        "summary_answers": st.session_state["summary_answers"],
        "text_story": st.session_state.get("Text_Story", ""),
        "chat_history": [(m.type, m.content) for m in message_history.messages],
        "chat_history_single_string": str(message_history),
        # "user_story": st.session_state.get("user_feedback", ""),
    }

    logger.info(f"Prepared scenario package: {json.dumps(scenario_package, indent=4)}")

    return scenario_package


def save_session_data(package, table):
    """
    Saves the session data to a connected database.
    Args:
        package (dict): a dict of data to be stored in the database
        table (DynamoDB.Table): a DynamoDB table where the data should be stored
    """

    try:
        table.put_item(Item=package)
    except Exception as e:
        logger.error(f"Unable to write to {table.table_name}:\n\t{e}")


def transcribe_saved_audio(transcribe):
    """
    Transcribe the saved audio file from S3 and store the transcript in session state.
    Waits for any in-progress S3 upload to complete before starting the transcription
    job, since AWS Transcribe reads the file directly from S3.
    """

    if st.session_state.get("Text_Story"):
        return st.session_state["Text_Story"]

    # Ensure the background S3 upload has finished before we ask Transcribe to read it.
    upload_thread = st.session_state.get("_s3_upload_thread")
    if upload_thread is not None and upload_thread.is_alive():
        logger.info("Waiting for S3 upload to complete before transcribing...")
        upload_thread.join()
        logger.info("S3 upload finished; proceeding with transcription")

    bucket_name = st.secrets.get("S3_BUCKET_NAME")
    key = f"{st.session_state['session_id']}/audio.wav"

    if not transcribe or not bucket_name:
        logger.info("Transcription skipped because Transcribe or S3 is not configured")
        st.session_state["Text_Story"] = ""
        return ""

    s3_uri = f"s3://{bucket_name}/{key}"
    job_name = f"onefile-{int(time.time())}"

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode="en-US",
        MediaFormat="wav",
        Media={"MediaFileUri": s3_uri},
    )

    text = None
    while True:
        job = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = job["TranscriptionJob"]["TranscriptionJobStatus"]

        if status == "COMPLETED":
            url = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
            text = requests.get(url).json()["results"]["transcripts"][0]["transcript"]
            break

        if status == "FAILED":
            raise RuntimeError(
                job["TranscriptionJob"].get("FailureReason", "Transcribe failed")
            )

        time.sleep(2)

    st.session_state["Text_Story"] = text
    logger.info("Transcription complete!")
    return text


def _upload_audio_to_s3(audio_bytes, bucket, bucket_name, key):
    """Upload audio bytes to S3 in a background thread."""
    try:
        bucket.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=audio_bytes,
            ContentType="audio/wav",
        )
        logger.info("Audio saved to S3 in background")
    except Exception as exc:
        logger.error(f"Background S3 upload failed: {exc}")


def process_recorded_audio(audio_bytes, bucket, max_recording_seconds):
    """
    Process the recorded audio, save it, generate a short preview, and route the
    user to a separate preview page.

    Trimming and preview generation happen synchronously so the preview page can
    render immediately. The (potentially slow) S3 upload runs in a background
    thread so the user is not blocked waiting for the network.
    """

    max_duration_ms = max_recording_seconds * 1000
    audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
    if len(audio_segment) > max_duration_ms:
        audio_segment = audio_segment[:max_duration_ms]
        trimmed_buffer = io.BytesIO()
        audio_segment.export(trimmed_buffer, format="wav")
        audio_bytes = trimmed_buffer.getvalue()
        logger.info("Audio trimmed to 10 minutes")

    # Build the 10-second preview before navigating away.
    preview_bytes = create_audio_preview(audio_bytes, max_seconds=10)

    st.session_state["Audio_Story"] = audio_bytes
    st.session_state["Audio_Story_Preview"] = preview_bytes
    st.session_state["Text_Story"] = ""
    st.session_state["_final_processing_complete"] = False

    # Upload to S3 in the background so the user reaches the preview page immediately.
    # The thread is stored in session state so transcription can wait for it to finish.
    bucket_name = st.secrets.get("S3_BUCKET_NAME")
    key = f"{st.session_state['session_id']}/audio.wav"
    if bucket and bucket_name:
        upload_thread = threading.Thread(
            target=_upload_audio_to_s3,
            args=(audio_bytes, bucket, bucket_name, key),
            daemon=True,
        )
        upload_thread.start()
        st.session_state["_s3_upload_thread"] = upload_thread
        logger.info("S3 audio upload started in background")
    else:
        st.session_state["_s3_upload_thread"] = None
        logger.info("S3 upload skipped (bucket not configured)")

    st.session_state["agentState"] = "audioPreview"
    st.rerun()
