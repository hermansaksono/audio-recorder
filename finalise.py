import datetime
import io
import json
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

    # if st.session_state.get("save") and table:
    if table:
        package = summarise_session_data(message_history)
        save_session_data(package, table)
        logger.info("data saved")
        # st.session_state.agentState = "final"
        # st.rerun()
    else:
        logger.info("data not saved")

    st.session_state["agentState"] = "final"
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

    # --- Visible 10-minute countdown timer ---
    MAX_RECORDING_SECONDS = 10 * 60  # 10 minutes
    components.html(
        f"""
        <div id="timer" style="font-size:1.4rem; font-weight:600; text-align:center;
                                padding:8px 0; font-family:monospace;">
            Time remaining: 10:00 (starts when recording starts)
        </div>
        <script>
            (() => {{
                let total = {MAX_RECORDING_SECONDS};
                let tick = null;
                let started = false;
                const el = document.getElementById('timer');

                function render() {{
                    const m = Math.floor(total / 60);
                    const s = total % 60;
                    el.textContent = 'Time remaining: ' + m + ':' + String(s).padStart(2, '0');
                }}

                function startCountdown() {{
                    if (started) return;
                    started = true;
                    render();
                    tick = setInterval(() => {{
                        total--;
                        if (total <= 0) {{
                            clearInterval(tick);
                            el.textContent = '\u23f0 Time is up \u2014 please stop recording';
                            el.style.color = 'red';
                            return;
                        }}
                        render();
                    }}, 1000);
                }}

                function attachToRecorderButton() {{
                    const hostDoc = window.parent && window.parent.document ? window.parent.document : document;
                    const buttons = Array.from(hostDoc.querySelectorAll('button'));
                    const recorderButton = buttons.find((btn) =>
                        (btn.innerText || '').includes('Click to record')
                    );

                    if (!recorderButton) return false;
                    recorderButton.addEventListener('click', startCountdown, {{ once: true }});
                    return true;
                }}

                if (!attachToRecorderButton()) {{
                    const attachRetry = setInterval(() => {{
                        if (attachToRecorderButton()) {{
                            clearInterval(attachRetry);
                        }}
                    }}, 300);
                }}
            }})();
        </script>
        """,
        height=50,
    )

    # --- Audio recorder ---
    # Auto-stops after 30 seconds of silence. The countdown timer above is the visual cue.
    # The pydub trim below enforces the 10-minute limit on the backend.
    st.caption("Press the microphone to start/stop recording.")
    _, mic_col, _ = st.columns([1, 1, 1])
    with mic_col:
        audio_bytes = audio_recorder(
            pause_threshold=30.0,       # stop after 30s of silence
            energy_threshold=0.01,      # real silence detection
            sample_rate=44100,
            text="",
        )

    if audio_bytes:
        # --- Server-side safety trim to 10 minutes (pydub) ---
        MAX_DURATION_MS = MAX_RECORDING_SECONDS * 1000
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
        if len(audio_segment) > MAX_DURATION_MS:
            audio_segment = audio_segment[:MAX_DURATION_MS]
            trimmed_buffer = io.BytesIO()
            audio_segment.export(trimmed_buffer, format="wav")
            audio_bytes = trimmed_buffer.getvalue()
            logger.info("Audio trimmed to 10 minutes")

        bucket_name = st.secrets.get("S3_BUCKET_NAME")
        key = f"{st.session_state['session_id']}/audio.wav"

        bucket.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=audio_bytes,
            ContentType="audio/wav"
        )
        logger.info("audio was saved")
        st.session_state["Audio_Story"] = audio_bytes
        preview_bytes = create_audio_preview(audio_bytes, max_seconds=10)
        st.audio(preview_bytes, format="audio/wav")

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
        st.write(text)


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
