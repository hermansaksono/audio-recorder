# Setup

In this file, we will collect notes on the options in the config files and other things that will be relevant to users owning an an instance of the app.

## Participant ID tracking

In the `Participant tracking settings` section of the config file, you can set whether a user of your app is required to provide a participant ID. 
If a user must provide a participant ID, set `require_participant_id = true`; otherwise this setting can be left out entirely or set to `false`.

If a participant ID is required, the user will be prompted to provide one after giving consent. 
They can either fill the input widget on their own, or, if a participant ID is embedded in the URL (e.g., as in http://my-micro-narratives-app/?participant_id=TESTID1234), confirm the suggestion in the prefilled input widget (in this example, `TESTID1234`).

If the participant ID is not required, a placeholder will be used when the data is sent to the database.
This will be the same as the Streamlit session ID.

If you choose to embed a participant ID in the URL of your app, make sure you use `participant_id` as the query parameter, as the app won't be able to extract IDs from other ones. 
If a different query parameter is used, the app will not prefill the input widget, and the user will have to provide the ID themselves.
