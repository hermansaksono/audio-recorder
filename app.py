import os
import sys

import boto3
import streamlit as st
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.output_parsers.json import SimpleJsonOutputParser
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain_openai import ChatOpenAI
from langsmith import Client

import check
import conversation
import customize
import finalise
import identify
import micCheck
import review
import scenario
from llm_config import LLMConfig


def stateAgent(
    llm_prompts,
    chat_model,
    extraction_chain,
    smith_client,
    message_history,
    memory,
    table,
    bucket,
    transcribe,
):
    """
    Main flow function of the whole interaction -- keeps track of the system state and
    calls the appropriate procedure on each streamlit refresh.
    Args:
        llm_prompts (LLMConfig): class containing text and templates for the app
        chat_model (ChatOpenAI): OpenAI chat model
        smith_client (langsmith.Client): LangSmith client
        message_history (StreamlitChatMessageHistory): chat history, stored in Streamlit
            session state
        memory (ConversationBufferMemory): chat history
        table (DynamoDB.Table | None): a DynamoDB table where the data will be stored
    """

    # Use dummy data
    testing = False

    if testing:
        logger.info(
            f"Running stateAgent loop\tsession state: {st.session_state['agentState']}"
        )

    conversation_chain = ConversationChain(
        prompt=llm_prompts.questions_prompt_template,
        llm=chat_model,
        verbose=True,
        memory=memory,
    )

    # Select the appropriate agent depending on session state
    # (start/check/summarise/review/finalise)
    match st.session_state["agentState"]:
        case "identify":
            identify.get_participant_id(llm_prompts)
        case "microphoneCheck":
            micCheck.checkmicrophone()
        case "micHelp":
            micCheck.show_mic_help_page()
        case "customize":
            customize.get_customize_request(llm_prompts)
            logger.info("try to customize")
        case "start":
            conversation.getData(
                llm_prompts,
                conversation_chain,
                message_history,
            )
        case "check":
            check.checkMessages(message_history)
        case "summarise":
            scenario.summariseData(
                llm_prompts,
                chat_model,
                message_history,
                extraction_chain,
                testing,
            )
        case "review":
            review.reviewData(
                smith_client,
                chat_model,
                llm_prompts.adaptation_prompt_template,
                llm_prompts.one_shot,
                testing,
            )
        case "finalise":
            scenario.finaliseScenario(
                chat_model, llm_prompts.adaptation_prompt_template
            )
        case "save":
            finalise.saveScenario(
                message_history, table
                )
        case "final":
            finalise.display_completion_page(bucket, transcribe)
        case "audioPreview":
            finalise.display_audio_preview_page()
        case "audioConfirmed":
            finalise.display_save_congratulations_page(
                message_history,
                table,
                transcribe,
            )


def markConsent():
    """
    Updates the session's consent marker; used when button is pressed on consent page.
    """

    logger.info("Consent given")
    st.session_state["consent"] = True


def requestConsent(consent_text):
    """
    Generates a page with the provided consent text and a button to accept.
    """

    logger.info("Consent not provided")
    consent_message = st.container()
    with consent_message:
        st.markdown(consent_text)
        st.button("I accept", key="consent_button", on_click=markConsent)


@st.cache_resource
def createLLMPromptsFromFile(config_file):
    """
    Generate set of prompts and other strings required by the app from config file.
    Args:
        config_file (str): path to configuration file
    """

    logger.info(f"Configuring app using {config_file}\n")
    llm_prompts = LLMConfig(config_file)

    return llm_prompts


