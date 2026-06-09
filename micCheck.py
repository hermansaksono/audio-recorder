import streamlit as st
import streamlit.components.v1 as components

logger = st.logger.get_logger("micronarratives")


def show_mic_help_page():
    """
    Display a placeholder help page for microphone troubleshooting.
    """

    st.markdown("<h4>Microphone Help</h4>", unsafe_allow_html=True)
    st.write(
        "this is where I will write instructions on how to deal with a mic that is "
        "not working"
    )

    previous_state = st.session_state.get("previousAgentState", "microphoneCheck")
    if previous_state == "micHelp":
        previous_state = "microphoneCheck"

    if st.button("Try Again", use_container_width=True):
        st.session_state["agentState"] = previous_state
        st.rerun()

def checkmicrophone():
    """
    Prompts the user to record themselves saying "hello", plays it back,
    and provides a button to proceed once verified.
    """

    st.markdown(
        """
        <style>
        [data-testid="stAudioInput"] .e18uw4vz1 {
            height: auto !important;
            min-height: var(--sizes-largestElementHeight, 80px);
            overflow: visible !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    components.html(
        """
        <script>
        const doc = window.parent.document;
        const observer = new MutationObserver(() => {
            const container = doc.querySelector(
                '[data-testid="stAudioInput"]'
            );
            if (!container) return;
            const customMsg =
                'Microphone access was denied. Please allow '
                + 'microphone permissions in your browser '
                + 'settings and reload the page.';
            const spans = container.querySelectorAll('span');
            spans.forEach(span => {
                const text = span.textContent.trim().toLowerCase();
                if (text.includes('an error has occurred')
                    || text.includes('this app would like to use your microphone')) {
                    span.textContent = customMsg;
                    const link = span.parentElement.querySelector('a');
                    if (link) link.remove();
                }
            });
        });
        observer.observe(doc.body, { childList: true, subtree: true });
        </script>
        """,
        height=0,
    )

    st.markdown("<h4>Microphone Check</h4>", unsafe_allow_html=True)
    st.markdown(
        "Before we start, we need to make sure the mic is working "
        "because you will use it later.  \n"
        "Click on the mic button below and say *hello*. "
        "Then, follow the next instructions.  \n"
        '*Note: your web browser may ask for permission to use the mic. '
        'Please click "Allow".*'
    )

    audio_input = st.audio_input("", label_visibility="collapsed")

    audio_value = audio_input.getvalue() if audio_input else None

    if audio_value:
        logger.info("Mic check audio received")
        st.write("Does this sound clear?")
        st.audio(audio_value, format="audio/wav")

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            if st.button("No, I cannot hear my voice", use_container_width=True):
                logger.info("Microphone check rejected by user")
                st.session_state["previousAgentState"] = st.session_state.get(
                    "agentState", "microphoneCheck"
                )
                st.session_state["agentState"] = "micHelp"
                st.rerun()

        with col2:
            if st.button(
                "Yes, I can hear my voice", use_container_width=True
            ):
                logger.info("Microphone check confirmed by user")
                st.session_state["agentState"] = "customize"
                st.rerun()