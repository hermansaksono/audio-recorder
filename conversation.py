import streamlit as st


def getData(llm_prompts, conversation_chain, msgs):
    """Collects answers to main questions from the user.

    The conversation flow is stored in the msgs variable (which acts as the persistent
    langchain-streamlit memory for the bot). The prompt for LLM must be set up to
    return "FINISHED" when all data is collected.

    Parameters:
    testing: bool variable that will insert a dummy conversation instead of engaging
    with the user

    Returns:
    Nothing returned as all data is stored in msgs.
    """

    st.markdown("#### Collecting the details of your story")
    messages_container = st.container(border=True)
    chat_input = st.chat_input()

    ## if this is the first run, set up the intro
    if len(msgs.messages) == 0:
        msgs.add_ai_message(llm_prompts.questions_intro)

    # as Streamlit refreshes page after each input, we have to refresh all messages.
    # in our case, we are just interested in showing the last AI-Human turn of the
    # conversation for simplicity

    last_message = msgs.messages[-1:]

    for msg in last_message:
        if msg.type == "ai":
            with messages_container:
                st.chat_message(msg.type).write(msg.content)

    # If user inputs a new answer, generate new response and add into msgs
    if chat_input:
        # Note: new messages are saved to history automatically by Langchain during run
        with messages_container:
            # show that the message was accepted
            st.chat_message("human").write(chat_input)

            # generate the reply using langchain
            response = conversation_chain.invoke(input=chat_input)

            # the prompt must be set up to return "FINISHED" once all questions have
            # been answered
            # If finished, move the flow to summarisation, otherwise continue.
            if "FINISHED" in response["response"]:
                st.divider()
                st.chat_message("ai").write(llm_prompts.questions_outro)

                # Update state so that summarisation agent is called next
                st.session_state.agentState = "check"
                st.rerun()
            else:
                st.chat_message("ai").write(response["response"])

        # st.text(st.write(response))
