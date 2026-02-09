import streamlit as st

logger = st.logger.get_logger("micronarratives")

def checkmicrophone():
    """
    Prompts the user to record themselves saying "hello", plays it back,
    and provides a button to proceed once verified.
    """

    st.markdown("#### Microphone Check")
    st.markdown(
        "**Mic check:** Please record yourself saying *hello* to test the mic."
    )

    audio_value = st.audio_input("Record a voice message")

    if audio_value:
        logger.info("Mic check audio received")
        st.write("Does this sound clear?")
        st.audio(audio_value)
        
        # Add a visual separator for better UI
        st.divider()

        # Confirmation button to advance state
        if st.button("I can hear my voice", type="primary", use_container_width=True):
            logger.info("Microphone check confirmed by user")
            st.session_state["agentState"] = "customize"
            st.rerun()