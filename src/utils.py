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


def get_tags(input):
    tags = []
    input = input.strip().split(",")

    for item in input:
        tag = {}
        item = item.split(":")
        if len(item) != 2:
            LOGGER.error("Invalid tags")
            exit(1)

        tag["Key"] = item[0]
        tag["Value"] = item[1]
        tags.append(tag)
    return tags


def validate_db_config(db_config):
    db_config["security_groups"] = args.sg.strip().split(",")
    db_config["availability_zone"] = args.az.strip()
    db_config["subnet_group"] = args.subnet.strip()
    db_config["tags"] = get_tags(args.tags)

    if len(db_config["security_groups"]) == 0:
        LOGGER.error("Invalid security groups")
        exit(1)
    if db_config["availability_zone"] == "":
        LOGGER.error("Invalid availability zone")
        exit(1)
    if db_config["subnet_group"] == "":
        LOGGER.error("Invalid subnet group")
        exit(1)
