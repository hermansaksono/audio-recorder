import streamlit as st
import streamlit.components.v1 as components

logger = st.logger.get_logger("micronarratives")


def show_mic_help_page():
    """
    Display microphone troubleshooting instructions. Lets the user try again
    after fixing the issue, or, as a last resort, stop participation if the
    microphone cannot be made to work.
    """

    st.markdown("<h4>Microphone Help</h4>", unsafe_allow_html=True)
    st.markdown(
        "Sorry, it looks like the microphone isn't working. The microphone is "
        "needed to take part, so let's try to fix it. Please go through the steps "
        "below, then try again."
    )

    st.markdown(
        "**1. Allow microphone access**  \n"
        "If your browser asked for permission, click *Allow*. If you blocked it "
        "earlier, click the lock (🔒) or microphone (🎤) icon in the address bar, "
        "set the microphone to *Allow*, and reload the page."
    )
    st.markdown(
        "**2. Check the correct microphone is selected**  \n"
        "If you have more than one microphone (for example, a headset and a "
        "built-in mic), make sure the one you want to use is chosen in your "
        "browser or computer sound settings."
    )
    st.markdown(
        "**3. Check the microphone itself**  \n"
        "Make sure it is plugged in, not muted, and that the volume is turned up. "
        "If you can, try speaking a little louder or moving closer to the mic."
    )

    st.divider()

    previous_state = st.session_state.get("previousAgentState", "micCheck")
    if previous_state == "micHelp":
        previous_state = "micCheck"

    if st.button("Try Again", use_container_width=True):
        logger.info("User retrying microphone check from help page")
        st.session_state["agentState"] = previous_state
        st.session_state.pop("confirmStopParticipation", None)
        st.rerun()

    st.markdown(
        "<p style='margin-top:1.5rem; color:gray;'>Still not working after trying "
        "the steps above?</p>",
        unsafe_allow_html=True,
    )

    if not st.session_state.get("confirmStopParticipation", False):
        if st.button(
            "I can't get my microphone to work",
            use_container_width=True,
        ):
            st.session_state["confirmStopParticipation"] = True
            st.rerun()
    else:
        st.warning(
            "Because the microphone is required to take part, ending here means "
            "you will not be able to continue this session. Are you sure?"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Go back", use_container_width=True):
                st.session_state["confirmStopParticipation"] = False
                st.rerun()
        with col2:
            if st.button(
                "Yes, stop participation",
                use_container_width=True,
                type="primary",
            ):
                logger.info("User stopped participation from microphone help page")
                st.session_state.pop("confirmStopParticipation", None)
                st.session_state["agentState"] = "sessionEnded"
                st.rerun()


def show_session_ended_page():
    """
    Final screen shown when a participant stops because the microphone could
    not be made to work.
    """

    st.markdown("<h4>Session ended</h4>", unsafe_allow_html=True)
    st.markdown(
        "Thank you for your time. Because the microphone is needed to take part "
        "and we weren't able to get it working, your participation ends here.  \n\n"
        "If you'd like to try again later, close this tab and reopen the link from "
        "a device with a working microphone. If you continue to have trouble, "
        "please contact the research team."
    )

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
                    "agentState", "micCheck"
                )
                st.session_state["agentState"] = "micHelp"
                st.rerun()

        with col2:
            if st.button(
                "Yes, I can hear my voice", use_container_width=True
            ):
                logger.info("Microphone check confirmed by user")
                st.session_state["agentState"] = "record"
                st.rerun()