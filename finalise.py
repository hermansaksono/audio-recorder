import datetime
import json

import streamlit as st
from langsmith import traceable

from utils import score_mappings

logger = st.logger.get_logger("micronarratives")


def saveScenario(message_history, table):
    """
    Manages the process of saving the data related to the user's interaction with the
    app, and presenting the final scenario to the user.
    Args:
        message_history (StreamlitChatMessageHistory): chat history
        table (DynamoDB.Table | None): a DynamoDB table where the data should be stored
    """

    package = summarise_session_data(message_history)

    if table:
        save_session_data(package, table)

    st.chat_message("ai").write(
        ":tada: Yay! :tada:"
        "You've now completed the interaction and hopefully found a story that "
        "you liked! "
        )
    # display_completion_page()


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
        # "initial_scenario": st.session_state["generated_scenarios"][
        #     st.session_state["selected_scenario_index"]
        # ],
        "all_scenario":st.session_state["generated_scenarios"],
        # "final_scenario": st.session_state["final_scenario"],
        "summary_answers": st.session_state["summary_answers"],
        # "scenarios": scenarios_with_feedback,
        "chat_history": [(m.type, m.content) for m in message_history.messages],
        "chat_history_single_string": str(message_history),
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


def display_completion_page():
    """
    Displays the final scenario to the user.
    """

    st.markdown(":tada: Yay! :tada:")
    st.markdown(
        "You've now completed the interaction and hopefully found a scenario that "
        "you liked! "
    )
