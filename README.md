# aws-updates-to-slack

How this would look in Slack:
```
aws-deployments-test APP  12:02 AM
    ████████████████████ 100.0%
    00:02:12 - [Build: project-name BuildStatus=IN_PROGRESS!]
    00:02:17 - [Build's Phase: SUBMITTED PhaseStatus=SUCCEEDED]
    00:02:18 - [Build's Phase: QUEUED PhaseStatus=SUCCEEDED]
    00:02:48 - [Build's Phase: PROVISIONING PhaseStatus=SUCCEEDED]
    00:02:53 - [Build's Phase: DOWNLOAD_SOURCE PhaseStatus=SUCCEEDED]
    00:03:14 - [Build's Phase: INSTALL PhaseStatus=SUCCEEDED]
    00:03:19 - [Build's Phase: PRE_BUILD PhaseStatus=SUCCEEDED]
    00:05:00 - [Build's Phase: BUILD PhaseStatus=SUCCEEDED]
    00:05:31 - [Build's Phase: POST_BUILD PhaseStatus=SUCCEEDED]
    00:05:36 - [Build: project-name BuildStatus=SUCCEEDED!] (edited)
```

Run script by:
```bash
python3 code_build.py \
    --slack_token <...SLACK_TOKEN_HERE> \
    --channel_name <...SLACK_CHANNEL_NAME_HERE> \
    --project_name <...AWS_CODE_BUILD_PROJECT_NAME_HERE>
```