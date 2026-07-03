import streamlit as st

import micCheck
from recorder_services import (
    build_audio_key,
    create_bucket_link,
    create_database_link,
    fetch_session_data,
    process_recorded_audio,
    upload_audio_to_s3,
)

logger = st.logger.get_logger("micronarratives")

MAX_RECORDING_SECONDS = 10 * 60  # 10 minutes

# Labels for the storytelling points shown while the participant records.
SUMMARY_LABELS = {
    "aspirations": "Aspirations",
    "activity": "Activity",
    "location": "Location",
    "time": "Time",
    "companions": "Companions",
    "feelings": "Feelings",
    "takeaways": "Takeaways",
}


def initialiseAppPage():
    """Initialise the Streamlit page (title, icon, Arial font)."""
    st.set_page_config(page_title="Record Your Story", page_icon="🎙️")

    st.markdown(
        """
        <style>
        html, body, [class*="css"], [class*="st-"],
        .stApp, .stApp * {
            font-family: Arial, Helvetica, sans-serif !important;
        }
        .material-icons, .material-icons-outlined,
        [class*="material-symbols"],
        span[data-testid="stIconMaterial"],
        [data-testid*="ChatMessageAvatar"] * {
            font-family: "Material Symbols Rounded", "Material Symbols Outlined",
                         "Material Icons" !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("🎙️ Record Your Story")


def initialiseSessionState():
    """
    Read the identifiers from the URL and set up the recorder's session state. This app
    and the conversation app are opened as two separate links that carry the SAME
    identifiers, so they must be read the same way here as in the conversation app:
    Prolific's ``SESSION_ID`` / ``PROLIFIC_PID`` / ``STUDY_ID`` (lowercase accepted as a
    fallback for manually constructed links). ``session_id`` is required -- it is the
    DynamoDB primary key and drives the S3 upload location, so without it we cannot
    locate the participant's data or upload the audio to the right place.
    """
    query_params = st.query_params

    if "session_id" not in st.session_state:
        st.session_state["session_id"] = query_params.get("SESSION_ID") or (
            query_params.get("session_id")
        )
    if "participant_id" not in st.session_state:
        st.session_state["participant_id"] = query_params.get("PROLIFIC_PID") or (
            query_params.get("participant_id")
        )
    if "study_id" not in st.session_state:
        st.session_state["study_id"] = query_params.get("STUDY_ID") or (
            query_params.get("study_id")
        )
    if "prolific_pid" not in st.session_state:
        st.session_state["prolific_pid"] = query_params.get("PROLIFIC_PID") or (
            query_params.get("prolific_pid")
        )

    if "agentState" not in st.session_state:
        st.session_state["agentState"] = "micCheck"

    # The participant's storytelling points, fetched from DynamoDB once.
    if "summary_answers" not in st.session_state:
        st.session_state["summary_answers"] = None

    if "Audio_Story" not in st.session_state:
        st.session_state["Audio_Story"] = None
    if "Audio_Story_Preview" not in st.session_state:
        st.session_state["Audio_Story_Preview"] = None


def loadSummaryAnswers(table):
    """Fetch and cache this session's storytelling points from DynamoDB."""
    if st.session_state["summary_answers"] is not None:
        return

    item = fetch_session_data(table, st.session_state["session_id"])
    st.session_state["summary_answers"] = (item or {}).get("summary_answers", {})


def render_summary_points():
    """Show the storytelling points so the participant can refer to them while telling
    their story."""
    summary_answers = st.session_state.get("summary_answers") or {}
    if not summary_answers:
        return

    st.markdown("**Here are some aspects of your story.**")
    for field, content in summary_answers.items():
        label = SUMMARY_LABELS.get(field, field.capitalize())
        st.markdown(f"- **{label}**: {content}")


def display_record_page():
    """Show the storytelling points and the recording widget."""
    render_summary_points()

    st.markdown(
        "**Now that you have the storytelling points, you can bring your story to "
        "life. Please tell it out loud in your own words, just like you would if "
        "you were sharing it with a friend or family member who's never heard it "
        "before.**"
    )

    st.divider()

    st.markdown(
        "Click on the microphone icon below to record your story. "
        "When you are done, click on the button again.  \n"
        "Your web browser may ask for permission to use the mic. "
        'Please click "Allow".  \n'
        "*Note: recording will automatically stop after 10 minutes.*"
    )

    audio_input = st.audio_input("", label_visibility="collapsed")
    audio_bytes = audio_input.getvalue() if audio_input else None

    if audio_bytes:
        process_recorded_audio(audio_bytes, MAX_RECORDING_SECONDS)


def display_preview_page(bucket):
    """Play back a 10-second preview and, once confirmed, upload the audio to S3."""
    st.markdown("<h4>You have recorded your own story</h4>", unsafe_allow_html=True)

    if st.session_state.get("Audio_Story_Preview"):
        st.markdown(
            "Play your story below to make sure it sounds fine. "
            "This preview is just the first 10 seconds of your recording. "
            "The full recording will be saved, don't worry."
        )
        st.audio(st.session_state["Audio_Story_Preview"], format="audio/wav")
    else:
        st.write("No audio preview is available yet.")

    st.divider()
    st.write("Can you hear your recording?")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("No, I cannot hear my recording", use_container_width=True):
            logger.info("Audio preview rejected by user")
            st.session_state["previousAgentState"] = "record"
            st.session_state["agentState"] = "micHelp"
            st.rerun()

    with col2:
        if st.button("Yes, I can hear my recording", use_container_width=True):
            logger.info("Audio preview confirmed by user")
            key = build_audio_key(st.session_state["session_id"])
            with st.spinner("Saving your story..."):
                uploaded = upload_audio_to_s3(
                    st.session_state["Audio_Story"], bucket, key
                )
            if uploaded:
                st.session_state["agentState"] = "done"
            else:
                st.session_state["agentState"] = "uploadFailed"
            st.rerun()


def display_done_page():
    """Terminal congratulations screen."""
    st.markdown("<h2>🎉 Congratulations!</h2>", unsafe_allow_html=True)
    st.markdown("You have finished this experience! Thank you for sharing your story.")


def display_upload_failed_page():
    """Shown if the S3 upload failed; lets the participant retry."""
    st.error(
        "Something went wrong while saving your recording. Please try again. "
        "If the problem continues, contact the research team."
    )
    if st.button("Try saving again", use_container_width=True):
        st.session_state["agentState"] = "preview"
        st.rerun()


def display_missing_session_page():
    """Shown when the app is opened without a session id in the URL."""
    st.error(
        "This recording link is missing its session information, so we can't record "
        "your story here. Please make sure you opened the exact link you were given "
        "(it should include your session details). If the problem continues, contact "
        "the research team."
    )


if __name__ == "__main__":
    initialiseAppPage()
    initialiseSessionState()

    bucket = create_bucket_link()
    table = create_database_link()

    if not st.session_state.get("session_id"):
        display_missing_session_page()
    else:
        loadSummaryAnswers(table)

        match st.session_state["agentState"]:
            case "micCheck":
                micCheck.checkmicrophone()
            case "micHelp":
                micCheck.show_mic_help_page()
            case "sessionEnded":
                micCheck.show_session_ended_page()
            case "record":
                display_record_page()
            case "preview":
                display_preview_page(bucket)
            case "uploadFailed":
                display_upload_failed_page()
            case "done":
                display_done_page()
