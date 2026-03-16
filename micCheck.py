import streamlit as st
from audio_recorder_streamlit import audio_recorder

logger = st.logger.get_logger("micronarratives")


def show_mic_help_page():
    """
    Display a placeholder help page for microphone troubleshooting.
    """

    st.markdown("#### Microphone Help")
    st.write(
        "this is where I will write instructions on how to deal with a mic that is not working"
    )

def checkmicrophone():
    """
    Prompts the user to record themselves saying "hello", plays it back,
    and provides a button to proceed once verified.
    """

    st.markdown("#### Microphone Check")
    st.markdown(
        "**Mic check:** Please record yourself saying *hello* to test the mic."
    )

    st.caption("Press the microphone to start/stop recording.")

    _, mic_col, _ = st.columns([1, 1, 1])
    with mic_col:
        audio_value = audio_recorder(
            pause_threshold=30.0,
            energy_threshold=0.01,
            sample_rate=44100,
            text="",
        )

    if audio_value:
        logger.info("Mic check audio received")
        st.write("Does this sound clear?")
        st.audio(audio_value, format="audio/wav")
        
        st.divider()

        # Place columns INSIDE the function and INSIDE the audio check
        col1, col2 = st.columns(2)

        with col1:
            if st.button("I cannot hear my voice", use_container_width=True):
                logger.info("Microphone check rejected by user")
                st.session_state["agentState"] = "micHelp"
                st.rerun()

        with col2:
            if st.button("I can hear my voice", type="primary", use_container_width=True):
                logger.info("Microphone check confirmed by user")
                st.session_state["agentState"] = "customize"
                st.rerun()