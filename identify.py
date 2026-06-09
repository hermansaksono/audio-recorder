import streamlit as st

logger = st.logger.get_logger("micronarratives")


def display_identity_page(text, editable):
    """
    Display the participant ID collection page.

    This function creates a Streamlit page that prompts the user to enter their
    participant ID. It first attempts to extract the ID from URL parameters, and
    if available, pre-fills the input field with this value.

    Args:
        text (str): Optional text shown before ID input box
        editable (bool): Whether the pre-filled ID should be editable

    Returns:
        str: The participant ID entered by the user or an empty string if none provided.
    """
    st.markdown("<h4>Participant Identification</h4>", unsafe_allow_html=True)

    # Get ID from URL parameter if available
    query_params = st.query_params
    default_id = query_params.get("participant_id", "")

    # Use a form to require explicit submission
    with st.form(key="participant_form"):
        if text:
            st.write(text)

        participant_id = st.text_input(
            "Enter your participant ID:",
            value=default_id,
            key="participant_id_input",
            disabled=not editable,
        )

        submit_button = st.form_submit_button("Confirm ID")

    if submit_button and participant_id.strip():
        return participant_id.strip()

    # Return None if no confirmed ID yet
    return None


def get_participant_id(llm_prompts):
    """
    Get participant ID and update session state accordingly.

    Based on settings in llm_prompts, this function obtains a participant ID either by:
    1. Using the session ID if participant ID is not required
    2. Collecting the ID from the user through the display_identity_page function

    Once a valid ID is obtained, the function updates the session state with the ID
    and advances the application state to the next step ("start").

    Args:
        llm_prompts (LLMConfig): Configuration object containing prompts, settings,
            and a flag indicating whether a participant ID is required.
    """

    if llm_prompts.require_participant_id:
        participant_id = display_identity_page(
            llm_prompts.participant_collection_text, llm_prompts.editable_participant_id
        )
    else:
        participant_id = st.session_state["session_id"]

    # Once participant ID is either provided by the user or set to the same
    # value as session ID, equal, set agentState to "start"
    if participant_id:
        logger.info(f"Participant ID: {participant_id}")
        st.session_state["participant_id"] = participant_id
        st.session_state["agentState"] = "microphoneCheck"
        st.rerun()