def initialiseAppPage():
    """
    Initialise the Streamlit app's page.
    """

    st.set_page_config(page_title="Storytelling Chatbot", page_icon="💬")
    st.title("💬 Storytelling Chatbot")

    # Hide GitHub icon
    st.markdown(
        """
        <style>
        [data-testid="stToolbarActions"] {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialiseStreamlitSessionState(num_scenarios):
    """
    Initialise variables that persist throughout refreshes of a Streamlit session.
    """

    # The participant ID for tracking across sessions
    if "participant_id" not in st.session_state:
        st.session_state["participant_id"] = None

    # Whether the user has provided consent
    if "consent" not in st.session_state:
        st.session_state["consent"] = False

    # The current state of the app
    if "agentState" not in st.session_state:
        st.session_state["agentState"] = "identify"

    # A unique identifier for this conversation
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = (
            st.runtime.scriptrunner.get_script_run_ctx().session_id
        )

    # Also track LangSmith ID (may not be used depending on data storage choice)
    if "langsmith_run_id" not in st.session_state:
        st.session_state["langsmith_run_id"] = None

    # A dict containing key points from the conversation
    if "summary_answers" not in st.session_state:
        st.session_state["summary_answers"] = {}

    # The scenarios generated by the LLM, based on the summary answers
    if "generated_scenarios" not in st.session_state:
        st.session_state["generated_scenarios"] = [""] * num_scenarios

    # Numerical feedback from the user on each of the scenarios
    if "scenario_feedback" not in st.session_state:
        st.session_state["scenario_feedback"] = [None] * num_scenarios

    # Textual judgement on initial scenario content (may not be completed for all)
    if "scenario_judgement" not in st.session_state:
        st.session_state["scenario_judgement"] = [""] * num_scenarios

    # The index of the selected scenario
    if "selected_scenario_index" not in st.session_state:
        st.session_state["selected_scenario_index"] = None

    # The text of the selected scenario (potentially with adaptations)
    if "final_scenario" not in st.session_state:
        st.session_state["final_scenario"] = ""

    # Full recorded audio from the final storytelling step
    if "Audio_Story" not in st.session_state:
        st.session_state["Audio_Story"] = None

    # First 10 seconds of the recorded audio for playback preview
    if "Audio_Story_Preview" not in st.session_state:
        st.session_state["Audio_Story_Preview"] = None

    # Transcript generated from the final audio recording
    if "Text_Story" not in st.session_state:
        st.session_state["Text_Story"] = ""

    # Whether the final transcription + save step has completed
    if "_final_processing_complete" not in st.session_state:
        st.session_state["_final_processing_complete"] = False

@st.cache_resource
def loadSettings():
    """
    Obtain settings from streamlit secrets file and/or command line arguments.
    """

    # LangChain uses API keys and settings from env
    os.environ["LANGCHAIN_API_KEY"] = st.secrets["LANGCHAIN_API_KEY"]
    os.environ["LANGCHAIN_PROJECT"] = st.secrets["LANGCHAIN_PROJECT"]
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if st.secrets["LANGCHAIN_ENDPOINT"]:
        os.environ["LANGCHAIN_ENDPOINT"] = st.secrets["LANGCHAIN_ENDPOINT"]

    # Get an OpenAI API Key before continuing
    if "OPENAI_API_KEY" in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
    else:
        os.environ["OPENAI_API_KEY"] = st.sidebar.text_input(
            "OpenAI API Key", type="password"
        )
    if not os.environ["OPENAI_API_KEY"]:
        st.info("Enter an OpenAI API Key to continue")
        st.stop()

    # Identify config file from input args or streamlit secrets
    input_args = sys.argv[1:]
    if len(input_args):
        config_file = input_args[0]
    else:
        config_file = st.secrets.get(
            "CONFIG_FILE", os.path.join("configs", "example_social.toml")
        )

    return config_file


def buildExtractionChain(extraction_prompt_template, model_name):
    """
    Create a chain to generate json-formatted output based on the conversation history.
    Args:
        extraction_prompt (str): text for the extraction prompt
        model_name (str): name of the OpenAI LLM
    Returns:
        RunnableSequence: chain to extract json-formatted output from conversation
    """

    extraction_llm = ChatOpenAI(
        temperature=0.1, model=model_name, openai_api_key=os.environ["OPENAI_API_KEY"]
    )

    extraction_chain = (
        extraction_prompt_template | extraction_llm | SimpleJsonOutputParser()
    )

    return extraction_chain


@st.cache_resource
def createDatabaseLink():
    """
    Set up a boto3 session to handle connection to the DynamoDB database (if required).
    The table name should be specified via Streamlit secrets; if none is provided, the
    process of saving to a database will be skipped. Relies on credentials being
    available in the current environment.
    Returns:
        table (DynamoDB.Table | None): the DynamoDB table where the data will be stored,
            or None if storage in a database is not required
    """

    if table_name := st.secrets.get("DYNAMODB_TABLE_NAME"):
        session = boto3.Session()
        dynamodb_resource = session.resource("dynamodb")
        table = dynamodb_resource.Table(table_name)
        logger.info(f"Data will be saved to {table_name}\n")
    else:
        table = None
        logger.info("No database details provided\n")

    return table

@st.cache_resource
def createBucketLink():
    """
    Set up a boto3 session to handle connection to the s3 bucket (if required).
    The bucket name should be specified via Streamlit secrets; if none is provided, the
    process of saving audio to a bucket will be skipped. Relies on credentials being
    available in the current environment.
    Returns:
        bucket (s3.Bucket | None): the s3 bucket where the final audio will be stored,
            or None if storage in a database is not required
    """

    if bucket_name := st.secrets.get("S3_BUCKET_NAME"):
        bucket = boto3.client(
            service_name = 's3',
            region_name = st.secrets.get("AWS_DEFAULT_REGION"),
            aws_access_key_id = st.secrets.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key = st.secrets.get("AWS_SECRET_ACCESS_KEY")
        )
        logger.info(f"audio will be saved to {bucket_name}\n")
    else:
        bucket = None
        logger.info("No bucket details provided\n")

    return bucket


@st.cache_resource
def createTranscribeLink():
    """
    Create and cache a boto3 Transcribe client.
    Uses Streamlit secrets for region + credentials, same as your S3 setup.
    Returns:
        transcribe (boto3 client): Amazon Transcribe client
    """
    region = st.secrets.get("AWS_DEFAULT_REGION", "us-east-1")

    transcribe = boto3.client(
        service_name="transcribe",
        region_name=region,
        aws_access_key_id=st.secrets.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=st.secrets.get("AWS_SECRET_ACCESS_KEY"),
    )

    logger.info(f"Transcribe client initialized in region {region}")
    return transcribe

if __name__ == "__main__":
    logger = st.logger.get_logger("micronarratives")

    initialiseAppPage()

    config_file = loadSettings()
    llm_prompts = createLLMPromptsFromFile(config_file)
    table = createDatabaseLink()
    bucket = createBucketLink()
    transcribe = createTranscribeLink()

    # Initialise Streamlit session and LangSmith
    initialiseStreamlitSessionState(len(llm_prompts.personas))
    chat_model = ChatOpenAI(
        temperature=0.3,
        model=llm_prompts.model_name,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )

    smith_client = Client()
    message_history = StreamlitChatMessageHistory(key="langchain_messages")
    memory = ConversationBufferMemory(memory_key="history", chat_memory=message_history)

    extraction_chain = buildExtractionChain(
        llm_prompts.extraction_prompt_template, llm_prompts.model_name
    )

    if st.session_state["consent"]:
        stateAgent(
            llm_prompts,
            chat_model,
            extraction_chain,
            smith_client,
            message_history,
            memory,
            table,
            bucket,
            transcribe,
        )
    else:
        requestConsent(llm_prompts.intro_and_consent)