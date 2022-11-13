import argparse
from collections import OrderedDict
from datetime import datetime
import json
import time

import boto3

from progress_bar import SlackProgress


def main(args: argparse.Namespace) -> None:
    slack_token = args.slack_token
    channel_name = args.channel_name
    project_name = args.project_name
    iam_slack_usernames_mapping = args.iam_slack_usernames_mapping

    codebuild_client = boto3.client('codebuild')

    iam_slack_usernames_mapping = json.loads(iam_slack_usernames_mapping)
    sts_client = boto3.client('sts')
    response = sts_client.get_caller_identity()
    iam_username = response['Arn'].partition('/')[-1]
    if iam_slack_usernames_mapping.get(iam_username):
        iam_username_log_message = f"<@{iam_slack_usernames_mapping[iam_username]}>"
    else:
        iam_username_log_message = f"'AWS User {iam_username}'"

    build_response_data: dict = codebuild_client.start_build(
        projectName=project_name,
    )
    build_id = build_response_data["build"]["id"]
    build_status = build_response_data["build"]["buildStatus"]

    # Initialize Slack here
    sp = SlackProgress(token=slack_token, channel=channel_name)
    current_percentage_int = 0

    build_phases_updated_in_slack_mapping = OrderedDict([
        ("SUBMITTED", False),
        ("QUEUED", False),
        ("PROVISIONING", False),
        ("DOWNLOAD_SOURCE", False),
        ("INSTALL", False),
        ("PRE_BUILD", False),
        ("BUILD", False),
        ("POST_BUILD", False),
    ])

    # Initialize Slack ProgressBar here
    pbar = sp.new()
    log_message = f"Build: *{project_name}*, BuildStatus=`{build_status}`, Initiated by: {iam_username_log_message}"
    pbar.pos = current_percentage_int
    pbar.log(log_message)

    is_build_running = True
    while is_build_running:
        print(f"Sleeping for 5 sec... {datetime.now()}")
        time.sleep(5)

        build_response_data: dict = codebuild_client.batch_get_builds(
            ids=[build_id]
        )

        build_status = build_response_data["builds"][0]["buildStatus"]
        if build_status != 'IN_PROGRESS':
            # break here and update slack finally.
            is_build_running = False
            log_message = f"Build: *{project_name}*, BuildStatus=`{build_status}`"
            if build_status == 'SUCCEEDED':
                log_message_emoji = ":large_blue_circle:"
            else:
                log_message_emoji = ":red_circle:"
            log_message += log_message_emoji
            pbar.pos = 100
            pbar.log(log_message)
            break

        current_build_phases = build_response_data["builds"][0]["phases"]
        for index, (_build_phase, _is_build_phase_updated_in_slack) in enumerate(list(build_phases_updated_in_slack_mapping.items()), start=1):
            if _is_build_phase_updated_in_slack:
                continue

            print(f"updating {_build_phase} in slack...")
            build_phase_found = False
            phases_found = []
            for current_build_phase in current_build_phases:
                phaseType = current_build_phase["phaseType"]
                phases_found.append(phaseType)

                if _build_phase != phaseType:
                    continue

                build_phase_found = True
                break

            if not build_phase_found:
                print(f"ughh, Build Phase {_build_phase} not found, found {phases_found} instead")
                break

            if not current_build_phase.get("phaseStatus"):
                print(f"ughh, Build Phase {_build_phase} has no status yet.")
                break

            phase_type, phase_status = current_build_phase["phaseType"], current_build_phase["phaseStatus"]
            log_message = f"Build's Phase: {phase_type}, PhaseStatus=*{phase_status}*"
            current_percentage_int += 100/len(build_phases_updated_in_slack_mapping.keys())
            pbar.pos = current_percentage_int
            pbar.log(log_message)
            build_phases_updated_in_slack_mapping[_build_phase] = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='aws-deployments-test',
        description='Pushes updates to slack about a CodeBuild'
    )
    parser.add_argument('--slack_token', type=str)
    parser.add_argument('--channel_name', type=str)
    parser.add_argument('--project_name', type=str)
    parser.add_argument('--iam_slack_usernames_mapping', default="{}", type=str)
    args = parser.parse_args()

    main(args=args)
