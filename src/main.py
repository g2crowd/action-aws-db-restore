import argparse

from src.config import is_sharing_enabled, is_valid, load_config, replace_placeholder
from src.rds import (
    copy_snapshot,
    does_target_exists,
    get_snapshot_details,
    init_client,
    restore_snapshot,
    share_snapshot,
)
from src.tf import get_outputs
from src.utils import assume_aws_role, setup_custom_logger

LOGGER = setup_custom_logger("root")


def main(command_line=None):
    parser = argparse.ArgumentParser(description="Restore RDS snapshot")
    parser.add_argument("-c", "--config", required=True)
    parser.add_argument("-t", "--tfstate")
    args = parser.parse_args(command_line)

    data = load_config(args.config)
    status, err = is_valid(data)
    if not status:
        LOGGER.error(err)
        exit(1)

    source = data["Source"]
    target = data["Target"]
    target_credentials = assume_aws_role(target.get("AssumeRole"), "target")

    tf_outputs = get_outputs(target_credentials, args.tfstate)
    if args.tfstate and tf_outputs is None:
        LOGGER.error("TF state file does not exists")
        exit(1)

    source = replace_placeholder(source, tf_outputs or {}, target_credentials)
    target = replace_placeholder(target, tf_outputs or {}, target_credentials)

    target_client = init_client(target_credentials)
    target_exists = does_target_exists(
        target_client, target["DBIdentifier"], data["ClusterMode"]
    )
    if target_exists and not data.get("DeleteExistingTarget", True):
        LOGGER.error("Target DB already exists and target DB deletion is disabled")
        exit(1)

    if is_sharing_enabled(source):
        # Cross-account: copy snapshot in source account with shared KMS key,
        # then share with target account.
        source_share_credentials = assume_aws_role(
            source["Share"]["AssumeRole"], "source"
        )
        source_client = init_client(source_share_credentials)
        (
            target["SnapshotIdentifier"],
            target["SnapshotArn"],
            target["Engine"],
            target["EngineVersion"],
        ) = share_snapshot(
            source_client,
            source["DBIdentifier"],
            target["DBIdentifier"],
            source["Share"]["SourceKmsKey"],
            source["Share"]["TargetAccount"],
            data["ClusterMode"],
        )
        if target["SnapshotIdentifier"] is None:
            LOGGER.error("Failed to share snapshot")
            exit(1)

        LOGGER.info(
            "Updating KMS key of {} with {}".format(
                target["SnapshotArn"], source["Share"]["TargetKmsKey"]
            )
        )
    else:
        # Snapshot already exists in target account (cross-account copy was done
        # externally). Source.DBIdentifier is the snapshot identifier in target account.
        LOGGER.info(
            "Snapshot {} already in target account, skipping share step".format(
                source["DBIdentifier"]
            )
        )
        (
            target["SnapshotIdentifier"],
            target["SnapshotArn"],
            target["Engine"],
            target["EngineVersion"],
        ) = get_snapshot_details(
            target_client, source["DBIdentifier"], data["ClusterMode"]
        )
        if target["SnapshotArn"] is None:
            LOGGER.error(
                "Snapshot {} not found in target account".format(source["DBIdentifier"])
            )
            exit(1)

    restore_snapshot(target_client, target, target_exists, data["ClusterMode"])


if __name__ == "__main__":
    main()
