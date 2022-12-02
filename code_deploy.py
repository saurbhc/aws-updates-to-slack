import argparse
from collections import OrderedDict
from datetime import datetime
import json
import time
import subprocess

import boto3

from progress_bar import SlackProgress


def main(args: argparse.Namespace) -> None:
    slack_token = args.slack_token
    channel_name = args.channel_name
    project_name = args.project_name
    iam_slack_usernames_mapping = args.iam_slack_usernames_mapping
    aws_region = args.aws_region
    slack_link = args.slack_link
    commit_id = args.commit_id
    ssh_git_repo_url = args.ssh_git_repo_url
    git_repo_branch = args.git_repo_branch
    deployment_group_name = args.deployment_group_name
    repository_name = args.repository_name

    if not commit_id:
        commit_id = subprocess.Popen(f"echo -n \"$(git ls-remote {ssh_git_repo_url} | grep refs/heads/{git_repo_branch} | cut -f 1)\"", shell=True, stdout=subprocess.PIPE).stdout.read()
        commit_id = commit_id.decode("utf-8")

    codedeploy_client = boto3.client('codedeploy')

    iam_slack_usernames_mapping = json.loads(iam_slack_usernames_mapping)
    sts_client = boto3.client('sts')
    response = sts_client.get_caller_identity()
    iam_username = response['Arn'].partition('/')[-1]
    if iam_slack_usernames_mapping.get(iam_username):
        iam_username_log_message = f"<@{iam_slack_usernames_mapping[iam_username]}>"
    else:
        iam_username_log_message = f"'AWS User {iam_username}'"

    deployment_id = args.deployment_id
    if not deployment_id:
        print(f"creating deployment for commit_id: {commit_id}...")
        deploy_response_data: dict = codedeploy_client.create_deployment(
            applicationName=project_name,
            deploymentGroupName=deployment_group_name,
            deploymentConfigName="CodeDeployDefault.AllAtOnce",
            description=f"Initiated by code_deploy.py script - by {iam_username}",
            revision={
                "revisionType": "GitHub",
                "gitHubLocation": {
                    "repository": f"{repository_name}/{project_name}",
                    "commitId": commit_id,
                }
            },
            fileExistsBehavior='OVERWRITE'
        )
        deployment_id = deploy_response_data["deploymentId"]
    print(f"deployment_id: {deployment_id}...")

    # Get Deployment
    deploy_response_data = codedeploy_client.get_deployment(
        deploymentId=deployment_id
    )
    deployment_info = deploy_response_data["deploymentInfo"]
    deployment_status = deployment_info["status"]

    # List Deployment Instances
    is_deployment_ready = False
    while not is_deployment_ready:
        try:
            response = codedeploy_client.list_deployment_instances(
                deploymentId=deployment_id,
            )
            instances_list = response["instancesList"]
            is_deployment_ready = True
        except Exception as err:
            print(err)
            print(f"deployment not ready, sleeping for 5 sec")
            time.sleep(5)

    deploy_phases_updated_in_slack_mapping = {}
    for instance in instances_list:
        deploy_phases_updated_in_slack_mapping[instance] = OrderedDict()

    # Batch Get Deployment Targets
    response = codedeploy_client.batch_get_deployment_instances(
        deploymentId=deployment_id,
        instanceIds=instances_list
    )
    for deployment_instance in response['instancesSummary']:
        deployment_instance_id = deployment_instance['instanceId']
        _instance_id = deployment_instance_id.rpartition("/")[-1]
        deployment_instance_lifecycle_events = deployment_instance['lifecycleEvents']
        deploy_phases_updated_in_slack_mapping[_instance_id] = {}

        for deployment_instance_lifecycle_event in deployment_instance_lifecycle_events:
            lifecycle_event_name = deployment_instance_lifecycle_event["lifecycleEventName"]
            deploy_phases_updated_in_slack_mapping[_instance_id][lifecycle_event_name] = False

    # Create AWS CodeDeploy Console URL
    code_deploy_console_link = f"https://{aws_region}.console.aws.amazon.com/codesuite/codedeploy/deployments/{deployment_id}?region={aws_region}"

    # Initialize Slack here
    prefix = f"<{code_deploy_console_link}|*CodeDeploy: {project_name} - {deployment_group_name}*>"
    if slack_link:
        slack_link_pts = slack_link.rpartition('/')[-1]
        msg_ts = f"{(slack_link_pts.split('p')[-1])[:-6]}.{(slack_link_pts.split('p')[-1])[-6:]}"
        sp = SlackProgress(token=slack_token, channel=channel_name, prefix=prefix, msg_ts=msg_ts)
    else:
        sp = SlackProgress(token=slack_token, channel=channel_name, prefix=prefix)
    current_percentage_int = 0

    # Initialize Slack ProgressBar here
    pbar = sp.new()
    log_message = f"Build: *{project_name}*, DeploymentStatus=`{deployment_status}`, Initiated by: {iam_username_log_message}"
    pbar.pos = current_percentage_int
    pbar.log(log_message)

    is_deployment_in_progress = True if deployment_status not in ['Succeeded', 'Failed', 'Stopped'] else False
    while is_deployment_in_progress:
        print(f"Sleeping for 5 sec... {datetime.now()}")
        time.sleep(5)

        ## Update new phases
        # Get Deployment
        deploy_response_data = codedeploy_client.get_deployment(
            deploymentId=deployment_id
        )
        deployment_info = deploy_response_data["deploymentInfo"]
        deployment_status = deployment_info["status"]
        is_deployment_in_progress = True if deployment_status not in ['Succeeded', 'Failed', 'Stopped'] else False
        if not is_deployment_in_progress:
            # break here and update slack finally.
            log_message = f"Deploy: *{project_name}*, DeployentStatus=`{deployment_status}`"
            if deployment_status == 'Succeeded':
                log_message_emoji = ":large_blue_circle:"
            else:
                log_message_emoji = ":red_circle:"
            log_message += log_message_emoji
            pbar.pos = 100
            pbar.log(log_message)
            break

        # List Deployment Instances
        response = codedeploy_client.list_deployment_instances(
            deploymentId=deployment_id,
        )
        instances_list = response["instancesList"]

        # Batch Get Deployment Targets
        response = codedeploy_client.batch_get_deployment_instances(
            deploymentId=deployment_id,
            instanceIds=instances_list
        )
        for deployment_instance in response['instancesSummary']:
            deployment_instance_id = deployment_instance['instanceId']
            _instance_id = deployment_instance_id.rpartition("/")[-1]
            deployment_instance_lifecycle_events = deployment_instance['lifecycleEvents']
            if not deploy_phases_updated_in_slack_mapping.get(_instance_id):
                deploy_phases_updated_in_slack_mapping[_instance_id] = {}

            for deployment_instance_lifecycle_event in deployment_instance_lifecycle_events:
                lifecycle_event_name = deployment_instance_lifecycle_event["lifecycleEventName"]
                # lifecycle_event_status = deployment_instance_lifecycle_event["status"]
                if lifecycle_event_name not in deploy_phases_updated_in_slack_mapping[_instance_id]:
                    deploy_phases_updated_in_slack_mapping[_instance_id][lifecycle_event_name] = False

        # 
        for instance_id, instance_phases in deploy_phases_updated_in_slack_mapping.items():
            deploy_phase_found = False
            for _deploy_phase, _is_deploy_phase_updated_in_slack in instance_phases.items():
                if _is_deploy_phase_updated_in_slack:
                    continue

                print(f"updating {_deploy_phase} in slack...")
                phases_found = []
                break_main = False
                for deployment_instance in response['instancesSummary']:
                    if break_main:
                        break

                    deployment_instance_id = deployment_instance['instanceId']
                    _instance_id = deployment_instance_id.rpartition("/")[-1]
                    if instance_id != _instance_id:
                        continue

                    deployment_instance_lifecycle_events = deployment_instance['lifecycleEvents']
                    for deployment_instance_lifecycle_event in deployment_instance_lifecycle_events:
                        lifecycle_event_name = deployment_instance_lifecycle_event["lifecycleEventName"]
                        # lifecycle_event_status = deployment_instance_lifecycle_event["status"]
                        phases_found.append(lifecycle_event_name)
                        if _deploy_phase != lifecycle_event_name:
                                continue

                        deploy_phase_found = True
                        break_main = True
                        phase_type, phase_status, instance_label = lifecycle_event_name, deployment_instance_lifecycle_event.get("status"), deployment_instance.get("instanceType")

                        if not phase_status:
                            print(f"ughh, Deploy Phase {_deploy_phase} has no status yet.")
                            break

                        if phase_status in ['Pending', 'InProgress']:
                            print(f"skipping, phase {phase_type} has status {phase_status}")
                            continue

                        log_message = f"Deploy: *{project_name}*, DeployentStatus=`{deployment_status}`"
                        print(f"instance_label: {instance_label}")
                        
                        if instance_label == 'Blue':
                            log_message_emoji = ":blue_book:"
                        else:
                            log_message_emoji = ":green_book:"

                        instance_link = f"https://{aws_region}.console.aws.amazon.com/ec2/v2/home?region={aws_region}#Instances:instanceId={_instance_id}"
                        log_message = f"Deployment's Phase: {phase_type}, [{log_message_emoji} <{instance_link}|*{_instance_id}*>] PhaseStatus=*{phase_status}*"
                        current_percentage_int += 100/13
                        current_percentage_int = round(current_percentage_int, 1)
                        pbar.pos = current_percentage_int
                        pbar.log(log_message)
                        deploy_phases_updated_in_slack_mapping[_instance_id][_deploy_phase] = True
                        break

    log_message = f"{prefix} *{deployment_status}!* {iam_username_log_message}"
    pbar.log_thread(log_message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='aws-deployments-test',
        description='Pushes updates to slack about a CodeDeploy'
    )
    parser.add_argument('--slack_token', type=str)
    parser.add_argument('--channel_name', type=str)
    parser.add_argument('--iam_slack_usernames_mapping', type=str)
    parser.add_argument('--aws_region', default="eu-west-1", type=str)
    parser.add_argument('--slack_link', type=str)

    parser.add_argument('--project_name', type=str)
    parser.add_argument('--deployment_group_name', type=str)
    parser.add_argument('--deployment_id', default="", type=str)

    parser.add_argument('--commit_id', type=str)
    parser.add_argument('--ssh_git_repo_url', type=str)
    parser.add_argument('--git_repo_branch', type=str)
    parser.add_argument('--repository_name', type=str)

    args = parser.parse_args()

    main(args=args)
