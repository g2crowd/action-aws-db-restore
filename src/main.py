import argparse
import os

import rds
import utils

LOGGER = utils.setup_custom_logger("root")


def main(command_line=None):
    parser = argparse.ArgumentParser(description="Restore RDS snapshot")
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--delete", required=True)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--key")
    parser.add_argument("--share")
    parser.add_argument("--account")
    parser.add_argument("--sg")
    parser.add_argument("--az")
    parser.add_argument("--subnet")
    parser.add_argument("--tags")
    parser.add_argument("--assume")
    args = parser.parse_args(command_line)

    db_config = {}
    source_snapshot = args.source
    target_exists = rds.target_exists(args.assume, args.target, args.cluster)
    if target_exists and not args.delete:
        LOGGER.error("Target DB already exists and target DB deletion is disabled")
        exit(1)

    if args.share is not None:
        if args.key is None:
            LOGGER.error("The KMS key Id is required for sharing snapshot")
            exit(1)
        source_snapshot = rds.share_snashot(
            args.assume, args.source, args.target, args.key, args.account, args.cluster
        )

    if database is None:
        db_config["security_groups"] = (
            [] if args.sg is None else args.sg.strip().split(",")
        )
        db_config["availability_zone"] = "" if args.az is None else args.az.strip()
        db_config["subnet_group"] = "" if args.subnet is None else args.subnet.strip()
        db_config["tags"] = [] if args.tags is None else get_tags(args.tags)
    else:
        db_config = rds.get_config(args.assume, args.database, args.cluster)

    rds.restore_snashot(
        args.assume, args.source, args.target, db_config, target_exists, args.cluster
    )


if __name__ == "__main__":
    main()
