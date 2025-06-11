import streamlit as st

logger = st.logger.get_logger("micronarratives")


def checkMessages(message_history):
    """
    Check the conversation between the AI and participant for content which should be
    flagged. If this is present, load a page which prevents further interaction with the
    app.
    Args:
        message_history (StreamlitChatMessageHistory): message history between the AI
            and participant
    """

    safety_check_passed = review_for_safety(message_history)

    if safety_check_passed:
        logger.info("Safety check passed, proceeding to summary + scenario generation")
        st.session_state["agentState"] = "summarise"
        st.rerun()
    else:
        show_safety_page()


def review_for_safety(message_history):
    """
    To be completed: a function to check the message history for content that should be
    brought to the attention of the study organisers.
    Args:
        message_history (StreamlitChatMessageHistory): message history between the AI
            and participant
    Returns:
        bool: whether the safety check has been passed
    """

    return True


def show_safety_page():
    """
    Holding page to be displayed after a failed safety check. It is not possible to
    interact with the app further once this page has been accessed.
    """

    safety_container = st.container()
    with safety_container:
        st.markdown("Example text here...")
