import logging

import boto3

LOGGER = logging.getLogger("root")


def setup_custom_logger(name):
    formatter = logging.Formatter(fmt="[%(levelname)s] %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


def assume_aws_role(role_arn, role_name):
    if not role_arn:
        return None

    LOGGER.info(f"Assuming {role_name} AWS role")
    client = boto3.client("sts")
    response = client.assume_role(
        RoleArn=role_arn, RoleSessionName="RestoreDBSession", DurationSeconds=28800
    )
    return response["Credentials"]
