# Deployment

This repository ships two things that deploy **separately**:

1. **The recorder (App 2)** — a Streamlit app (`app.py`). Deploy it to Streamlit Community
   Cloud or AWS Elastic Beanstalk, as described below.
2. **The transcription pipeline (App 3)** — two AWS Lambda functions in
   `transcription_pipeline/`. It is **not** part of the Streamlit deployment; deploy it to
   AWS following [`transcription_pipeline/README.md`](../transcription_pipeline/README.md).

The two communicate only through S3 (the recorder uploads a `.wav`, which triggers the
pipeline) and DynamoDB — so they can be deployed independently, in either order.

## Streamlit Community Cloud

[Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud) is
the quickest way to host the recorder. The repository is already compatible (correct
structure, `Pipfile.lock` listing dependencies), so you can go straight to the
["Deploy!"](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
instructions in Streamlit's documentation, pointing it at `app.py`. Deployments are
triggered on every push to the selected branch.

Then follow
["Optional: Configure secrets and Python version"](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy#optional-configure-secrets-and-python-version):

- Set the Python version to **3.12**.
- Add the secrets described in [`setup.md`](./setup.md#secrets) (`S3_BUCKET_NAME`,
  `DYNAMODB_TABLE_NAME`, and the AWS region/credentials).

## AWS Elastic Beanstalk

The recorder can also run on AWS Elastic Beanstalk. Because it both **reads** DynamoDB and
**writes** to S3, its instance role needs S3 and DynamoDB permissions.

Before you start, log into the AWS Management Console and switch to your preferred region
at the top-right. This should match the region of your S3 bucket and DynamoDB table (the
current deployment uses `us-east-2`).

### Prepare the DynamoDB table and S3 bucket

The recorder expects the shared `session_id`-keyed DynamoDB table (created by / shared with
the conversation app) and the audio S3 bucket that the transcription pipeline watches:

- **DynamoDB table** — partition key `session_id` (String), no sort key. See
  [`setup.md`](./setup.md#secrets) for how the recorder connects to it.
- **S3 bucket** — the recorder uploads recordings to it, and the pipeline's Lambda A must
  be triggered by `ObjectCreated` events for `.wav` objects in the same bucket (see the
  pipeline README).

Set both names, the region, and credentials in `.streamlit/secrets.toml` before zipping the
app for upload.

### Deploy the app using Elastic Beanstalk

Follow the Elastic Beanstalk
["Getting started"](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/GettingStarted.CreateApp.html)
guide; the recorder-specific steps are:

* Open **Elastic Beanstalk** from the "Services" menu and click **Create environment**.

#### Step 1 — Configure environment

* Choose names for the app and environment.
* Set **Platform** to Python, **Platform branch** to Python 3.12.
* Under **Application code**, choose **Upload your code**, give it a version label, and
  upload a zip of the app.
  * Only the files needed to run the recorder are required. Generate the zip from the repo
    root with:

    ```sh
    zip -r app.zip *.py Procfile Pipfile.lock LICENSE .streamlit
    ```

  * The `Procfile` contains the command AWS runs to start the app.
  * Do **not** include `transcription_pipeline/` — it is deployed separately as Lambdas,
    not run by Beanstalk.

#### Step 2 — Configure service access

* For "Existing service roles", see
  [step 9 of the Getting Started guide](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/GettingStarted.CreateApp.html#GettingStarted.CreateApp.Create).
* The recorder needs to reach both S3 and DynamoDB, so instead of the default
  `aws-elasticbeanstalk-ec2-role`, create a role with the same defaults **plus** access to
  those services. When selecting permission policies, add (in addition to the three
  recommended policies):
  * `AmazonS3FullAccess` (or a scoped policy allowing `s3:PutObject` on your audio bucket), and
  * `AmazonDynamoDBReadOnlyAccess` (or a scoped policy allowing `dynamodb:GetItem` on your table).

#### Steps 3 & 4 — Networking, database, tags, traffic and scaling

* Leave configurations as they are.

#### Step 5 — Updates, monitoring, and logging

* Under **Add environment property**, add:
  * `PORT` = `8501`
  * `AWS_REGION` = your region (e.g. `us-east-2`)
* Review all configurations and submit.

### Recommended changes for production deployments

#### Set up a load balancer

* Navigate to your Elastic Beanstalk environment → **Configuration**.
* Edit **Instance traffic and scaling** and switch **Environment type** to **Load
  balanced** (this creates an application load balancer). For low user numbers, a maximum
  of 1 instance is fine.

If enhanced health reporting is enabled, update the health check path:

* Search the console for **Load balancers (EC2 feature)** → **Target Groups**.
* Select your target group → **Health check** tab → **Edit**.
* Replace the default path with `/healthz` (used by Streamlit) and save.

#### Use a custom domain name

A custom domain gives a cleaner URL and enables HTTPS. See
[Routing traffic to an Elastic Beanstalk environment](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-to-beanstalk-environment.html).
If your domain was not provided by AWS, follow the
[additional instructions](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/MigratingDNS.html)
to use Route 53 as its DNS service. For subdomains, see
[Routing traffic for subdomains](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-routing-traffic-for-subdomains.html).

#### Configure HTTPS

Follow the AWS documentation to configure
[HTTPS termination at the load balancer](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/configuring-https-elb.html).
If you do not already have a certificate for your domain, that page explains how to create
one.

#### Alter headers (e.g. to embed in a survey)

To embed the recorder in an iframe (for example inside a Qualtrics survey), relax the
reverse proxy's content security policy. See
[Reverse proxy configuration](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.proxy.html)
for background, then:

* Create `.platform/nginx/conf.d/` in the repository and add a `.conf` file (any name,
  e.g. `amend_headers.conf`) containing:

  ```conf
  add_header Content-Security-Policy "frame-ancestors 'self' https://your-survey-host.example.com;";
  ```

* Adjust the `frame-ancestors` list to the hosts allowed to embed the app (see
  [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors)).
* Include the `.platform` folder in the deployment zip and redeploy.
