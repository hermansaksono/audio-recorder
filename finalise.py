import threading

import streamlit as st

from finalise_services import (
    process_recorded_audio,
    save_session_data,
    summarise_session_data,
    transcribe_saved_audio,
)

logger = st.logger.get_logger("micronarratives")
# if you want to save the final scenario please make save = False
# and uncomment the statements included below
save = True


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
            st.session_state["previousAgentState"] = st.session_state.get(
                "agentState", "audioPreview"
            )
            st.session_state["agentState"] = "micHelp"
            st.rerun()

    with col2:
        if st.button(
            "I can hear my recording", type="primary", use_container_width=True
        ):
            logger.info("Audio preview confirmed by user")
            st.session_state["agentState"] = "audioConfirmed"
            st.rerun()


def display_save_congratulations_page(message_history, table, transcribe):
    """
    Transcribes the saved audio, saves the session data, and displays a
    congratulations message.
    """

    if not st.session_state.get("_final_processing_complete", False):
        with st.spinner(
            "Finalizing your story, generating the transcript, and saving everything..."
        ):
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
        "**Now that you have the storytelling points, you can bring your story to "
        "life. Please tell it out loud in your own words, just like you would if "
        "you were sharing it with a friend or family member who’s never heard it "
        "before.**"
    )

    MAX_RECORDING_SECONDS = 10 * 60  # 10 minutes

    st.caption(
        "Use the microphone input below to record your story. When you stop "
        "recording, the app will save the first 10 seconds as a preview and trim "
        "anything over 10 minutes."
    )
    audio_input = st.audio_input("Record your story")
    audio_bytes = audio_input.getvalue() if audio_input else None

    if audio_bytes:
        process_recorded_audio(
            audio_bytes,
            bucket,
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
