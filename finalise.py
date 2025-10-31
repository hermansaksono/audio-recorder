import datetime
import json

import streamlit as st
from langsmith import traceable

from utils import score_mappings

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

    # if st.session_state.get("save") and table:
    if table:
        package = summarise_session_data(message_history)
        save_session_data(package, table)
        logger.info("data saved")
        # st.session_state.agentState = "final"
        # st.rerun()
    else:
        logger.info("data not saved")

    display_completion_page(table)
    


@traceable
def summarise_session_data(message_history):
    """
    Collates a summary of all the data from this interaction with a user. If LangSmith
    is enabled, the contents of the summarised package will be stored in LangSmith.
    Args:
        message_history (StreamlitChatMessageHistory): chat history
    Returns:
        dict: data package to be placed in the database
    """

    # Combine scenario text and all user feedback (converted to numerical where
    # appropriate) into single dataset
    scenarios_with_feedback = [
        {"text": scenario, "feedback": feedback, "judgement": judgement}
        for scenario, feedback, judgement in zip(
            st.session_state["generated_scenarios"],
            [score_mappings.get(fb) for fb in st.session_state["scenario_feedback"]],
            st.session_state["scenario_judgement"],
            strict=True,
        )
    ]

    # Note: two different formats of the message history are saved, to better suit
    # different analysis methods after data collection
    scenario_package = {
        "session_id": str(st.session_state["session_id"]),
        "participant_id": str(st.session_state["participant_id"]),
        "langsmith_session_id": str(st.session_state["langsmith_run_id"]),
        "completion_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "all_scenario":st.session_state["generated_scenarios"],
        "summary_answers": st.session_state["summary_answers"],
        "chat_history": [(m.type, m.content) for m in message_history.messages],
        "chat_history_single_string": str(message_history),
        # "user_story": st.session_state.get("user_feedback", ""),
    }

    logger.info(f"Prepared scenario package: {json.dumps(scenario_package, indent=4)}")

    return scenario_package


def save_session_data(package, table):
    """
    Saves the session data to a connected database.
    Args:
        package (dict): a dict of data to be stored in the database
        table (DynamoDB.Table): a DynamoDB table where the data should be stored
    """

    try:
        table.put_item(Item=package)
    except Exception as e:
        logger.error(f"Unable to write to {table.table_name}:\n\t{e}")


def display_completion_page(table):
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

    st.markdown("**Now that you’ve seen the bullet points, " 
    "bring the story to life—tell it out loud in your own words, " 
    "just like you would if you were sharing it with a friend or " 
    "family member who’s never heard it before.**")

    audio_value = st.audio_input("Start Recording")

    if(audio_value):
        st.session_state["Audio_Story"] = audio_value
        st.audio(audio_value)
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
