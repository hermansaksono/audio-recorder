import datetime
import io
import json
import threading
import time

import requests
import streamlit as st
import streamlit.components.v1 as components
from audio_recorder_streamlit import audio_recorder
from pydub import AudioSegment
from langsmith import traceable

from utils import score_mappings

logger = st.logger.get_logger("micronarratives")
# if you want to save the final scenario please make save = False
# and uncomment the statements included below
save = True


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


def saveScenario(message_history, table):
    """
    Manages the process of saving the data related to the user's interaction with the
    app, and presenting the final scenario to the user.
    Args:
        message_history (StreamlitChatMessageHistory): chat history
        table (DynamoDB.Table | None): a DynamoDB table where the data should be stored
    """

    st.session_state["agentState"] = "final"

    # Save in the background so the final page can appear immediately.
    if table:
        package = summarise_session_data(message_history)
        save_thread = threading.Thread(
            target=save_session_data,
            args=(package, table),
            daemon=True,
        )
        save_thread.start()
        logger.info("Data save started in background")
    else:
        logger.info("data not saved")

    st.rerun()
    


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
        "all_scenario":st.session_state["generated_scenarios"],
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
        job = transcribe.get_transcription_job(
            TranscriptionJobName=job_name
        )
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


def process_recorded_audio(audio_bytes, bucket, transcribe, max_recording_seconds):
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


def display_audio_preview_page():
    """
    Displays a separate page with a 10-second preview of the user's recording,
    and asks whether they can hear the playback before proceeding to save.
    """

    st.markdown("#### Audio Preview")

    if st.session_state.get("Audio_Story_Preview"):
        st.write("Here are the first 10 seconds of your recording.")
        st.audio(st.session_state["Audio_Story_Preview"], format="audio/wav")
    else:
        st.write("No audio preview is available yet.")

    st.divider()
    st.write("Can you hear your recording?")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("I cannot hear my recording", use_container_width=True):
            logger.info("Audio preview rejected by user")
            st.session_state["agentState"] = "micHelp"
            st.rerun()

    with col2:
        if st.button("I can hear my recording", type="primary", use_container_width=True):
            logger.info("Audio preview confirmed by user")
            st.session_state["agentState"] = "audioConfirmed"
            st.rerun()


def display_save_congratulations_page(message_history, table, transcribe):
    """
    Transcribes the saved audio, saves the session data, and displays a
    congratulations message.
    """

    if not st.session_state.get("_final_processing_complete", False):
        with st.spinner("Finalizing your story, generating the transcript, and saving everything..."):
            transcribe_saved_audio(transcribe)
            if table:
                package = summarise_session_data(message_history)
                save_session_data(package, table)
                logger.info("Data saved after transcription")
            else:
                logger.info("Data not saved")
            st.session_state["_final_processing_complete"] = True
            st.rerun()

    st.markdown("## :tada: Congratulations!")
    st.markdown(
        "You have finished this experience! Thank you for sharing your story."
    )



def display_completion_page(bucket, transcribe):
    """
    Displays the final scenario to the user.
    """
    generated_scenarios = st.session_state["generated_scenarios"]
    scenario_columns = st.columns(len(generated_scenarios))

    for col_index, column in enumerate(scenario_columns):
        with column:
            st.header(f"Example {col_index + 1}")
            st.write(generated_scenarios[col_index])

    st.markdown("**Here are some aspects of your story.**")
    labels = {
        "aspirations": "Aspirations",
        "activity": "Activity",
        "location": "Location",
        "time": "Time",
        "companions": "Companions",
        "feelings": "Feelings",
        "takeaways": "Takeaways"
    }

    for field, content in st.session_state["summary_answers"].items():
        label = labels.get(field, field.capitalize())
        st.markdown(f"- **{label}**: {content}")

    st.markdown(
        "**Now that you’ve seen the bullet points, "
        "bring the story to life—tell it out loud in your own words, "
        "just like you would if you were sharing it with a friend or "
        "family member who’s never heard it before.**"
    )

    MAX_RECORDING_SECONDS = 10 * 60  # 10 minutes

    # --- Phase 1: show a Start button; clicking it reruns into the active recorder view ---
    # The recorder itself is configured to auto-start on load, so the timer and
    # recording begin together without requiring a second click on the mic button.
    if not st.session_state.get("recording_started", False):
        _, btn_col, _ = st.columns([1, 1, 1])
        with btn_col:
            if st.button(
                "🎙️ Start Recording",
                type="primary",
                use_container_width=True,
            ):
                st.session_state["recording_started"] = True
                st.rerun()
        audio_bytes = None
    else:
        # --- Phase 2: timer auto-starts on render; mic is now visible ---
        components.html(
            f"""
            <div id="timer" style="font-size:1.4rem; font-weight:600; text-align:center;
                                    padding:8px 0; font-family:monospace;">
                Time remaining: 10:00
            </div>
            <script>
                (() => {{
                    let total = {MAX_RECORDING_SECONDS};
                    const el = document.getElementById('timer');
                    function render() {{
                        const m = Math.floor(total / 60);
                        const s = total % 60;
                        el.textContent = 'Time remaining: ' + m + ':' + String(s).padStart(2, '0');
                    }}
                    render();
                    const tick = setInterval(() => {{
                        total--;
                        if (total <= 0) {{
                            clearInterval(tick);
                            el.textContent = '\u23f0 Time is up \u2014 please stop recording';
                            el.style.color = 'red';
                            return;
                        }}
                        render();
                    }}, 1000);
                }})();
            </script>
            """,
            height=50,
        )

        # --- Audio recorder ---
        # Auto-starts when shown, auto-stops after 30 s of silence; pydub enforces
        # the 10-min limit on the backend.
        st.caption("Recording starts automatically. Press the microphone button to stop when you are done.")
        _, mic_col, _ = st.columns([1, 1, 1])
        with mic_col:
            audio_bytes = audio_recorder(
                pause_threshold=30.0,
                energy_threshold=0.01,
                sample_rate=44100,
                auto_start=True,
                text="",
            )

    if audio_bytes:
        st.session_state["recording_started"] = False  # reset for any future reruns
        process_recorded_audio(
            audio_bytes,
            bucket,
            transcribe,
            MAX_RECORDING_SECONDS,
        )


#     user_feedback = st.text_area(
#     "Now it's your turn to write a story:",
#     value=st.session_state.get("user_feedback", "")
# )

#     if st.button("Submit"):
#         st.session_state["save"] = True
#         st.session_state["user_feedback"] = user_feedback
#         st.rerun()


# def display_final_page():
#     """
#     Displays the final scenario to the user.
#     """
#     st.markdown(":tada: Yay! :tada:")
#     st.markdown(
#         "You've now completed the interaction and written your own story! "
#     )
#     st.markdown(
#         "**Here is your story!** "
#     )

#     st.markdown(
#         st.session_state.get("user_feedback", "")
#     )
