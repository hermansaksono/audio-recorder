import streamlit as st
from streamlit_feedback import streamlit_feedback

import scenario
from utils import score_mappings

logger = st.logger.get_logger("micronarratives")


def reviewData(
    smith_client,
    chat_model,
    adaptation_prompt_template,
    one_shot,
    testing,
):
    """
    Procedure that governs the scenario review and selection by the user.

    It presents the scenarios generated in previous phases (and saved to
    st.session_state) and sets up the feedback / selection buttons and popovers.
    """

    ## If we're testing this function, the previous functions have set up the three
    # column structure yet and we don't have scenarios.
    ## --> we will set these up now.
    if testing:
        testing_reviewSetUp()

    num_scenarios = len(st.session_state["generated_scenarios"])

    # # If a scenario hasn't been selected yet, show all scenarios and feedback mechanisms
    # if st.session_state["selected_scenario_index"] is None:
    st.markdown("#### Review these examples to help you tell your own story")
    st.divider()

    scenario_columns = st.columns(num_scenarios)
    for col_index, column in enumerate(scenario_columns):
        with column:
              set_up_feedback(col_index, smith_client, one_shot)

    #     st.divider()

    #     st.chat_message("ai").write(
    #         "Please have a look at the examples above. "
    #         "Use the 👍 and 👎  to leave a rating and short comment on each of the "
    #         "examples. "
    #         "Then pick the one that you like the most to help you tell your own."
    #     )

    #     selection_columns = st.columns(num_scenarios)
    #     for index, column in enumerate(selection_columns):
    #         popover = column.popover(
    #             f"Pick example {index + 1}", use_container_width=True
    #         )
    #         scenario.scenario_selection(popover, index)

    # # and finally, assuming we have selected a scenario, let's move to the final state!
    # # Note that we ensured that the screen is free for any new content now as people had
    # # to click to select a scenario -- streamlit is starting with a fresh page
    # else:
        # great, we have a scenario selected, and all the key information is now in
        # t.session_state['scenario_package'], created in the
        # def click_selection_yes(button_num, scenario):

        # set the flow pointer accordingly
    st.session_state["agentState"] = "save"
    st.rerun()
    # scenario.finaliseScenario(chat_model, adaptation_prompt_template)


def set_up_feedback(scenario_index, smith_client, one_shot):
    st.header(f"Example {scenario_index + 1}")
    st.write(st.session_state["generated_scenarios"][scenario_index])

    # Once feedback is submitted, it cannot be changed
    # streamlit_feedback(
    #     feedback_type="thumbs",
    #     optional_text_label="[Optional] Please provide an explanation",
    #     align="center",
    #     key=f"column_{scenario_index + 1}_fb",
    #     disable_with_score=st.session_state["scenario_feedback"][scenario_index],
    #     on_submit=collectFeedback,
    #     args=(
    #         scenario_index,
    #         st.session_state["generated_scenarios"][scenario_index],
    #         smith_client,
    #         one_shot,
    #     ),
    # )


def collectFeedback(answer, column_index, scenario, smith_client, one_shot):
    """
    Submits user's feedback on specific scenario to langsmith; called as on_submit
    function for the respective streamlit feedback object.

    The payload combines the text of the scenario, user output, and answers. This
    function is intended to be called as 'on_submit' for the streamlit_feedback
    component.

    Parameters:
    answer (dict): Returned by streamlit_feedback function, contains "the user response,
    with the feedback_type, score and text fields"
    column_id (str): marking which column this belong too
    scenario (str): the scenario that users submitted feedback on
    """

    # Store feedback score and convert immediately to numerical equivalent for LangSmith
    st.session_state["scenario_feedback"][column_index] = answer["score"]
    num_score = score_mappings.get(answer["score"])

    if num_score is not None:
        ## combine all data that we want to store in Langsmith
        payload = f"{num_score} rating scenario: \n{scenario} \nBased on: \n{one_shot}"

        # Record the feedback with the formulated feedback type string
        # and optional comment
        smith_client.create_feedback(
            run_id=st.session_state["langsmith_run_id"],
            value=payload,
            key=f"column_{column_index + 1}_fb",
            score=num_score,
            comment=answer["text"],
        )
    else:
        logger.warning("Invalid feedback score was not submitted to LangSmith")


def testing_reviewSetUp():
    """
    Simple function that just sets up dummy scenario data, used when testing later flows
    of the process.
    """

    ## setting up testing code -- will likely be pulled out into a different procedure
    text_scenarios = {
        "s1": (
            "So, here's the deal. I've been really trying to get my head around "
            "this coding thing, specifically in langchain. I thought I'd share my "
            "struggle online, hoping for some support or advice. But guess what? My "
            "PhD students and postdocs, the very same people I've been telling how "
            "crucial it is to learn coding, just laughed at me! Can you believe it? "
            "It made me feel super ticked off and embarrassed. I mean, who needs "
            "that kind of negativity, right? So, I did what I had to do. I let all "
            "the postdocs go, re-advertised their positions, and had a serious chat "
            "with the PhDs about how uncool their reaction was to my coding "
            "struggles."
        ),
        "s2": (
            "So, here's the thing. I've been trying to learn this coding thing called "
            "langchain, right? It's been a real struggle, so I decided to share my "
            "troubles online. I thought my phd students and postdocs would understand, "
            "but instead, they just laughed at me! Can you believe that? After all the "
            "times I've told them how important it is to learn how to code. It made me "
            "feel really mad and embarrassed, you know? So, I did what I had to do. I "
            "told the postdocs they were out and had to re-advertise their positions. "
            "And I had a serious talk with the phds, telling them that laughing at my "
            "coding struggles was not cool at all."
        ),
        "s3": (
            "So, here's the deal. I've been trying to learn this coding language "
            "called langchain, right? And it's been a real struggle. So, I decided to "
            "post about it online, hoping for some support or advice. But guess what? "
            "My PhD students and postdocs, the same people I've been telling how "
            "important it is to learn coding, just laughed at me! Can you believe it? "
            "I was so ticked off and embarrassed. I mean, who does that? So, I did "
            "what any self-respecting person would do. I fired all the postdocs and "
            "re-advertised their positions. And for the PhDs? I had a serious talk "
            "with them about how uncool their reaction was to my coding struggles."
        ),
    }

    # insert the dummy text into the right st.sessionstate locations
    st.session_state.response_1 = {"output_scenario": text_scenarios["s1"]}
    st.session_state.response_2 = {"output_scenario": text_scenarios["s2"]}
    st.session_state.response_3 = {"output_scenario": text_scenarios["s3"]}
