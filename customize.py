import streamlit as st

logger = st.logger.get_logger("micronarratives")


def display_customize_page(text, editable):
    """
    Display the customize request collection page.

    This function creates a Streamlit page that prompts the user to enter their
    request for the customization of the main persona.

    Args:
        text (str): Optional text shown before ID input box
        editable (bool): Whether the pre-filled ID should be editable

    Returns:
        str: The customization request entered by the user or an empty string if
            none provided.
    """
    st.markdown("#### Personalize your chatbot")

    # Use a form to require explicit submission
    with st.form(key="participant_form"):
        if text:
            st.write(text)

        participant_id = st.text_input(
            "You can customize your chatbot. How would you like the chatbot to talk?\n"
            'For example:\n\n"Please make my chatbot more cheerful"',
            value="",
            key="participant_customization_request",
            disabled=not editable,
        )

        submit_button = st.form_submit_button("Confirm request")

    if submit_button and participant_id.strip():
        return participant_id.strip()

    # Return None if no confirmed ID yet
    return None


def get_customize_request(llm_prompts):
    """
    Get customization request and update session state accordingly.

    Based on settings in llm_prompts, this function obtains a customization request by
    Collecting the ID from the user through the display_identity_page function

    Once a valid request is obtained, the function updates the session state with the 
    customization and advances the application state to the next step ("start").

    Args:
        llm_prompts (LLMConfig): Configuration object containing prompts, settings,
            and a flag indicating whether a participant ID is required.
    """

    customize_request = display_customize_page(
        llm_prompts.participant_collection_text, llm_prompts.editable_participant_id
    )

    # Once customization requese is provided by the user or set to the none
    if customize_request:
        logger.info(f"Customize Request: {customize_request}")
        st.session_state["customize_request"] = customize_request
        llm_prompts.questions_prompt_template = (
            llm_prompts.update_questions_prompt_template(customize_request)
        )
        st.session_state["agentState"] = "start"
        st.rerun()